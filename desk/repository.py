"""Репозиторий для desk-сущностей V4."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from desk.models import CarryTrade, RepoDeal, RVSignal, SpreadReport, StressResult
from scraper.orm import (
    CarryTradeORM,
    CurvePointORM,
    RepoDealORM,
    RVSignalORM,
    SpreadReportORM,
    StressRunORM,
)


async def save_curve_points(
    session: AsyncSession,
    *,
    currency: str,
    points: list[tuple[str, float, float]],
    ns_params: dict | None = None,
) -> int:
    rows = [
        {
            "currency": currency,
            "tenor": tenor,
            "years": Decimal(str(years)),
            "rate_pct": Decimal(str(rate)),
            "observed_at": datetime.now(UTC),
            "ns_params": ns_params,
        }
        for tenor, years, rate in points
    ]
    if not rows:
        return 0
    stmt = pg_insert(CurvePointORM).values(rows)
    await session.execute(stmt)
    return len(rows)


async def save_rv_signals(session: AsyncSession, signals: Iterable[RVSignal]) -> int:
    rows = [
        {
            "internal_id": s.internal_id,
            "peer_currency": s.peer_currency,
            "z_score": Decimal(str(s.z_score)),
            "spread_pct": Decimal(str(s.spread_pct)),
            "fair_spread_pct": Decimal(str(s.fair_spread_pct)),
            "side": s.side,
            "rationale": s.rationale,
            "peer_set": s.peer_set,
            "asof_date": s.asof_date,
        }
        for s in signals
    ]
    if not rows:
        return 0
    stmt = pg_insert(RVSignalORM).values(rows)
    await session.execute(stmt)
    return len(rows)


async def latest_rv_signals(session: AsyncSession, limit: int = 50) -> list[RVSignalORM]:
    result = await session.execute(
        select(RVSignalORM).order_by(RVSignalORM.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def save_carry_trades(session: AsyncSession, trades: Iterable[CarryTrade]) -> int:
    rows = [
        {
            "internal_id": t.internal_id,
            "notional": t.notional,
            "coupon_pct": Decimal(str(t.coupon_pct)),
            "funding_rate_pct": Decimal(str(t.funding_rate_pct)),
            "rolldown_bps": Decimal(str(t.rolldown_bps)),
            "expected_pnl_pct": Decimal(str(t.expected_pnl_pct)),
            "breakeven_bps": Decimal(str(t.breakeven_bps)),
            "horizon_days": t.horizon_days,
            "asof_date": t.asof_date,
        }
        for t in trades
    ]
    if not rows:
        return 0
    stmt = pg_insert(CarryTradeORM).values(rows)
    await session.execute(stmt)
    return len(rows)


async def save_repo_deal(session: AsyncSession, deal: RepoDeal) -> None:
    stmt = pg_insert(RepoDealORM).values(
        internal_id=deal.internal_id,
        notional=deal.notional,
        haircut_pct=Decimal(str(deal.haircut_pct)),
        repo_rate_pct=Decimal(str(deal.repo_rate_pct)),
        tenor_days=deal.tenor_days,
        cash_lent=deal.cash_lent,
        collateral_value=deal.collateral_value,
        accrued_interest=deal.accrued_interest,
        asof_date=deal.asof_date,
    )
    await session.execute(stmt)


async def save_stress_run(session: AsyncSession, result: StressResult) -> int:
    stmt = (
        pg_insert(StressRunORM)
        .values(
            scenario_name=result.scenario.name,
            scenario_kind=result.scenario.kind,
            scenario=result.scenario.model_dump(mode="json"),
            portfolio_value=result.portfolio_value,
            stressed_value=result.stressed_value,
            pnl=result.pnl,
            pnl_pct=Decimal(str(result.pnl_pct)),
            by_position={k: float(v) for k, v in result.by_position.items()},
            by_tenor={k: float(v) for k, v in result.by_tenor.items()},
            asof_date=result.asof_date,
        )
        .returning(StressRunORM.id)
    )
    res = await session.execute(stmt)
    return int(res.scalar_one())


async def latest_stress_runs(session: AsyncSession, limit: int = 10) -> list[StressRunORM]:
    result = await session.execute(
        select(StressRunORM).order_by(StressRunORM.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def save_spread_reports(session: AsyncSession, reports: Iterable[SpreadReport]) -> int:
    rows = [
        {
            "internal_id": r.internal_id,
            "currency": r.currency,
            "tenor_years": Decimal(str(r.tenor_years)),
            "ytm_pct": Decimal(str(r.ytm_pct)) if r.ytm_pct is not None else None,
            "flat_yield_pct": Decimal(str(r.flat_yield_pct))
            if r.flat_yield_pct is not None
            else None,
            "z_spread_pct": Decimal(str(r.z_spread_pct)) if r.z_spread_pct is not None else None,
            "g_spread_pct": Decimal(str(r.g_spread_pct)) if r.g_spread_pct is not None else None,
            "curve_rate_pct": Decimal(str(r.curve_rate_pct))
            if r.curve_rate_pct is not None
            else None,
            "model_price": Decimal(str(r.model_price)) if r.model_price is not None else None,
            "market_price": Decimal(str(r.market_price)) if r.market_price is not None else None,
            "mispricing_pct": Decimal(str(r.mispricing_pct))
            if r.mispricing_pct is not None
            else None,
            "side": r.side,
            "asof_date": r.asof_date,
        }
        for r in reports
    ]
    if not rows:
        return 0
    stmt = pg_insert(SpreadReportORM).values(rows)
    await session.execute(stmt)
    return len(rows)


async def latest_spread_reports(session: AsyncSession, limit: int = 50) -> list[SpreadReportORM]:
    result = await session.execute(
        select(SpreadReportORM).order_by(SpreadReportORM.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
