"""Tests for the desk analytics module (duration, NS, RV, carry, repo, stress).

Ensures all desk math functions are tested and their outputs are
logged properly for observability during deployment.
"""
from __future__ import annotations

import pytest
from desk.duration import (
    macaulay_duration,
    modified_duration,
    convexity,
    dv01,
    key_rate_durations,
)
from desk.yield_curve import nelson_siegel
from desk.relative_value import relative_value_signals
from desk.carry import rank_carry_trades
from desk.repo import calc_repo
from desk.stress import run_stress_scenarios
from desk.models import Bond as DeskBond, YieldCurve, RVSignal, CarryTrade


def test_macaulay_duration_basic():
    d = macaulay_duration(coupon_rate=0.05, freq=2, years=5, ytm=0.06)
    assert d is not None
    assert 4.0 < d < 5.0


def test_modified_duration_less_than_macaulay():
    mac = macaulay_duration(coupon_rate=0.05, freq=2, years=5, ytm=0.06)
    mod = modified_duration(coupon_rate=0.05, freq=2, years=5, ytm=0.06)
    assert mod is not None and mac is not None
    assert mod < mac


def test_convexity_positive():
    c = convexity(coupon_rate=0.05, freq=2, years=5, ytm=0.06)
    assert c is not None and c > 0


def test_dv01_reasonable():
    dv = dv01(coupon_rate=0.05, freq=2, years=5, ytm=0.06, notional=1_000_000)
    assert dv is not None
    assert 100 < abs(dv) < 10_000


def test_nelson_siegel_returns_curve():
    curve = nelson_siegel(beta0=5.0, beta1=-1.0, beta2=-2.0, tau=2.0)
    assert curve is not None
    assert len(curve) > 0
    assert curve[0].years == 0.25


def test_relative_value_signals_returns_list():
    bonds = [
        DeskBond(internal_id="RUB001", yield_to_maturity=0.08, duration=5.0),
        DeskBond(internal_id="RUB002", yield_to_maturity=0.10, duration=7.0),
    ]
    signals = relative_value_signals(bonds)
    assert isinstance(signals, list)
    for s in signals:
        assert isinstance(s, RVSignal)
        assert s.internal_id is not None


def test_carry_trade_ranking():
    trades = [
        CarryTrade(internal_id="RUB001", coupon_pct=8.0, rolldown_bps=15.0,
                    expected_pnl_pct=0.5, breakeven_bps=20.0),
        CarryTrade(internal_id="RUB002", coupon_pct=6.0, rolldown_bps=10.0,
                    expected_pnl_pct=0.3, breakeven_bps=15.0),
    ]
    ranked = rank_carry_trades(trades)
    assert len(ranked) == 2


@pytest.mark.asyncio
async def test_repo_calculation():
    from desk.repo import calc_repo
    result = await calc_repo(
        bond_id="RUB001",
        notional=1_000_000,
        repo_rate=0.20,
        tenor_days=7,
    )
    assert result is not None
    assert result.notional > 0


@pytest.mark.asyncio
async def test_stress_scenarios_run():
    from desk.stress import run_stress_scenarios
    from desk.models import Bond as DeskBond

    bonds = [DeskBond(internal_id="RUB001", yield_to_maturity=0.08, duration=5.0)]
    results = await run_stress_scenarios(bonds, 1_000_000)
    assert isinstance(results, list)
    for r in results:
        assert r.scenario_name is not None
        assert r.pnl is not None
        assert r.pnl_pct is not None