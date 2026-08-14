"""Репозиторий для Reward/Risk Score."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scoring.engine import score_bond
from scoring.models import BondScore, ScoreBreakdown
from scraper.db import upsert_row
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
    await upsert_row(
        session,
        BondScoreORM,
        index_elements=["internal_id"],
        values=_to_orm(score),
    )


async def upsert_scores_batch(session: AsyncSession, scores: list[BondScore]) -> int:
    if not scores:
        return 0
    for s in scores:
        await upsert_row(
            session,
            BondScoreORM,
            index_elements=["internal_id"],
            values=_to_orm(s),
        )
    return len(scores)


async def top_scores(
    session: AsyncSession, limit: int = 20, offset: int = 0, market: str | None = None
) -> list[BondScoreORM]:
    stmt = select(BondScoreORM)
    if market:
        stmt = stmt.join(BondORM, BondScoreORM.internal_id == BondORM.internal_id, isouter=True)
        stmt = stmt.where(BondORM.market == market)
    stmt = stmt.order_by(BondScoreORM.score.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_scores(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(BondScoreORM))
    return int(result.scalar_one())


async def recompute_all(session: AsyncSession) -> int:
    """Пересчитать Score для всех облигаций в БД."""
    from datetime import date

    from desk.ytm import to_price_pct, ytm_from_price

    result = await session.execute(select(BondORM))
    bonds = list(result.scalars().all())
    scores: list[BondScore] = []
    for b in bonds:
        ytm = float(b.yield_to_maturity) if b.yield_to_maturity is not None and float(b.yield_to_maturity) > 0 else None
        if ytm is None and b.price is not None and b.coupon_rate is not None and b.maturity_date is not None:
            try:
                price_pct = to_price_pct(b.price, b.nominal)
                if price_pct is not None:
                    solved = ytm_from_price(
                        price_pct=price_pct,
                        coupon_rate_pct=float(b.coupon_rate),
                        coupon_frequency=int(b.coupon_frequency or 2),
                        maturity=b.maturity_date,
                        asof=date.today(),
                    )
                    if solved is not None and solved > 0:
                        ytm = round(solved, 4)
                        b.yield_to_maturity = Decimal(str(ytm))
            except Exception:
                pass
        scores.append(
            score_bond(
                internal_id=b.internal_id,
                yield_to_maturity=ytm,
                currency=b.currency,
                maturity_date=b.maturity_date,
                status=b.status,
                issuer=b.issuer,
                price=b.price,
                nominal=b.nominal,
                coupon_rate=b.coupon_rate,
                market=getattr(b, "market", "bcse"),
            )
        )
    await upsert_scores_batch(session, scores)
    await session.commit()
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
