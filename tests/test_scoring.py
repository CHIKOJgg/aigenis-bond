"""Тесты scoring: формулы Reward/Risk Score."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from scoring.engine import score_bond, score_bonds


def test_score_basic_usd_high_ytm() -> None:
    s = score_bond(
        internal_id="OP-1",
        yield_to_maturity=Decimal("10"),
        currency="USD",
        maturity_date=date(2028, 6, 15),
        status="active",
        issuer="Министерство финансов",
        price=Decimal("98"),
    )
    assert s.score >= 70
    assert s.breakdown.currency_component == 25
    assert s.breakdown.metal_component == 0
    assert s.score == s.breakdown.total()


def test_score_metal_bonus() -> None:
    s = score_bond(
        internal_id="GOLD-1",
        yield_to_maturity=Decimal("3"),
        currency="XAU",
        maturity_date=date(2030, 1, 1),
        status="active",
    )
    assert s.breakdown.metal_component == 10
    assert s.breakdown.currency_component == 20


def test_score_long_duration_penalty() -> None:
    s = score_bond(
        internal_id="LONG-1",
        yield_to_maturity=Decimal("5"),
        currency="USD",
        maturity_date=date(2040, 1, 1),
        status="active",
    )
    assert s.breakdown.duration_component == -15


def test_score_delisted_penalty() -> None:
    s = score_bond(
        internal_id="DEL-1",
        yield_to_maturity=Decimal("8"),
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="delisted",
    )
    assert s.breakdown.credit_risk_component <= -10


def test_score_byn_inflation_penalty_when_low_ytm() -> None:
    s = score_bond(
        internal_id="BY-1",
        yield_to_maturity=Decimal("3"),
        currency="BYN",
        maturity_date=date(2028, 1, 1),
        status="active",
    )
    assert s.breakdown.inflation_component == -5


def test_score_byn_inflation_bonus_when_high_ytm() -> None:
    s = score_bond(
        internal_id="BY-2",
        yield_to_maturity=Decimal("12"),
        currency="BYN",
        maturity_date=date(2028, 1, 1),
        status="active",
    )
    assert s.breakdown.inflation_component == 2


def test_score_bonds_bulk() -> None:
    items = [
        {
            "internal_id": "A",
            "yield_to_maturity": 5,
            "currency": "USD",
            "maturity_date": date(2028, 1, 1),
            "status": "active",
        },
        {
            "internal_id": "B",
            "yield_to_maturity": 7,
            "currency": "BYN",
            "maturity_date": date(2030, 1, 1),
            "status": "active",
        },
        {
            "internal_id": "C",
            "yield_to_maturity": 2,
            "currency": "XAU",
            "maturity_date": date(2026, 1, 1),
            "status": "active",
        },
    ]
    scored = score_bonds(items)
    assert len(scored) == 3
    assert all(s.computed_at is not None for s in scored)
