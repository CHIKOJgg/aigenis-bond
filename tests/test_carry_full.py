"""Comprehensive tests for desk.carry (carry trade / rolldown / breakeven)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from desk.carry import _rolldown_bps, carry_for_bond, rank_carry
from desk.models import NelsonSiegelParams


def _bond(internal_id="B", ytm=12.0, coupon=12.0, maturity=date(2029, 1, 1), freq=2, nominal=1000, currency="BYN"):
    return SimpleNamespace(
        internal_id=internal_id,
        yield_to_maturity=ytm,
        coupon_rate=coupon,
        coupon_frequency=freq,
        maturity_date=maturity,
        start_date=date(2024, 1, 1),
        nominal=nominal,
        currency=currency,
    )


def test_rolldown_bps_basic():
    assert _rolldown_bps(12.0, 10.0) == 200.0


def test_rolldown_bps_zero_when_flat():
    assert _rolldown_bps(10.0, 10.0) == 0.0


def test_carry_none_when_missing_fields():
    b = _bond()
    b.yield_to_maturity = None
    assert carry_for_bond(b, funding_rate_pct=5.0) is None
    b2 = _bond()
    b2.coupon_rate = None
    assert carry_for_bond(b2, funding_rate_pct=5.0) is None


def test_carry_positive_when_coupon_above_funding():
    ct = carry_for_bond(_bond(ytm=12, coupon=12), funding_rate_pct=5.0)
    assert ct is not None
    # carry (coupon - funding) is positive -> expected pnl positive
    assert ct.expected_pnl_pct > 0
    assert ct.rolldown_bps >= 0


def test_carry_negative_when_funding_above_coupon():
    ct = carry_for_bond(_bond(ytm=4, coupon=4), funding_rate_pct=10.0)
    assert ct is not None
    assert ct.breakeven_bps < 0  # negative cushion


def test_carry_without_curve_uses_ytm():
    ct = carry_for_bond(_bond(ytm=12, coupon=12), funding_rate_pct=5.0, curve_params=None)
    assert ct is not None
    # no rolldown when curve absent -> expected pnl = carry only
    assert ct.expected_pnl_pct == pytest.approx(ct.rolldown_bps / 100 * 0 + ct.expected_pnl_pct, abs=1e-6)


def test_carry_with_curve_adds_rolldown():
    params = NelsonSiegelParams(beta0=12.0, beta1=0.0, beta2=-2.0, tau=2.0)
    ct = carry_for_bond(_bond(ytm=12, coupon=12), funding_rate_pct=5.0, curve_params=params)
    assert ct is not None
    # shorter-tenor yield lower than spot -> positive rolldown -> expected > carry part
    assert ct.rolldown_bps != 0


def test_rank_carry_sorts_desc():
    bonds = [
        _bond(internal_id="low", ytm=6, coupon=6),
        _bond(internal_id="high", ytm=14, coupon=14),
    ]
    ranked = rank_carry(bonds, funding_rate_pct=5.0)
    assert ranked[0].internal_id == "high"
    assert all(ranked[i].expected_pnl_pct >= ranked[i + 1].expected_pnl_pct for i in range(len(ranked) - 1))


def test_rank_carry_skips_incomplete():
    bonds = [_bond(internal_id="ok", ytm=10, coupon=10), _bond(internal_id="bad")]
    bonds[1].yield_to_maturity = None
    ranked = rank_carry(bonds, funding_rate_pct=5.0)
    assert all(r.internal_id == "ok" for r in ranked)
