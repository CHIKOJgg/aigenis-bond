"""Comprehensive tests for desk.spreads and desk.yield_curve (NS fit, Z/G spread)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from desk.models import NelsonSiegelParams
from desk.spreads import compute_spreads, solve_flat_yield
from desk.yield_curve import (
    _ns_rate,
    curve_from_bonds,
    fit_nelson_siegel,
    interpolate,
)


# --------------------------------------------------------------------------- #
# Nelson-Siegel rate
# --------------------------------------------------------------------------- #
def test_ns_rate_at_zero_tenor():
    assert _ns_rate(0.0, 10.0, 1.0, -1.0, 2.0) == pytest.approx(11.0)


def test_ns_rate_flat_when_betas_zero():
    assert _ns_rate(5.0, 10.0, 0.0, 0.0, 2.0) == pytest.approx(10.0)


def test_ns_rate_converges_to_beta0_at_long_tenor():
    assert _ns_rate(100.0, 9.0, 2.0, -3.0, 2.0) == pytest.approx(9.0, abs=0.05)


# --------------------------------------------------------------------------- #
# fit_nelson_siegel
# --------------------------------------------------------------------------- #
def _point(tenor, rate):
    from desk.models import CurvePoint

    return CurvePoint(tenor=tenor, years={"1Y": 1.0, "2Y": 2.0, "5Y": 5.0, "10Y": 10.0}[tenor], rate_pct=rate)


def test_fit_empty_returns_zeros():
    p = fit_nelson_siegel([])
    assert p.beta0 == 0.0 and p.beta1 == 0.0 and p.beta2 == 0.0


def test_fit_single_point_flat_curve():
    p = fit_nelson_siegel([_point("5Y", 11.0)])
    assert p.beta0 == pytest.approx(11.0, abs=0.01)


def test_fit_two_points_flat_curve():
    p = fit_nelson_siegel([_point("1Y", 10.0), _point("5Y", 10.0)])
    assert p.beta0 == pytest.approx(10.0, abs=0.01)


def test_fit_three_points_recovers_shape():
    pts = [_point("1Y", 12.0), _point("5Y", 10.0), _point("10Y", 9.0)]
    p = fit_nelson_siegel(pts)
    # short end above long end => beta1 positive (y(0)=beta0+beta1 > beta0)
    assert p.beta1 > 0


def test_interpolate_unknown_tenor_raises():
    with pytest.raises(ValueError):
        interpolate(None, NelsonSiegelParams(beta0=10, beta1=0, beta2=0, tau=2), "99Y")


# --------------------------------------------------------------------------- #
# solve_flat_yield
# --------------------------------------------------------------------------- #
def test_solve_flat_yield_par_bond():
    from desk.cashflow import pricing_cashflows

    flows = pricing_cashflows(
        nominal=1000, coupon_rate_pct=10, coupon_frequency=2,
        maturity=date(2029, 1, 1), asof=date(2024, 1, 1), issue_date=date(2024, 1, 1),
    )
    # price at par (100% of 1000 = 1000) -> flat ~ 10%
    flat = solve_flat_yield(flows, 1000.0)
    assert flat is not None
    assert flat == pytest.approx(0.10, abs=0.005)


def test_solve_flat_yield_none_for_empty():
    assert solve_flat_yield([], 100.0) is None


def test_solve_flat_yield_none_for_nonpositive_price():
    assert solve_flat_yield([(1.0, 50.0)], 0.0) is None


# --------------------------------------------------------------------------- #
# compute_spreads
# --------------------------------------------------------------------------- #
def _spread_bond(internal_id="B", ytm=10.0, price=100.0, coupon=10.0, freq=2, currency="BYN", maturity=date(2029, 1, 1)):
    return SimpleNamespace(
        internal_id=internal_id,
        yield_to_maturity=ytm,
        price=price,
        coupon_rate=coupon,
        coupon_frequency=freq,
        currency=currency,
        maturity_date=maturity,
        start_date=date(2024, 1, 1),
        nominal=1000,
    )


def test_compute_spreads_fair_at_curve():
    curves = {"BYN": NelsonSiegelParams(beta0=10.0, beta1=0.0, beta2=0.0, tau=2.0)}
    reports = compute_spreads([_spread_bond(ytm=10, price=100)], curves, asof=date(2024, 1, 1))
    assert len(reports) == 1
    r = reports[0]
    assert r.g_spread_pct == pytest.approx(0.0, abs=0.1)
    assert r.side == "fair"


def test_compute_spreads_cheap_when_price_below_model():
    # Price 95 (below par) with curve at 10% -> market cheaper than model.
    curves = {"BYN": NelsonSiegelParams(beta0=10.0, beta1=0.0, beta2=0.0, tau=2.0)}
    reports = compute_spreads([_spread_bond(ytm=13, price=95)], curves, asof=date(2024, 1, 1))
    r = reports[0]
    assert r.g_spread_pct == pytest.approx(3.0, abs=0.5)
    assert r.side == "cheap"


def test_compute_spreads_rich_when_price_above_model():
    # Price 105 (above par) with curve at 14% -> market richer than model.
    curves = {"BYN": NelsonSiegelParams(beta0=14.0, beta1=0.0, beta2=0.0, tau=2.0)}
    reports = compute_spreads([_spread_bond(ytm=10, price=105)], curves, asof=date(2024, 1, 1))
    r = reports[0]
    assert r.side == "rich"


def test_compute_spreads_skips_missing_curve():
    reports = compute_spreads([_spread_bond(currency="XXX")], {"BYN": NelsonSiegelParams(beta0=10, beta1=0, beta2=0, tau=2)}, asof=date(2024, 1, 1))
    assert reports == []


def test_compute_spreads_skips_matured_bond():
    reports = compute_spreads(
        [_spread_bond(maturity=date(2020, 1, 1))],
        {"BYN": NelsonSiegelParams(beta0=10, beta1=0, beta2=0, tau=2)},
        asof=date(2024, 1, 1),
    )
    assert reports == []


def test_compute_spreads_sorted_by_abs_mispricing():
    curves = {"BYN": NelsonSiegelParams(beta0=10.0, beta1=0.0, beta2=0.0, tau=2.0)}
    bonds = [
        _spread_bond(internal_id="fair", ytm=10.2, price=100),
        _spread_bond(internal_id="cheap", ytm=14, price=95),
    ]
    reports = compute_spreads(bonds, curves, asof=date(2024, 1, 1))
    assert reports[0].internal_id == "cheap"


# --------------------------------------------------------------------------- #
# curve_from_bonds (eligibility-aware)
# --------------------------------------------------------------------------- #
def _eligible_bond(internal_id="E", ytm=10.0, price=100.0, currency="BYN", maturity=date(2029, 1, 1)):
    return SimpleNamespace(
        internal_id=internal_id,
        yield_to_maturity=ytm,
        price=price,
        coupon_rate=10,
        coupon_frequency=2,
        currency=currency,
        maturity_date=maturity,
        start_date=date(2024, 1, 1),
        nominal=1000,
        status="active",
        is_government=False,
    )


def test_curve_from_bonds_builds_points():
    bonds = [
        _eligible_bond(ytm=11, maturity=date(2025, 1, 1)),  # ~1Y
        _eligible_bond(ytm=10, maturity=date(2029, 1, 1)),  # ~5Y
    ]
    curve = curve_from_bonds(bonds)
    assert len(curve.points) >= 1
    assert all(0 < p.rate_pct < 100 for p in curve.points)


def test_curve_from_bonds_excludes_distressed():
    good = _eligible_bond(ytm=10, price=100)
    bad = _eligible_bond(ytm=50, price=70)  # distribution: price<80 & ytm>30
    curve = curve_from_bonds([good, bad])
    # distressed bond must not dominate the short bucket
    assert curve.points[0].rate_pct < 50
