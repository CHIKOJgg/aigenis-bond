from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

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
    stmt = pg_insert(BondHistoryORM).values(payload)
    update_cols = {c: stmt.excluded[c] for c in payload[0] if c not in {"internal_id", "date"}}
    stmt = stmt.on_conflict_do_update(
        index_elements=[BondHistoryORM.internal_id, BondHistoryORM.date], set_=update_cols
    )
    await session.execute(stmt)
    return len(payload)


async def last_history_date(session: AsyncSession, internal_id: str) -> date | None:
    result = await session.execute(
        select(BondHistoryORM.date)
        .where(BondHistoryORM.internal_id == internal_id)
        .order_by(BondHistoryORM.date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


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
    stmt = pg_insert(BondDailyAccrualORM).values(payload)
    update_cols = {c: stmt.excluded[c] for c in payload[0] if c not in {"internal_id", "date"}}
    stmt = stmt.on_conflict_do_update(
        index_elements=[BondDailyAccrualORM.internal_id, BondDailyAccrualORM.date], set_=update_cols
    )
    await session.execute(stmt)
    return len(payload)


async def last_accrual_date(session: AsyncSession, internal_id: str) -> date | None:
    result = await session.execute(
        select(BondDailyAccrualORM.date)
        .where(BondDailyAccrualORM.internal_id == internal_id)
        .order_by(BondDailyAccrualORM.date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
