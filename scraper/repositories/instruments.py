"""Asset-class-agnostic instrument read models (bonds + MOEX stocks).

Used by watchlist / alerts / search so callers can treat any instrument
(bond or equity) through one small surface: ``InstrumentSummary`` and
``instrument_summary()`` / ``search_instruments()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.models import AssetClass
from scraper.orm import BondORM, StockORM


@dataclass(slots=True)
class InstrumentSummary:
    internal_id: str
    asset_class: AssetClass
    name: str
    currency: str
    price: Decimal | None = None
    headline: str | None = None
    market: str | None = None
    status: str = "unknown"
    fetched_at: datetime | None = None


def _from_bond(b: BondORM) -> InstrumentSummary:
    return InstrumentSummary(
        internal_id=b.internal_id,
        asset_class="bond",
        name=b.name,
        currency=b.currency,
        price=b.price,
        headline=f"Доходность {b.yield_to_maturity}%" if b.yield_to_maturity is not None else None,
        market=b.market,
        status=b.status,
        fetched_at=b.fetched_at,
    )


def _from_stock(s: StockORM) -> InstrumentSummary:
    headline = None
    if s.dividend_yield is not None:
        headline = f"Див. доходность {s.dividend_yield}%"
    elif s.pbr_ratio is not None:
        headline = f"P/B {s.pbr_ratio}"
    return InstrumentSummary(
        internal_id=s.internal_id,
        asset_class="equity",
        name=s.name,
        currency=s.currency,
        price=s.price,
        headline=headline,
        market=s.board,
        status=s.status,
        fetched_at=s.fetched_at,
    )


async def instrument_summary(session: AsyncSession, internal_id: str) -> InstrumentSummary | None:
    """Resolve a single instrument by id across bonds and stocks."""
    bond = (
        await session.execute(select(BondORM).where(BondORM.internal_id == internal_id))
    ).scalar_one_or_none()
    if bond is not None:
        return _from_bond(bond)
    stock = (
        await session.execute(select(StockORM).where(StockORM.internal_id == internal_id))
    ).scalar_one_or_none()
    if stock is not None:
        return _from_stock(stock)
    return None


async def search_instruments(
    session: AsyncSession, query: str, limit: int = 20
) -> list[InstrumentSummary]:
    """Search bonds and stocks by name / id / issuer, newest first."""
    pattern = f"%{query}%"
    bonds = (
        (
            await session.execute(
                select(BondORM)
                .where(
                    (BondORM.name.ilike(pattern))
                    | (BondORM.internal_id.ilike(pattern))
                    | (BondORM.issuer.ilike(pattern))
                )
                .order_by(BondORM.fetched_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if len(bonds) >= limit:
        return [_from_bond(b) for b in bonds]
    stocks = (
        (
            await session.execute(
                select(StockORM)
                .where(
                    (StockORM.name.ilike(pattern))
                    | (StockORM.internal_id.ilike(pattern))
                    | (StockORM.secid.ilike(pattern))
                    | (StockORM.issuer.ilike(pattern))
                )
                .order_by(StockORM.fetched_at.desc())
                .limit(limit - len(bonds))
            )
        )
        .scalars()
        .all()
    )
    merged = [_from_bond(b) for b in bonds] + [_from_stock(s) for s in stocks]
    merged.sort(key=lambda x: x.fetched_at or datetime.min, reverse=True)
    return merged[:limit]
