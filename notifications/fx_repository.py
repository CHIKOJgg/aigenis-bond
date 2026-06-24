"""Репозитории для FX и металлов."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.orm import FxRateORM, MetalPriceORM


async def upsert_fx(session: AsyncSession, pair: str, rate: Decimal) -> None:
    stmt = pg_insert(FxRateORM).values(pair=pair, rate=rate)
    await session.execute(stmt)


async def latest_fx(session: AsyncSession, pair: str) -> FxRateORM | None:
    result = await session.execute(
        select(FxRateORM)
        .where(FxRateORM.pair == pair)
        .order_by(FxRateORM.observed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def latest_metal(session: AsyncSession, metal: str) -> MetalPriceORM | None:
    result = await session.execute(
        select(MetalPriceORM)
        .where(MetalPriceORM.metal == metal)
        .order_by(MetalPriceORM.observed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def upsert_metal(session: AsyncSession, metal: str, price: Decimal) -> None:
    stmt = pg_insert(MetalPriceORM).values(metal=metal, price=price)
    await session.execute(stmt)


async def previous_metal(session: AsyncSession, metal: str) -> MetalPriceORM | None:
    result = await session.execute(
        select(MetalPriceORM)
        .where(MetalPriceORM.metal == metal)
        .order_by(MetalPriceORM.observed_at.desc())
        .offset(1)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def previous_fx(session: AsyncSession, pair: str) -> FxRateORM | None:
    result = await session.execute(
        select(FxRateORM)
        .where(FxRateORM.pair == pair)
        .order_by(FxRateORM.observed_at.desc())
        .offset(1)
        .limit(1)
    )
    return result.scalar_one_or_none()
