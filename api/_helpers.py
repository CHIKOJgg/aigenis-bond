"""Pure helpers shared across the analytics API.

Extracted from ``api/analytics.py`` so the oversized router module stays focused
on endpoint wiring rather than carrying every helper inline.
"""

from __future__ import annotations

from decimal import Decimal

from scoring.models import UserPreferences
from scraper.models import Bond
from scraper.orm import BondORM


def orm_to_bond(b: BondORM) -> Bond:
    return Bond(
        internal_id=b.internal_id,
        name=b.name,
        currency=b.currency,
        yield_to_maturity=b.yield_to_maturity,
        coupon_rate=b.coupon_rate,
        coupon_frequency=b.coupon_frequency,
        maturity_date=b.maturity_date,
        price=b.price,
        start_date=b.start_date,
        issuer=b.issuer,
        status=b.status,
        nominal=b.nominal,
        fetched_at=b.fetched_at,
    )


def default_prefs(user_id: int) -> UserPreferences:
    return UserPreferences(
        user_id=user_id,
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("500"),
        share_usd=0.5,
        share_byn=0.3,
        share_metals=0.1,
        share_eur=0.1,
        strategy="Balanced",
        watchlist=[],
    )


def most_common(items: list[str]) -> str | None:
    if not items:
        return None
    counts: dict[str, int] = {}
    for it in items:
        counts[it] = counts.get(it, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def bond_facts(b: Bond) -> dict:
    return {
        "internal_id": b.internal_id,
        "name": b.name,
        "currency": b.currency,
        "issuer": b.issuer,
        "yield_to_maturity": float(b.yield_to_maturity) if b.yield_to_maturity else None,
        "coupon_rate": float(b.coupon_rate) if b.coupon_rate else None,
        "price": float(b.price) if b.price else None,
        "nominal": float(b.nominal) if b.nominal else None,
        "maturity_date": b.maturity_date.isoformat() if b.maturity_date else None,
        "status": b.status,
    }
