"""Tests for the demo surface's pure helper logic (no DB / network needed)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import api.demo as demo
from api.demo import (
    PortfolioImpactRequest,
    _build_impact,
    _issuer_risk_payload,
    _strategy_notes,
)


def test_strategy_order_base_returns_are_monotonic():
    bases = [demo.STRATEGY_PROFILES[s]["baseReturn"] for s in demo.STRATEGY_ORDER]
    assert bases == sorted(bases)
    # passive < aggressive
    assert demo.STRATEGY_PROFILES["Conservative"]["baseReturn"] < demo.STRATEGY_PROFILES["Maximum Reward/Risk"]["baseReturn"]


def test_guarded_expected_return_preserves_strategy_order():
    # For every portfolio YTM in a plausible range, the strategy ordering must
    # stay monotonic (passive <= balanced <= aggressive). The guard exists so a
    # high-yield portfolio never flips the ranking.
    for ytm in (6.0, 12.4, 20.0):
        vals = [demo._guarded_expected_return(s, ytm) for s in demo.STRATEGY_ORDER]
        assert vals == sorted(vals)


def test_guarded_expected_return_returns_base_for_unknown_strategy():
    assert demo._guarded_expected_return("Nonsense", 12.4) == pytest.approx(
        demo.STRATEGY_PROFILES["Balanced"]["baseReturn"]
    )


def test_issuer_risk_payload_tiers():
    # sovereign
    sov = _issuer_risk_payload("Минфин", is_government=True, credit_component=12.0, status="active")
    assert sov["level"] == "Очень низкий"
    assert sov["score"] == 90.0
    # defaulted overrides everything
    dflt = _issuer_risk_payload("X", is_government=False, credit_component=10.0, status="defaulted")
    assert dflt["score"] == 15.0
    assert dflt["level"] == "Критический"
    # negative credit component -> high risk
    neg = _issuer_risk_payload("Y Corp", is_government=False, credit_component=-5.0, status="active")
    assert neg["level"] == "Умеренный"
    assert neg["score"] == 56.0


def test_issuer_risk_payload_exposes_engine_method():
    payload = _issuer_risk_payload("Z", is_government=False, credit_component=2.0, status="active")
    assert payload["method"].startswith("Reward/Risk engine")
    assert "credit_component" in payload


def test_strategy_notes_only_for_metals_plus_plus():
    assert _strategy_notes("Metals++", [{"internal_id": "X"}])
    assert _strategy_notes("Balanced", []) == []


def test_build_impact_known_bond_returns_response():
    resp = _build_impact(
        PortfolioImpactRequest(bond_id="demo-bond-001", allocation_pct=10)
    )
    assert resp.bond_id == "demo-bond-001"
    assert resp.allocation_pct == 10
    # before/after yields bracket the portfolio benchmark; after >= before when
    # the bond yield is above the benchmark.
    assert resp.before.expected_yield_pct > 0
    # adding a bond increases its issuer concentration
    issuer_key = resp.after.concentration_by_issuer
    assert any(v > 0 for v in issuer_key.values())


def test_build_impact_unknown_bond_raises_404():
    with pytest.raises(HTTPException) as exc:
        _build_impact(PortfolioImpactRequest(bond_id="does-not-exist", allocation_pct=10))
    assert exc.value.status_code == 404


def test_build_impact_allocations_limited_to_5_10_15():
    # boundary allocations produce valid responses
    for pct in (5, 10, 15):
        resp = _build_impact(PortfolioImpactRequest(bond_id="demo-bond-001", allocation_pct=pct))
        assert resp.allocation_pct == pct
