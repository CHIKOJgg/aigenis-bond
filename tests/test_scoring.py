"""Unit tests for the Reward/Risk scoring engine (scoring/engine.py)."""
from __future__ import annotations

from datetime import date

from scoring.engine import (
    _credit_risk_component,
    _currency_component,
    _duration_component,
    _inflation_component,
    _liquidity_component,
    _metal_component,
    _yield_component,
    score_bond,
    score_bonds,
)
from scoring.models import BondScore


def test_currency_component_known_values():
    assert _currency_component("USD") == 25.0
    assert _currency_component("XAU") == 20.0
    assert _currency_component("XAG") == 15.0
    assert _currency_component("XPT") == 12.0
    assert _currency_component("BYN") == 5.0
    assert _currency_component("EUR") == 0.0
    assert _currency_component("RUB") == 0.0  # unknown currency → 0


def test_currency_component_case_insensitive():
    assert _currency_component("usd") == 25.0


def test_yield_component_bounds():
    assert _yield_component(None) == 0.0
    assert _yield_component(0) == 0.0
    assert _yield_component(-3) == 0.0
    assert _yield_component(8) == 8.0
    assert _yield_component(200) == 60.0  # capped at 60


def test_duration_component_buckets():
    assert _duration_component(1.0) == 20.0
    assert _duration_component(3.0) == 10.0
    assert _duration_component(5.0) == 0.0
    assert _duration_component(10.0) == -15.0
    assert _duration_component(None) == 0.0


def test_metal_component():
    assert _metal_component("XAU") == 10.0
    assert _metal_component("XAG") == 5.0
    assert _metal_component("XPT") == 3.0
    assert _metal_component("USD") == 0.0


def test_liquidity_component_combinations():
    # Active with price and near maturity.
    good = _liquidity_component(has_price=True, status="active", days_to_maturity=100)
    assert good == 5 + 5 + 2
    # Delisted without price (delisted is not in the offer/matured penalty set).
    bad = _liquidity_component(has_price=False, status="delisted", days_to_maturity=None)
    assert bad == 0
    # Offer status without price is penalized.
    off = _liquidity_component(has_price=False, status="offer", days_to_maturity=None)
    assert off == -5


def test_credit_risk_component():
    assert _credit_risk_component("Министерство финансов", "active") == 10.0
    assert _credit_risk_component("Acme Bank", "active") == 0.0
    assert _credit_risk_component("Acme Corp", "active") == -5.0
    assert _credit_risk_component(None, "active") == -3.0
    assert _credit_risk_component("Any", "delisted") == -25.0
    assert _credit_risk_component("Any", "matured") == -10.0


def test_inflation_component():
    assert _inflation_component("USD", 5) == 5.0
    assert _inflation_component("BYN", 9) == 2.0
    assert _inflation_component("BYN", 5) == -5.0
    assert _inflation_component("EUR", 5) == -2.0
    assert _inflation_component("XAU", 5) == 0.0


def test_score_bond_basic_and_tier():
    s: BondScore = score_bond(
        internal_id="OP-1",
        yield_to_maturity=12.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Ministry of Finance",
        price=100.0,
    )
    assert s.score > 0
    assert s.tier in {"S", "A", "B", "C", "D"}
    assert s.breakdown.total() == s.score


def test_score_bond_tier_boundaries():
    # Low-yield, long, non-gov, non-metal → low score → tier D.
    low = score_bond(
        internal_id="L",
        yield_to_maturity=1.0,
        currency="EUR",
        maturity_date=date(2035, 1, 1),
        status="active",
        issuer="Some Corp",
        price=100.0,
    )
    assert low.tier == "D"

    # High-yield gov USD short → very high score → top tiers.
    high = score_bond(
        internal_id="H",
        yield_to_maturity=60.0,
        currency="USD",
        maturity_date=date(2027, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
    )
    assert high.tier in {"S", "A", "B"}


def test_score_bonds_batch():
    out = score_bonds(
        [
            {"internal_id": "A", "yield_to_maturity": 10.0, "currency": "USD", "status": "active"},
            {"internal_id": "B", "yield_to_maturity": 5.0, "currency": "BYN", "status": "active"},
        ]
    )
    assert [b.internal_id for b in out] == ["A", "B"]
    assert all(isinstance(b, BondScore) for b in out)
