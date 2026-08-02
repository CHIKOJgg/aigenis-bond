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
    assert _currency_component("USD") == 20.0
    assert _currency_component("XAU") == 16.0
    assert _currency_component("XAG") == 12.0
    assert _currency_component("XPT") == 9.0
    assert _currency_component("BYN") == 4.0
    assert _currency_component("EUR") == 0.0
    assert _currency_component("RUB") == 0.0  # unknown currency → 0


def test_currency_component_case_insensitive():
    assert _currency_component("usd") == 20.0


def test_yield_component_bounds():
    assert _yield_component(None) == 0.0
    assert _yield_component(0) == 0.0
    assert _yield_component(-3) == 0.0
    assert _yield_component(8) == 8.0
    assert _yield_component(200) == 40.0  # capped at 40


def test_duration_component_buckets():
    assert _duration_component(1.0) == 15.0
    assert _duration_component(3.0) == 10.0
    assert _duration_component(5.0) == 0.0
    assert _duration_component(10.0) == -10.0
    assert _duration_component(None) == 0.0


def test_metal_component():
    assert _metal_component("XAU") == 5.0
    assert _metal_component("XAG") == 4.0
    assert _metal_component("XPT") == 3.0
    assert _metal_component("USD") == 0.0


def test_liquidity_component_combinations():
    # Active with price and near maturity.
    good = _liquidity_component(has_price=True, status="active", days_to_maturity=100)
    assert good == 4 + 4 + 2
    # Delisted without price (delisted is not in the offer/matured penalty set).
    bad = _liquidity_component(has_price=False, status="delisted", days_to_maturity=None)
    assert bad == 0
    # Offer status without price is penalized.
    off = _liquidity_component(has_price=False, status="offer", days_to_maturity=None)
    assert off == -4


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


def test_score_calibration_max_never_exceeds_100():
    """Theoretical maximum is exactly 100; no currency combination can exceed it."""
    from datetime import date

    perfect = score_bond(
        internal_id="MAX",
        yield_to_maturity=100.0,  # capped by _yield_component
        currency="USD",
        maturity_date=date(2027, 1, 1),
        status="active",
        issuer="Министерство финансов",
        price=100.0,
    )
    assert perfect.score <= 100.0
    assert perfect.score >= 99.99  # 40+20+15+10+0+10+5 == 100

    from scoring.engine import CURRENCY_BONUS

    for cur in CURRENCY_BONUS:
        s = score_bond(
            internal_id=f"MAX-{cur}",
            yield_to_maturity=100.0,
            currency=cur,
            maturity_date=date(2027, 1, 1),
            status="active",
            issuer="Министерство финансов",
            price=100.0,
        )
        assert s.score <= 100.0, f"{cur} exceeds 100: {s.score}"


def test_score_calibration_tiers_are_meaningful():
    """A typical good USD bond is B, not S; S requires an exceptional profile."""
    from datetime import date

    typical_good_usd = score_bond(
        internal_id="TYP",
        yield_to_maturity=15.0,
        currency="USD",
        maturity_date=date(2029, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
    )
    # 15 + 20 + 10 + 10 + 10 + 5 = 70 → B (meaningful middle of the scale).
    assert 60 <= typical_good_usd.score <= 75
    assert typical_good_usd.tier in {"B", "C"}

    exceptional = score_bond(
        internal_id="EXC",
        yield_to_maturity=35.0,
        currency="USD",
        maturity_date=date(2027, 1, 1),
        status="active",
        issuer="Министерство финансов",
        price=100.0,
    )
    # 35 + 20 + 15 + 10 + 10 + 5 = 95 → S.
    assert exceptional.tier == "S"

    weak = score_bond(
        internal_id="WK",
        yield_to_maturity=2.0,
        currency="EUR",
        maturity_date=date(2036, 1, 1),
        status="delisted",
        issuer="Some Corp",
        price=None,
    )
    # 2 + 0 - 10 + 0 + 0 - 25 - 2 → well below 60 → D.
    assert weak.tier == "D"
