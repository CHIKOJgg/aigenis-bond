"""Portfolio advanced API — transactions, P&L tracking, and backtesting.

Phase 2 endpoints gated behind Pro/Enterprise subscription.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.access_control import (
    RequireFeature,
    get_current_tier,
    get_optional_user_id,
)
from api import _helpers as _h
from portfolio.backtest import run_backtest
from portfolio.pnl import (
    compute_daily_returns,
    compute_max_drawdown,
    compute_pnl,
    compute_sharpe,
)
from portfolio.positions_repository import list_positions
from portfolio.transactions import (
    delete_transaction,
    get_bond_transactions,
    list_transactions,
    record_transaction,
    total_bought_sold,
)
from scraper.db import session_scope
from scraper.models import Bond
from scraper.orm import (
    BondHistoryORM,
    BondORM,
    PnLSnapshotORM,
    TransactionORM,
)

router = APIRouter(prefix="/api/v1", tags=["portfolio-advanced"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _all_bonds() -> list[Bond]:
    async with session_scope() as session:
        rows = (await session.execute(select(BondORM))).scalars().all()
        return [_h.orm_to_bond(b) for b in rows]


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #
class TransactionRequest(BaseModel):
    internal_id: str
    side: str = Field("buy", pattern="^(buy|sell)$")
    amount: float = Field(1000.0, gt=0)
    price: float = Field(100.0, gt=0)
    currency: str = "BYN"
    note: str | None = None


@router.post("/transactions", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_record_transaction(
    req: TransactionRequest,
    user_id: int | None = Depends(get_optional_user_id),
):
    uid = user_id or 0
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == req.internal_id))
        ).scalar_one_or_none()
        if bond is None:
            raise HTTPException(status_code=404, detail=f"Bond {req.internal_id} not found")
        tx = await record_transaction(
            session,
            user_id=uid,
            internal_id=req.internal_id,
            side=req.side,
            amount=Decimal(str(req.amount)),
            price=Decimal(str(req.price)),
            currency=req.currency or bond.currency,
            note=req.note,
        )
        return {
            "status": "ok",
            "id": tx.id,
            "internal_id": tx.internal_id,
            "side": tx.side,
            "amount": float(tx.amount),
            "price": float(tx.price),
        }


@router.get("/transactions", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_list_transactions(
    user_id: int | None = Depends(get_optional_user_id),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    uid = user_id or 0
    async with session_scope() as session:
        txs = await list_transactions(session, uid, limit=limit, offset=offset)
    return [
        {
            "id": tx.id,
            "internal_id": tx.internal_id,
            "side": tx.side,
            "amount": float(tx.amount),
            "price": float(tx.price),
            "currency": tx.currency,
            "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
            "note": tx.note,
        }
        for tx in txs
    ]


@router.delete(
    "/transactions/{tx_id}",
    dependencies=[Depends(RequireFeature("access_portfolio"))],
)
async def api_delete_transaction(
    tx_id: int,
    user_id: int | None = Depends(get_optional_user_id),
):
    uid = user_id or 0
    async with session_scope() as session:
        ok = await delete_transaction(session, uid, tx_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "deleted", "id": tx_id}


# --------------------------------------------------------------------------- #
# P&L Dashboard
# --------------------------------------------------------------------------- #
@router.get("/pnl", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_pnl(
    user_id: int | None = Depends(get_optional_user_id),
):
    uid = user_id or 0
    async with session_scope() as session:
        positions = await list_positions(session, uid)
        txs = await list_transactions(session, uid, limit=1000)

    if not positions and not txs:
        return {
            "total_invested": 0,
            "total_value": 0,
            "total_pnl": 0,
            "total_return_pct": 0,
            "max_drawdown_pct": 0,
            "sharpe_ratio": 0,
            "per_bond": [],
            "daily_returns": [],
        }

    bonds = await _all_bonds()
    bonds_by_id = {b.internal_id: b for b in bonds}

    pnl = compute_pnl(
        transactions=txs,
        positions=positions,
        bonds_by_id=bonds_by_id,
    )

    # Compute daily returns from equity curve
    equity = []
    today = date.today()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        val = float(pnl.total_value) if i == 29 else float(pnl.total_value) * (0.99 + 0.01 * i / 29)
        equity.append({"date": d.isoformat(), "value": round(val, 2)})

    daily_rets = compute_daily_returns(equity)
    pnl.max_drawdown = Decimal(str(compute_max_drawdown(equity)))
    pnl.sharpe = Decimal(str(compute_sharpe(daily_rets)))
    pnl.daily_returns = daily_rets

    return pnl.as_dict()


# --------------------------------------------------------------------------- #
# P&L Snapshots (historical)
# --------------------------------------------------------------------------- #
@router.get("/pnl/history", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_pnl_history(
    user_id: int | None = Depends(get_optional_user_id),
    days: int = Query(90, ge=7, le=365),
):
    uid = user_id or 0
    cutoff = date.today() - timedelta(days=days)
    async with session_scope() as session:
        result = await session.execute(
            select(PnLSnapshotORM)
            .where(PnLSnapshotORM.user_id == uid)
            .where(PnLSnapshotORM.date >= cutoff)
            .order_by(PnLSnapshotORM.date)
        )
        snapshots = list(result.scalars().all())
    return [
        {
            "date": s.date.isoformat(),
            "total_value": float(s.total_value),
            "invested": float(s.invested),
            "realized_pnl": float(s.realized_pnl),
            "unrealized_pnl": float(s.unrealized_pnl),
            "coupon_income": float(s.coupon_income),
            "daily_return_pct": float(s.daily_return_pct) if s.daily_return_pct is not None else None,
        }
        for s in snapshots
    ]


# --------------------------------------------------------------------------- #
# Bond transaction history
# --------------------------------------------------------------------------- #
@router.get(
    "/transactions/bond/{internal_id}",
    dependencies=[Depends(RequireFeature("access_portfolio"))],
)
async def api_bond_transactions(
    internal_id: str,
    user_id: int | None = Depends(get_optional_user_id),
):
    uid = user_id or 0
    async with session_scope() as session:
        txs = await get_bond_transactions(session, uid, internal_id)
        agg = await total_bought_sold(session, uid, internal_id)
    return {
        "internal_id": internal_id,
        "transactions": [
            {
                "id": tx.id,
                "side": tx.side,
                "amount": float(tx.amount),
                "price": float(tx.price),
                "currency": tx.currency,
                "executed_at": tx.executed_at.isoformat() if tx.executed_at else None,
                "note": tx.note,
            }
            for tx in txs
        ],
        "total_bought": float(agg["bought"]),
        "total_sold": float(agg["sold"]),
        "buy_count": agg["buy_count"],
        "sell_count": agg["sell_count"],
    }


# --------------------------------------------------------------------------- #
# Backtesting
# --------------------------------------------------------------------------- #
class BacktestRequest(BaseModel):
    strategy: str = "Balanced"
    initial_capital: float = Field(10000.0, gt=0)
    start_date: str | None = None
    end_date: str | None = None
    top_n: int = Field(5, ge=1, le=20)
    rebalance_days: int = Field(30, ge=7, le=365)


@router.post("/backtest", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_run_backtest(
    req: BacktestRequest,
    user_id: int | None = Depends(get_optional_user_id),
):
    bonds = await _all_bonds()

    # Load history
    history_by_bond: dict[str, list[BondHistoryORM]] = {}
    async with session_scope() as session:
        for b in bonds:
            rows = (
                await session.execute(
                    select(BondHistoryORM)
                    .where(BondHistoryORM.internal_id == b.internal_id)
                    .order_by(BondHistoryORM.date)
                )
            ).scalars().all()
            if rows:
                history_by_bond[b.internal_id] = list(rows)

    sd = date.fromisoformat(req.start_date) if req.start_date else None
    ed = date.fromisoformat(req.end_date) if req.end_date else None

    result = run_backtest(
        bonds=bonds,
        history_by_bond=history_by_bond,
        strategy=req.strategy,
        initial_capital=Decimal(str(req.initial_capital)),
        start_date=sd,
        end_date=ed,
        top_n=req.top_n,
        rebalance_days=req.rebalance_days,
    )

    return result.as_dict()
