from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.db import upsert_row
from scraper.models import BondDailyAccrual, BondHistory
from scraper.orm import BondDailyAccrualORM, BondHistoryORM


def _to_orm(row: BondHistory) -> dict:
    return {
        "internal_id": row.internal_id,
        "date": row.date,
        "price": row.price,
        "yield": row.yield_,
        "coupon": row.coupon,
        "status": row.status,
    }


async def upsert_history_batch(session: AsyncSession, rows: Iterable[BondHistory]) -> int:
    payload = [_to_orm(r) for r in rows]
    if not payload:
        return 0
    for values in payload:
        await upsert_row(
            session,
            BondHistoryORM,
            index_elements=["internal_id", "date"],
            values=values,
        )
    return len(payload)


async def last_history_date(session: AsyncSession, internal_id: str) -> date | None:
    result = await session.execute(
        select(BondHistoryORM.date)
        .where(BondHistoryORM.internal_id == internal_id)
        .order_by(BondHistoryORM.date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def bond_history_since(
    session: AsyncSession, internal_id: str, cutoff: date
) -> list[BondHistoryORM]:
    """Ascending price/yield history rows from ``cutoff`` (inclusive)."""
    result = await session.execute(
        select(BondHistoryORM)
        .where(BondHistoryORM.internal_id == internal_id)
        .where(BondHistoryORM.date >= cutoff)
        .order_by(BondHistoryORM.date)
    )
    return list(result.scalars().all())


async def count_history(session: AsyncSession) -> int:
    from sqlalchemy import func as sa_func

    result = await session.execute(select(sa_func.count(BondHistoryORM.internal_id)))
    return int(result.scalar_one())


def _accrual_to_orm(row: BondDailyAccrual) -> dict:
    return {
        "internal_id": row.internal_id,
        "date": row.date,
        "accrued": row.accrued,
        "total_value": row.total_value,
    }


async def upsert_accruals_batch(session: AsyncSession, rows: Iterable[BondDailyAccrual]) -> int:
    payload = [_accrual_to_orm(r) for r in rows]
    if not payload:
        return 0
    for values in payload:
        await upsert_row(
            session,
            BondDailyAccrualORM,
            index_elements=["internal_id", "date"],
            values=values,
        )
    return len(payload)


async def last_accrual_date(session: AsyncSession, internal_id: str) -> date | None:
    result = await session.execute(
        select(BondDailyAccrualORM.date)
        .where(BondDailyAccrualORM.internal_id == internal_id)
        .order_by(BondDailyAccrualORM.date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
