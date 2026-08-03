"""Репозиторий для desk-сущностей V4."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select, text
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
    if session.get_bind().dialect.name == "sqlite":
        # SQLite can't express the date() expression-index target for DO
        # UPDATE; make the insert idempotent by deleting the day's points first.
        today = datetime.now(UTC).date()
        await session.execute(
            delete(CurvePointORM).where(
                CurvePointORM.currency == currency,
                func.date(CurvePointORM.observed_at) == today,
            )
        )
        await session.execute(stmt)
    else:
        # PostgreSQL: match the IMMUTABLE expression index uq_curve_tenor_day.
        day_expr = text("((observed_at AT TIME ZONE 'UTC')::date)")
        stmt = stmt.on_conflict_do_update(
            index_elements=["currency", "tenor", day_expr],
            set_={
                "years": stmt.excluded.years,
                "rate_pct": stmt.excluded.rate_pct,
                "ns_params": stmt.excluded.ns_params,
                "observed_at": stmt.excluded.observed_at,
            },
        )
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
    stmt = stmt.on_conflict_do_update(
        index_elements=["internal_id", "peer_currency", "asof_date"],
        set_={
            "z_score": stmt.excluded.z_score,
            "spread_pct": stmt.excluded.spread_pct,
            "fair_spread_pct": stmt.excluded.fair_spread_pct,
            "side": stmt.excluded.side,
            "rationale": stmt.excluded.rationale,
            "peer_set": stmt.excluded.peer_set,
        },
    )
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
    stmt = stmt.on_conflict_do_update(
        index_elements=["internal_id", "asof_date"],
        set_={
            "notional": stmt.excluded.notional,
            "coupon_pct": stmt.excluded.coupon_pct,
            "funding_rate_pct": stmt.excluded.funding_rate_pct,
            "rolldown_bps": stmt.excluded.rolldown_bps,
            "expected_pnl_pct": stmt.excluded.expected_pnl_pct,
            "breakeven_bps": stmt.excluded.breakeven_bps,
            "horizon_days": stmt.excluded.horizon_days,
        },
    )
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
    stmt = pg_insert(StressRunORM).values(
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
    stmt = stmt.on_conflict_do_update(
        index_elements=["scenario_name", "asof_date"],
        set_={
            "scenario_kind": stmt.excluded.scenario_kind,
            "scenario": stmt.excluded.scenario,
            "portfolio_value": stmt.excluded.portfolio_value,
            "stressed_value": stmt.excluded.stressed_value,
            "pnl": stmt.excluded.pnl,
            "pnl_pct": stmt.excluded.pnl_pct,
            "by_position": stmt.excluded.by_position,
            "by_tenor": stmt.excluded.by_tenor,
        },
    )
    stmt = stmt.returning(StressRunORM.id)
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
    stmt = stmt.on_conflict_do_update(
        index_elements=["internal_id", "asof_date"],
        set_={
            "currency": stmt.excluded.currency,
            "tenor_years": stmt.excluded.tenor_years,
            "ytm_pct": stmt.excluded.ytm_pct,
            "flat_yield_pct": stmt.excluded.flat_yield_pct,
            "z_spread_pct": stmt.excluded.z_spread_pct,
            "g_spread_pct": stmt.excluded.g_spread_pct,
            "curve_rate_pct": stmt.excluded.curve_rate_pct,
            "model_price": stmt.excluded.model_price,
            "market_price": stmt.excluded.market_price,
            "mispricing_pct": stmt.excluded.mispricing_pct,
            "side": stmt.excluded.side,
        },
    )
    await session.execute(stmt)
    return len(rows)


async def latest_spread_reports(session: AsyncSession, limit: int = 50) -> list[SpreadReportORM]:
    result = await session.execute(
        select(SpreadReportORM).order_by(SpreadReportORM.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
