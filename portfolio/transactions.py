"""Transaction log repository — CRUD for portfolio buy/sell transactions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.orm import TransactionORM


async def record_transaction(
    session: AsyncSession,
    *,
    user_id: int,
    internal_id: str,
    side: str,
    amount: Decimal,
    price: Decimal,
    currency: str,
    note: str | None = None,
) -> TransactionORM:
    tx = TransactionORM(
        user_id=user_id,
        internal_id=internal_id,
        side=side,
        amount=amount,
        price=price,
        currency=currency,
        note=note,
    )
    session.add(tx)
    await session.flush()
    return tx


async def list_transactions(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[TransactionORM]:
    result = await session.execute(
        select(TransactionORM)
        .where(TransactionORM.user_id == user_id)
        .order_by(TransactionORM.executed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_bond_transactions(
    session: AsyncSession,
    user_id: int,
    internal_id: str,
) -> list[TransactionORM]:
    result = await session.execute(
        select(TransactionORM)
        .where(
            TransactionORM.user_id == user_id,
            TransactionORM.internal_id == internal_id,
        )
        .order_by(TransactionORM.executed_at)
    )
    return list(result.scalars().all())


async def total_bought_sold(
    session: AsyncSession, user_id: int, internal_id: str
) -> dict:
    """Aggregate buys and sells for a single bond."""
    result = await session.execute(
        select(
            TransactionORM.side,
            func.sum(TransactionORM.amount),
            func.count(TransactionORM.id),
        )
        .where(
            TransactionORM.user_id == user_id,
            TransactionORM.internal_id == internal_id,
        )
        .group_by(TransactionORM.side)
    )
    out = {"bought": Decimal("0"), "sold": Decimal("0"), "buy_count": 0, "sell_count": 0}
    for side, total, cnt in result.all():
        if side == "buy":
            out["bought"] = total or Decimal("0")
            out["buy_count"] = cnt
        elif side == "sell":
            out["sold"] = total or Decimal("0")
            out["sell_count"] = cnt
    return out


async def delete_transaction(session: AsyncSession, user_id: int, tx_id: int) -> bool:
    tx = await session.get(TransactionORM, tx_id)
    if tx is None or tx.user_id != user_id:
        return False
    await session.delete(tx)
    return True
