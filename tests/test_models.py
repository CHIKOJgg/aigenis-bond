"""Тесты моделей."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from scraper.models import Bond, BondHistory


def test_bond_basic_normalization() -> None:
    bond = Bond(
        internal_id="OP-51",
        name="ОП-51",
        currency="usd",
        nominal="1000",
        coupon_rate="5,25%",
        price="98.5",
        maturity_date="2030-06-15",
        fetched_at=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert bond.currency == "USD"
    assert bond.nominal == Decimal("1000")
    assert bond.coupon_rate == Decimal("5.25")
    assert bond.price == Decimal("98.5")
    assert bond.maturity_date == date(2030, 6, 15)


def test_bond_currency_russian_aliases() -> None:
    for raw, expected in (
        ("доллар", "USD"),
        ("белорусский рубль", "BYN"),
        ("евро", "EUR"),
        ("золото", "XAU"),
    ):
        bond = Bond(
            internal_id="X",
            name="X",
            currency=raw,
            fetched_at=datetime.now(UTC),
        )
        assert bond.currency == expected


def test_bond_status_normalization() -> None:
    bond = Bond(
        internal_id="X",
        name="X",
        currency="USD",
        status="в обращении",
        fetched_at=datetime.now(UTC),
    )
    assert bond.status == "active"


def test_history_alias_yield() -> None:
    h = BondHistory.model_validate(
        {
            "internal_id": "OP-51",
            "date": "2026-06-01",
            "price": "98.0",
            "yield": "5.5",
            "coupon": "5.25",
        }
    )
    assert h.yield_ == Decimal("5.5")
    assert h.date == date(2026, 6, 1)
