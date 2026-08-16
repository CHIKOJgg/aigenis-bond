"""Comprehensive tests for desk.stress (rate/credit/FX shock P&L engine)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from desk.models import StressScenario
from desk.stress import _bucket_tenor, run_all_presets, run_stress


def _bond(internal_id, ytm=10.0, price=100.0, currency="BYN", is_gov=False,
          maturity=date(2028, 1, 1)):
    return SimpleNamespace(
        internal_id=internal_id,
        yield_to_maturity=ytm,
        price=price,
        currency=currency,
        is_government=is_gov,
        coupon_rate=10.0,
        coupon_frequency=2,
        start_date=date(2024, 1, 1),
        maturity_date=maturity,
    )


def _scn(kind, **kw):
    return StressScenario(kind=kind, name="test", description="test", **kw)


def test_bucket_tenor_boundaries():
    assert _bucket_tenor(0.5) == "1Y"
    assert _bucket_tenor(1.0) == "1Y"
    assert _bucket_tenor(3.0) == "5Y"
    assert _bucket_tenor(5.0) == "5Y"
    assert _bucket_tenor(10.0) == "10Y"
    assert _bucket_tenor(20.0) == "30Y"


def test_parallel_up_shock_loses_value():
    scn = _scn("parallel", rate_shocks={"1Y": 1.0, "5Y": 1.0, "10Y": 1.0, "30Y": 1.0})
    res = run_stress(scn, [(_bond("A"), Decimal("1000"))], base_currency="BYN", asof=date(2024, 1, 1))
    assert res.pnl < 0
    assert res.pnl_pct < 0


def test_parallel_down_shock_gains_value():
    scn = _scn("parallel", rate_shocks={"1Y": -1.0, "5Y": -1.0, "10Y": -1.0, "30Y": -1.0})
    res = run_stress(scn, [(_bond("A"), Decimal("1000"))], base_currency="BYN", asof=date(2024, 1, 1))
    assert res.pnl > 0


def test_credit_shock_spares_government():
    scn = _scn("credit_shock", credit_spread_shock_bps=150.0)
    res = run_stress(scn, [(_bond("GOV", is_gov=True), Decimal("1000"))],
                     base_currency="BYN", asof=date(2024, 1, 1))
    assert res.pnl == Decimal("0.00")


def test_credit_shock_hits_corporate():
    scn = _scn("credit_shock", credit_spread_shock_bps=150.0)
    res = run_stress(scn, [(_bond("CORP", is_gov=False), Decimal("1000"))],
                     base_currency="BYN", asof=date(2024, 1, 1))
    assert res.pnl < 0


def test_fx_shock_usd_gains_against_byn_base():
    scn = _scn("fx_shock", fx_shock_pct=-20.0)
    res = run_stress(scn, [(_bond("USD", currency="USD"), Decimal("1000"))],
                     base_currency="BYN", asof=date(2024, 1, 1))
    # USD appreciates 1/(1-0.2) = 1.25 -> +25%
    assert res.pnl > 0
    assert res.pnl == Decimal("250.00")


def test_fx_shock_byn_base_bond_unchanged():
    scn = _scn("fx_shock", fx_shock_pct=-20.0)
    res = run_stress(scn, [(_bond("BYN", currency="BYN"), Decimal("1000"))],
                     base_currency="BYN", asof=date(2024, 1, 1))
    assert res.pnl == Decimal("0.00")


def test_fx_shock_local_loses_against_usd_base():
    scn = _scn("fx_shock", fx_shock_pct=-20.0)
    res = run_stress(scn, [(_bond("BYN", currency="BYN"), Decimal("1000"))],
                     base_currency="USD", asof=date(2024, 1, 1)
                     )
    # local currency devalues 1+(-0.2) = 0.8 -> -20%
    assert res.pnl == Decimal("-200.00")


def test_fx_shock_usd_unchanged_against_usd_base():
    scn = _scn("fx_shock", fx_shock_pct=-20.0)
    res = run_stress(scn, [(_bond("USD", currency="USD"), Decimal("1000"))],
                     base_currency="USD", asof=date(2024, 1, 1))
    assert res.pnl == Decimal("0.00")


def test_run_all_presets_returns_eight_scenarios():
    results = run_all_presets([(_bond("A"), Decimal("1000"))], base_currency="USD")
    assert len(results) == 8
    assert set(results) == {
        "parallel_+100bp", "parallel_+300bp", "parallel_-100bp",
        "steepener_+50_+150", "flattener_+150_+50", "inversion_+200_-50",
        "credit_shock_+150bp", "fx_shock_-20%",
    }


def test_run_stress_values_expired_bond_via_duration_fallback():
    scn = _scn("parallel", rate_shocks={"1Y": 1.0})
    res = run_stress(scn, [(_bond("OLD", maturity=date(2020, 1, 1)), Decimal("1000"))],
                     base_currency="BYN", asof=date(2024, 1, 1))
    # Expired bonds are not skipped by run_stress; they are valued with the
    # time-based duration fallback and recorded per position.
    assert "OLD" in res.by_position
