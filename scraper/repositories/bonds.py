from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.models import Bond
from scraper.orm import BondORM


def _bond_to_orm(bond: Bond) -> dict:
    return {
        "internal_id": bond.internal_id,
        "isin": bond.isin,
        "name": bond.name,
        "issuer": bond.issuer,
        "currency": bond.currency,
        "nominal": bond.nominal,
        "coupon_rate": bond.coupon_rate,
        "coupon_frequency": bond.coupon_frequency,
        "maturity_date": bond.maturity_date,
        "price": bond.price,
        "yield_to_maturity": bond.yield_to_maturity,
        "amortization": bond.amortization,
        "offer_date": bond.offer_date,
        "start_date": bond.start_date,
        "end_date": bond.end_date,
        "registration_number": bond.registration_number,
        "issue_volume": bond.issue_volume,
        "issue_number": bond.issue_number,
        "income_method": bond.income_method,
        "in_stock": bond.in_stock,
        "guarantor": bond.guarantor,
        "maturity_term_text": bond.maturity_term_text,
        "coupon_description": bond.coupon_description,
        "coupon_schedule": bond.coupon_schedule,
        "indexation_currency": bond.indexation_currency,
        "exchange_rate_on_start": bond.exchange_rate_on_start,
        "term_days": bond.term_days,
        "quantity": bond.quantity,
        "status": bond.status,
        "raw": bond.raw,
        "fetched_at": bond.fetched_at,
    }


async def upsert_bond(session: AsyncSession, bond: Bond) -> None:
    values = _bond_to_orm(bond)
    stmt = pg_insert(BondORM).values(**values)
    update_cols = {c: stmt.excluded[c] for c in values if c not in {"internal_id"}}
    stmt = stmt.on_conflict_do_update(index_elements=[BondORM.internal_id], set_=update_cols)
    await session.execute(stmt)


async def upsert_bonds_batch(session: AsyncSession, bonds: Iterable[Bond]) -> int:
    rows = [_bond_to_orm(b) for b in bonds]
    if not rows:
        return 0
    stmt = pg_insert(BondORM).values(rows)
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in {"internal_id"}}
    stmt = stmt.on_conflict_do_update(index_elements=[BondORM.internal_id], set_=update_cols)
    await session.execute(stmt)
    return len(rows)


async def get_all_internal_ids(session: AsyncSession) -> Sequence[str]:
    result = await session.execute(select(BondORM.internal_id))
    return result.scalars().all()


async def exists(session: AsyncSession, internal_id: str) -> bool:
    result = await session.execute(
        select(BondORM.internal_id).where(BondORM.internal_id == internal_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def get_by_currency(session: AsyncSession, currency: str) -> Sequence[BondORM]:
    result = await session.execute(
        select(BondORM).where(BondORM.currency == currency).order_by(BondORM.yield_to_maturity.desc())
    )
    return result.scalars().all()


async def count_bonds(session: AsyncSession) -> int:
    from sqlalchemy import func as sa_func

    result = await session.execute(select(sa_func.count(BondORM.internal_id)))
    return int(result.scalar_one())


async def latest_fetched_at(session: AsyncSession):
    from sqlalchemy import func as sa_func

    result = await session.execute(select(sa_func.max(BondORM.fetched_at)))
    return result.scalar_one_or_none()
