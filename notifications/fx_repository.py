"""Репозитории для FX и металлов."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.orm import FxRateORM, MetalPriceORM


async def upsert_fx(session: AsyncSession, pair: str, rate: Decimal) -> None:
    obj = FxRateORM(pair=pair, rate=rate)
    session.add(obj)


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
    obj = MetalPriceORM(metal=metal, price=price)
    session.add(obj)


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
