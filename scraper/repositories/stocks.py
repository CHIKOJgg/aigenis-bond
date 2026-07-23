"""Репозиторий для работы с акциями MOEX."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.models import Stock, StockHistory
from scraper.orm import StockHistoryORM, StockORM


def _stock_to_orm(stock: Stock) -> dict:
    return {
        "internal_id": stock.internal_id,
        "secid": stock.secid,
        "name": stock.name,
        "isin": stock.isin,
        "issuer": stock.issuer,
        "board": stock.board,
        "currency": stock.currency,
        "lot_size": stock.lot_size,
        "prev_price": stock.prev_price,
        "price": stock.price,
        "open_price": stock.open_price,
        "high_price": stock.high_price,
        "low_price": stock.low_price,
        "close_price": stock.close_price,
        "volume": stock.volume,
        "value_traded": stock.value_traded,
        "market_capitalization": stock.market_capitalization,
        "pe_ratio": stock.pe_ratio,
        "pbr_ratio": stock.pbr_ratio,
        "dividend_yield": stock.dividend_yield,
        "earnings_per_share": stock.earnings_per_share,
        "sector": stock.sector,
        "status": stock.status,
        "raw": stock.raw,
        "fetched_at": stock.fetched_at,
    }


async def upsert_stock(session: AsyncSession, stock: Stock) -> None:
    values = _stock_to_orm(stock)
    stmt = pg_insert(StockORM).values(**values)
    update_cols = {c: stmt.excluded[c] for c in values if c not in {"internal_id"}}
    stmt = stmt.on_conflict_do_update(
        index_elements=[StockORM.internal_id], set_=update_cols
    )
    await session.execute(stmt)


async def upsert_stocks_batch(session: AsyncSession, stocks: Iterable[Stock]) -> int:
    rows = [_stock_to_orm(s) for s in stocks]
    if not rows:
        return 0
    stmt = pg_insert(StockORM).values(rows)
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in {"internal_id"}}
    stmt = stmt.on_conflict_do_update(
        index_elements=[StockORM.internal_id], set_=update_cols
    )
    await session.execute(stmt)
    return len(rows)


async def get_all_stock_internal_ids(session: AsyncSession) -> Sequence[str]:
    result = await session.execute(select(StockORM.internal_id))
    return result.scalars().all()


async def get_stocks_by_board(session: AsyncSession, board: str) -> Sequence[StockORM]:
    result = await session.execute(
        select(StockORM)
        .where(StockORM.board == board)
        .order_by(StockORM.value_traded.desc())
    )
    return result.scalars().all()


async def get_stock_by_internal_id(
    session: AsyncSession, internal_id: str
) -> StockORM | None:
    result = await session.execute(
        select(StockORM).where(StockORM.internal_id == internal_id)
    )
    return result.scalar_one_or_none()


async def count_stocks(session: AsyncSession) -> int:
    result = await session.execute(select(sa_func.count(StockORM.internal_id)))
    return int(result.scalar_one())


async def latest_stock_fetched_at(session: AsyncSession):
    result = await session.execute(select(sa_func.max(StockORM.fetched_at)))
    return result.scalar_one_or_none()


def _history_to_orm(row: StockHistory) -> dict:
    return {
        "internal_id": row.internal_id,
        "date": row.date,
        "open_price": row.open_price,
        "high_price": row.high_price,
        "low_price": row.low_price,
        "close_price": row.close_price,
        "volume": row.volume,
        "value_traded": row.value_traded,
        "weighted_avg_price": row.weighted_avg_price,
        "status": row.status,
    }


async def upsert_stock_history_batch(
    session: AsyncSession, rows: Iterable[StockHistory]
) -> int:
    payload = [_history_to_orm(r) for r in rows]
    if not payload:
        return 0
    stmt = pg_insert(StockHistoryORM).values(payload)
    update_cols = {c: stmt.excluded[c] for c in payload[0] if c not in {"internal_id", "date"}}
    stmt = stmt.on_conflict_do_update(
        index_elements=[StockHistoryORM.internal_id, StockHistoryORM.date],
        set_=update_cols,
    )
    await session.execute(stmt)
    return len(payload)


async def last_stock_history_date(session: AsyncSession, internal_id: str) -> date | None:
    result = await session.execute(
        select(StockHistoryORM.date)
        .where(StockHistoryORM.internal_id == internal_id)
        .order_by(StockHistoryORM.date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def count_stock_history(session: AsyncSession) -> int:
    result = await session.execute(select(sa_func.count(StockHistoryORM.internal_id)))
    return int(result.scalar_one())
