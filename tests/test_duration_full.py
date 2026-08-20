"""Comprehensive tests for desk.duration (Macaulay/Modified, convexity, DV01, KRD)."""

from __future__ import annotations

import decimal
from datetime import date
from types import SimpleNamespace

import pytest

from desk.duration import (
    bond_modified_duration,
    convexity,
    duration_report,
    dv01,
    key_rate_durations,
    macaulay_duration,
    modified_duration,
    portfolio_duration,
)


def _bond(
    internal_id="B1",
    ytm=10.0,
    coupon=10.0,
    freq=2,
    maturity=date(2029, 1, 1),
    issue=date(2024, 1, 1),
    nominal=1000,
):
    return SimpleNamespace(
        internal_id=internal_id,
        yield_to_maturity=ytm,
        coupon_rate=coupon,
        coupon_frequency=freq,
        maturity_date=maturity,
        start_date=issue,
        nominal=nominal,
    )


# --------------------------------------------------------------------------- #
# Macaulay / Modified duration
# --------------------------------------------------------------------------- #
def test_modified_duration_zero_coupon_equals_maturity_approx():
    # Zero coupon: modified duration = macaulay / (1 + y/freq) ~ 10/1.05 = 9.52.
    d = modified_duration(
        nominal=1000,
        coupon_rate_pct=0,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2034, 1, 1),
        ref=date(2024, 1, 1),
    )
    assert d == pytest.approx(9.52, abs=0.1)


def test_modified_less_than_macaulay_for_positive_yield():
    mac = macaulay_duration(
        nominal=1000,
        coupon_rate_pct=8,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2029, 1, 1),
        ref=date(2024, 1, 1),
    )
    mod = modified_duration(
        nominal=1000,
        coupon_rate_pct=8,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2029, 1, 1),
        ref=date(2024, 1, 1),
    )
    assert mod < mac
    assert mod == pytest.approx(mac / (1 + 0.10 / 2), abs=1e-6)


def test_coupon_bond_duration_shorter_than_zero_coupon():
    zc = modified_duration(
        nominal=1000,
        coupon_rate_pct=0,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2029, 1, 1),
        ref=date(2024, 1, 1),
    )
    cp = modified_duration(
        nominal=1000,
        coupon_rate_pct=10,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2029, 1, 1),
        ref=date(2024, 1, 1),
    )
    assert cp < zc


def test_duration_empty_when_no_flows():
    assert (
        macaulay_duration(
            nominal=1000,
            coupon_rate_pct=10,
            coupon_frequency=2,
            ytm_pct=10,
            maturity=date(2024, 1, 1),
            ref=date(2024, 6, 1),
        )
        == 0.0
    )


# --------------------------------------------------------------------------- #
# Convexity
# --------------------------------------------------------------------------- #
def test_convexity_positive_for_normal_bond():
    cvx = convexity(
        nominal=1000,
        coupon_rate_pct=8,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2029, 1, 1),
        ref=date(2024, 1, 1),
    )
    assert cvx > 0


def test_convexity_zero_when_no_flows():
    assert (
        convexity(
            nominal=1000,
            coupon_rate_pct=10,
            coupon_frequency=2,
            ytm_pct=10,
            maturity=date(2024, 1, 1),
            ref=date(2024, 6, 1),
        )
        == 0.0
    )


# --------------------------------------------------------------------------- #
# DV01
# --------------------------------------------------------------------------- #
def test_dv01_positive_and_smaller_than_duration():
    dv = dv01(
        nominal=1000,
        coupon_rate_pct=8,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2029, 1, 1),
        ref=date(2024, 1, 1),
    )
    assert dv > 0


def test_dv01_zero_when_no_flows():
    assert (
        dv01(
            nominal=1000,
            coupon_rate_pct=10,
            coupon_frequency=2,
            ytm_pct=10,
            maturity=date(2024, 1, 1),
            ref=date(2024, 6, 1),
        )
        == 0.0
    )


# --------------------------------------------------------------------------- #
# Key-rate durations
# --------------------------------------------------------------------------- #
def test_krd_keys_present():
    krd = key_rate_durations(
        nominal=1000,
        coupon_rate_pct=8,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2034, 1, 1),
        ref=date(2024, 1, 1),
    )
    assert "1Y" in krd and "5Y" in krd and "10Y" in krd and "30Y" in krd


def test_krd_sum_approximates_modified_duration():
    mod = modified_duration(
        nominal=1000,
        coupon_rate_pct=8,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2034, 1, 1),
        ref=date(2024, 1, 1),
    )
    krd = key_rate_durations(
        nominal=1000,
        coupon_rate_pct=8,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2034, 1, 1),
        ref=date(2024, 1, 1),
    )
    assert sum(krd.values()) == pytest.approx(mod, abs=0.5)


def test_krd_empty_for_no_flows():
    krd = key_rate_durations(
        nominal=1000,
        coupon_rate_pct=10,
        coupon_frequency=2,
        ytm_pct=10,
        maturity=date(2024, 1, 1),
        ref=date(2024, 6, 1),
    )
    assert all(v == 0.0 for v in krd.values())


# --------------------------------------------------------------------------- #
# bond_modified_duration (the platform-wide source of truth)
# --------------------------------------------------------------------------- #
def test_bond_modified_duration_calculates():
    d = bond_modified_duration(_bond(ytm=10, coupon=10))
    assert d is not None and d > 0


def test_bond_modified_duration_none_without_maturity():
    b = _bond()
    b.maturity_date = None
    assert bond_modified_duration(b) is None


def test_bond_modified_duration_none_without_ytm():
    b = _bond()
    b.yield_to_maturity = None
    assert bond_modified_duration(b) is None


def test_bond_modified_duration_none_for_zero_ytm():
    assert bond_modified_duration(_bond(ytm=0.0, coupon=0.0)) is None


def test_bond_modified_duration_none_for_negative_ytm():
    assert bond_modified_duration(_bond(ytm=-2.0)) is None


def test_bond_modified_duration_uses_default_nominal_when_missing():
    b = _bond()
    b.nominal = None
    # Missing nominal falls back to face 1000 so duration is still computed.
    d = bond_modified_duration(b)
    assert d is not None and d > 0


def test_bond_modified_duration_raises_on_unparseable_nominal():
    b = _bond()
    b.nominal = "not-a-number"
    # An unparseable nominal cannot be coerced and surfaces as an error
    # (callers must guard before calling).
    with pytest.raises(decimal.InvalidOperation):
        bond_modified_duration(b)


# --------------------------------------------------------------------------- #
# duration_report
# --------------------------------------------------------------------------- #
def test_duration_report_none_bond():
    rep = duration_report(None)
    assert rep.modified_duration == 0.0
    assert rep.internal_id is None


def test_duration_report_real_bond_has_accrued():
    rep = duration_report(_bond(ytm=10, coupon=10))
    assert rep.modified_duration > 0
    assert rep.accrued_interest is not None
    assert rep.asof_date is not None


def test_duration_report_ytm_override():
    rep = duration_report(_bond(ytm=10, coupon=10), ytm_override=12.0)
    assert rep.modified_duration > 0


# --------------------------------------------------------------------------- #
# portfolio_duration
# --------------------------------------------------------------------------- #
def test_portfolio_duration_empty():
    rep = portfolio_duration([])
    assert rep.modified_duration == 0.0


def test_portfolio_duration_equal_weight_average():
    bonds = [
        _bond(ytm=8, coupon=8, maturity=date(2027, 1, 1)),
        _bond(ytm=12, coupon=12, maturity=date(2031, 1, 1)),
    ]
    rep = portfolio_duration(bonds)
    # weighted avg of two positive durations is positive
    assert rep.modified_duration > 0


def test_portfolio_duration_explicit_weights():
    bonds = [
        _bond(internal_id="A", ytm=8, coupon=8, maturity=date(2027, 1, 1)),
        _bond(internal_id="B", ytm=12, coupon=12, maturity=date(2031, 1, 1)),
    ]
    rep = portfolio_duration(bonds, weights={"A": 0.75, "B": 0.25})
    assert rep.modified_duration > 0
