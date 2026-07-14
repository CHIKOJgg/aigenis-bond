"""Репозиторий для портфельных позиций пользователя и истории ребалансировок."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ml.models import RebalancePlan
from scraper.orm import PortfolioPositionORM, RebalanceHistoryORM


async def upsert_position(
    session: AsyncSession, user_id: int, internal_id: str, amount: Decimal
) -> None:
    from scraper.db import upsert_row

    await upsert_row(
        session,
        PortfolioPositionORM,
        ["user_id", "internal_id"],
        {"user_id": user_id, "internal_id": internal_id, "amount": amount},
    )


async def remove_position(session: AsyncSession, user_id: int, internal_id: str) -> None:
    pos = await get_position(session, user_id, internal_id)
    if pos is None:
        return
    await session.delete(pos)


async def get_position(
    session: AsyncSession, user_id: int, internal_id: str
) -> PortfolioPositionORM | None:
    result = await session.execute(
        select(PortfolioPositionORM).where(
            PortfolioPositionORM.user_id == user_id,
            PortfolioPositionORM.internal_id == internal_id,
        )
    )
    return result.scalar_one_or_none()


async def list_positions(session: AsyncSession, user_id: int) -> list[PortfolioPositionORM]:
    result = await session.execute(
        select(PortfolioPositionORM).where(PortfolioPositionORM.user_id == user_id)
    )
    return list(result.scalars().all())


def total_value(positions: list[PortfolioPositionORM]) -> Decimal:
    return sum((p.amount for p in positions), start=Decimal("0"))


async def save_rebalance_plan(session: AsyncSession, user_id: int, plan: RebalancePlan) -> int:
    values = {
        "user_id": user_id,
        "strategy": plan.strategy,
        "drift_threshold": Decimal(str(plan.drift_threshold)),
        "max_drift_observed": Decimal(str(plan.max_drift_observed)),
        "expected_return": (
            Decimal(str(plan.expected_return)) if plan.expected_return is not None else None
        ),
        "estimated_cost": (
            Decimal(str(plan.estimated_cost)) if plan.estimated_cost is not None else None
        ),
        "actions": [a.model_dump(mode="json") for a in plan.actions],
        "applied": False,
    }
    obj = RebalanceHistoryORM(**values)
    session.add(obj)
    await session.flush()
    return obj.id


async def list_rebalance_history(
    session: AsyncSession, user_id: int, limit: int = 20
) -> list[RebalanceHistoryORM]:
    result = await session.execute(
        select(RebalanceHistoryORM)
        .where(RebalanceHistoryORM.user_id == user_id)
        .order_by(RebalanceHistoryORM.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_rebalance_applied(session: AsyncSession, plan_id: int) -> None:
    from sqlalchemy import update

    await session.execute(
        update(RebalanceHistoryORM).where(RebalanceHistoryORM.id == plan_id).values(applied=True)
    )
