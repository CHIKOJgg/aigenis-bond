"""Репозиторий для Reward/Risk Score."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from scoring.engine import score_bond
from scoring.models import BondScore, ScoreBreakdown
from scraper.orm import BondORM, BondScoreORM


def _to_orm(score: BondScore) -> dict:
    return {
        "internal_id": score.internal_id,
        "score": Decimal(str(score.score)),
        "tier": score.tier,
        "breakdown": score.breakdown.model_dump(),
        "computed_at": score.computed_at,
    }


async def upsert_score(session: AsyncSession, score: BondScore) -> None:
    values = _to_orm(score)
    stmt = pg_insert(BondScoreORM).values(**values)
    update_cols = {c: stmt.excluded[c] for c in values if c != "internal_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=[BondScoreORM.internal_id], set_=update_cols
    )
    await session.execute(stmt)


async def upsert_scores_batch(session: AsyncSession, scores: list[BondScore]) -> int:
    if not scores:
        return 0
    rows = [_to_orm(s) for s in scores]
    stmt = pg_insert(BondScoreORM).values(rows)
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c != "internal_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=[BondScoreORM.internal_id], set_=update_cols
    )
    await session.execute(stmt)
    return len(rows)


async def top_scores(
    session: AsyncSession, limit: int = 20, offset: int = 0
) -> list[BondScoreORM]:
    result = await session.execute(
        select(BondScoreORM).order_by(BondScoreORM.score.desc()).limit(limit).offset(offset)
    )
    return list(result.scalars().all())


async def recompute_all(session: AsyncSession) -> int:
    """Пересчитать Score для всех облигаций в БД."""
    result = await session.execute(select(BondORM))
    bonds = list(result.scalars().all())
    scores: list[BondScore] = []
    for b in bonds:
        scores.append(
            score_bond(
                internal_id=b.internal_id,
                yield_to_maturity=b.yield_to_maturity,
                currency=b.currency,
                maturity_date=b.maturity_date,
                status=b.status,
                issuer=b.issuer,
                price=b.price,
            )
        )
    await upsert_scores_batch(session, scores)
    return len(scores)


async def get_score(session: AsyncSession, internal_id: str) -> BondScoreORM | None:
    result = await session.execute(
        select(BondScoreORM).where(BondScoreORM.internal_id == internal_id)
    )
    return result.scalar_one_or_none()


def score_from_orm(orm: BondScoreORM) -> BondScore:
    return BondScore(
        internal_id=orm.internal_id,
        score=float(orm.score),
        breakdown=ScoreBreakdown(**(orm.breakdown or {})),
        computed_at=orm.computed_at,
    )
