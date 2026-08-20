"""Comprehensive tests for portfolio.scenarios (USD/BYN scenario engine)."""

from __future__ import annotations

from decimal import Decimal

from portfolio.scenarios import run_all_scenarios, run_scenario


def test_bull_usd_strengthens_byn_value():
    res = run_scenario("Bull USD", current_usd_byn=Decimal("3.0"), usd_share=0.6, byn_share=0.4)
    assert res.fx_change_pct == 15.0
    assert res.usd_byn_end == Decimal("3.4500")
    # USD up 15%, BYN down 15% -> net = (0.6 - 0.4)*15% = 3%
    assert res.portfolio_value_change_pct == pytest.approx(3.0, abs=1e-6)


def test_neutral_no_change():
    res = run_scenario("Neutral", current_usd_byn=Decimal("3.0"), usd_share=0.5, byn_share=0.5)
    assert res.fx_change_pct == 0.0
    assert res.portfolio_value_change_pct == 0.0
    assert res.worst_position is None


def test_bull_byn_weakens_usd_value():
    res = run_scenario("Bull BYN", current_usd_byn=Decimal("3.0"), usd_share=0.5, byn_share=0.5)
    assert res.fx_change_pct == -10.0
    # BYN up 10% (USD down 10%): 0.5*(-0.10) + 0.5*(+0.10) = 0
    assert res.portfolio_value_change_pct == pytest.approx(0.0, abs=1e-6)


def test_stress_reduces_value():
    res = run_scenario("Stress", current_usd_byn=Decimal("3.0"), usd_share=0.8, byn_share=0.2)
    # USD down 30%: 0.8*(-0.30) + 0.2*(+0.30) = -0.24 + 0.06 = -0.18
    assert res.portfolio_value_change_pct == pytest.approx(-18.0, abs=1e-6)
    assert "Стресс" in res.notes[0]


def test_metals_and_eur_impact():
    res = run_scenario(
        "Bull USD",
        current_usd_byn=Decimal("3.0"),
        usd_share=0.0,
        byn_share=0.0,
        metals_share=1.0,
        eur_share=1.0,
    )
    # metals +0.3*0.15, eur +0.8*0.15
    assert res.portfolio_value_change_pct == pytest.approx((0.3 + 0.8) * 15.0, abs=1e-6)


def test_run_all_scenarios_four():
    results = run_all_scenarios(current_usd_byn=Decimal("3.0"), usd_share=0.5, byn_share=0.5)
    names = {r.scenario for r in results}
    assert names == {"Bull USD", "Neutral", "Bull BYN", "Stress"}


import pytest  # noqa: E402
