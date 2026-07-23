"""Stock API — MOEX акции, история, аналитика.

Бесплатные эндпоинты: листинг, детали, история.
Pro-эндпоинты: секторальная аналитика, фильтры, рекомендации.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.access_control import RequireFeature
from scraper.db import session_scope
from scraper.orm import StockHistoryORM, StockORM

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"])


# --- Pydantic response models ---


class StockResponse(BaseModel):
    internal_id: str
    secid: str
    name: str
    isin: str | None = None
    issuer: str | None = None
    board: str = "TQBR"
    currency: str = "RUB"
    lot_size: int | None = None
    prev_price: float | None = None
    price: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    close_price: float | None = None
    volume: int | None = None
    value_traded: float | None = None
    market_capitalization: float | None = None
    pe_ratio: float | None = None
    pbr_ratio: float | None = None
    dividend_yield: float | None = None
    earnings_per_share: float | None = None
    sector: str | None = None
    status: str = "unknown"
    fetched_at: str | None = None


class StockHistoryPoint(BaseModel):
    date: str
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    close_price: float | None = None
    volume: int | None = None
    value_traded: float | None = None
    weighted_avg_price: float | None = None


class StockStatsResponse(BaseModel):
    total_stocks: int
    active_stocks: int
    by_sector: dict[str, int]
    by_board: dict[str, int]


class StockSectorSummary(BaseModel):
    sector: str
    count: int
    avg_pe: float | None = None
    avg_dividend_yield: float | None = None
    total_market_cap: float | None = None


# --- Helpers ---


def _stock_to_response(s: StockORM) -> StockResponse:
    return StockResponse(
        internal_id=s.internal_id,
        secid=s.secid,
        name=s.name,
        isin=s.isin,
        issuer=s.issuer,
        board=s.board,
        currency=s.currency,
        lot_size=s.lot_size,
        prev_price=float(s.prev_price) if s.prev_price is not None else None,
        price=float(s.price) if s.price is not None else None,
        open_price=float(s.open_price) if s.open_price is not None else None,
        high_price=float(s.high_price) if s.high_price is not None else None,
        low_price=float(s.low_price) if s.low_price is not None else None,
        close_price=float(s.close_price) if s.close_price is not None else None,
        volume=s.volume,
        value_traded=float(s.value_traded) if s.value_traded is not None else None,
        market_capitalization=float(s.market_capitalization) if s.market_capitalization is not None else None,
        pe_ratio=float(s.pe_ratio) if s.pe_ratio is not None else None,
        pbr_ratio=float(s.pbr_ratio) if s.pbr_ratio is not None else None,
        dividend_yield=float(s.dividend_yield) if s.dividend_yield is not None else None,
        earnings_per_share=float(s.earnings_per_share) if s.earnings_per_share is not None else None,
        sector=s.sector,
        status=s.status,
        fetched_at=s.fetched_at.isoformat() if s.fetched_at else None,
    )


# --- Free endpoints ---


@router.get("", response_model=list[StockResponse])
async def list_stocks(
    board: str | None = None,
    sector: str | None = None,
    sort_by: str = "value_traded",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[StockResponse]:
    """Список акций MOEX с фильтрацией и сортировкой."""
    async with session_scope() as session:
        stmt = select(StockORM)
        if board:
            stmt = stmt.where(StockORM.board == board.upper())
        if sector:
            stmt = stmt.where(StockORM.sector == sector)
        sort_col = getattr(StockORM, sort_by, StockORM.value_traded)
        if sort_col is None:
            sort_col = StockORM.value_traded
        stmt = stmt.order_by(sort_col.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        stocks = list(result.scalars().all())
    return [_stock_to_response(s) for s in stocks]


@router.get("/stats", response_model=StockStatsResponse)
async def stock_stats() -> StockStatsResponse:
    """Агрегированная статистика по акциям."""
    from sqlalchemy import text as sa_text

    async with session_scope() as session:
        total = (await session.execute(sa_text("SELECT COUNT(*) FROM stocks"))).scalar() or 0
        active = (
            await session.execute(sa_text("SELECT COUNT(*) FROM stocks WHERE status = 'active'"))
        ).scalar() or 0
        by_sector = await session.execute(
            sa_text("SELECT COALESCE(sector, 'Unknown') as s, COUNT(*) as cnt FROM stocks GROUP BY s")
        )
        by_board = await session.execute(
            sa_text("SELECT board, COUNT(*) as cnt FROM stocks GROUP BY board")
        )
    return StockStatsResponse(
        total_stocks=total,
        active_stocks=active,
        by_sector={row[0]: row[1] for row in by_sector.fetchall()},
        by_board={row[0]: row[1] for row in by_board.fetchall()},
    )


@router.get("/sectors", response_model=list[StockSectorSummary])
async def stock_sectors() -> list[StockSectorSummary]:
    """Сводка по секторам: количество, средний P/E, див. доходность, капитализация."""
    from sqlalchemy import func as sa_func

    async with session_scope() as session:
        stmt = (
            select(
                StockORM.sector,
                sa_func.count(StockORM.internal_id).label("cnt"),
                sa_func.avg(StockORM.pe_ratio).label("avg_pe"),
                sa_func.avg(StockORM.dividend_yield).label("avg_dy"),
                sa_func.sum(StockORM.market_capitalization).label("total_mc"),
            )
            .where(StockORM.sector.isnot(None))
            .group_by(StockORM.sector)
            .order_by(sa_func.sum(StockORM.market_capitalization).desc())
        )
        result = await session.execute(stmt)
        rows = result.all()
    return [
        StockSectorSummary(
            sector=r[0] or "Unknown",
            count=r[1],
            avg_pe=round(float(r[2]), 2) if r[2] else None,
            avg_dividend_yield=round(float(r[3]), 2) if r[3] else None,
            total_market_cap=float(r[4]) if r[4] else None,
        )
        for r in rows
    ]


@router.get("/{internal_id}", response_model=StockResponse)
async def get_stock(internal_id: str) -> StockResponse:
    """Детали одной акции."""
    async with session_scope() as session:
        result = await session.execute(
            select(StockORM).where(StockORM.internal_id == internal_id)
        )
        stock = result.scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Stock {internal_id} not found")
    return _stock_to_response(stock)


@router.get("/{internal_id}/history", response_model=list[StockHistoryPoint])
async def stock_history(
    internal_id: str,
    days: int = Query(default=30, ge=1, le=365),
) -> list[StockHistoryPoint]:
    """История торгов акцией (дневные свечи)."""
    async with session_scope() as session:
        result = await session.execute(
            select(StockORM).where(StockORM.internal_id == internal_id)
        )
        stock = result.scalar_one_or_none()
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Stock {internal_id} not found")
    async with session_scope() as session:
        stmt = (
            select(StockHistoryORM)
            .where(StockHistoryORM.internal_id == internal_id)
            .order_by(StockHistoryORM.date.desc())
            .limit(days)
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
    return [
        StockHistoryPoint(
            date=r.date.isoformat(),
            open_price=float(r.open_price) if r.open_price is not None else None,
            high_price=float(r.high_price) if r.high_price is not None else None,
            low_price=float(r.low_price) if r.low_price is not None else None,
            close_price=float(r.close_price) if r.close_price is not None else None,
            volume=r.volume,
            value_traded=float(r.value_traded) if r.value_traded is not None else None,
            weighted_avg_price=float(r.weighted_avg_price) if r.weighted_avg_price is not None else None,
        )
        for r in reversed(rows)
    ]


@router.get("/board/{board}", response_model=list[StockResponse])
async def stocks_by_board(
    board: str,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[StockResponse]:
    """Акции по торговой доске (TQBR, TQOD, TQDE)."""
    async with session_scope() as session:
        stmt = (
            select(StockORM)
            .where(StockORM.board == board.upper())
            .order_by(StockORM.value_traded.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        stocks = list(result.scalars().all())
    return [_stock_to_response(s) for s in stocks]


# --- Pro endpoints ---


@router.get("/top/dividend", response_model=list[StockResponse])
async def top_dividend_stocks(
    limit: int = Query(default=20, ge=1, le=100),
    _tier: str = Depends(RequireFeature("access_stock_list")),
) -> list[StockResponse]:
    """Топ акций по дивидендной доходности (Pro)."""
    async with session_scope() as session:
        stmt = (
            select(StockORM)
            .where(StockORM.dividend_yield.isnot(None))
            .where(StockORM.dividend_yield > 0)
            .order_by(StockORM.dividend_yield.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        stocks = list(result.scalars().all())
    return [_stock_to_response(s) for s in stocks]


@router.get("/top/cap", response_model=list[StockResponse])
async def top_cap_stocks(
    limit: int = Query(default=20, ge=1, le=100),
    _tier: str = Depends(RequireFeature("access_stock_list")),
) -> list[StockResponse]:
    """Топ акций по рыночной капитализации (Pro)."""
    async with session_scope() as session:
        stmt = (
            select(StockORM)
            .where(StockORM.market_capitalization.isnot(None))
            .order_by(StockORM.market_capitalization.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        stocks = list(result.scalars().all())
    return [_stock_to_response(s) for s in stocks]


@router.get("/search/{query}")
async def search_stocks(
    query: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[StockResponse]:
    """Поиск акций по названию / тикеру / ISIN."""
    async with session_scope() as session:
        pattern = f"%{query}%"
        stmt = (
            select(StockORM)
            .where(
                (StockORM.name.ilike(pattern))
                | (StockORM.secid.ilike(pattern))
                | (StockORM.isin.ilike(pattern))
                | (StockORM.issuer.ilike(pattern))
            )
            .order_by(StockORM.value_traded.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        stocks = list(result.scalars().all())
    return [_stock_to_response(s) for s in stocks]
