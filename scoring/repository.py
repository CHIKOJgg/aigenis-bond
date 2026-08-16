"""Репозиторий для Reward/Risk Score."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from scoring.eligibility import (
    DISTRIBUTION_MAX_PRICE_PCT,
    DISTRIBUTION_MIN_YTM_PCT,
    EXCLUDED_STATUSES,
    EXTREME_MAX_YTM_PCT,
)
from scoring.engine import score_bond
from scoring.models import BondScore, ScoreBreakdown
from scraper.db import upsert_row
from scraper.orm import BondORM, BondScoreORM


def _to_orm(score: BondScore) -> dict[str, Any]:
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
    """Топ по Score из бумаг, допущенных в портфель (eligibility gate).

    Исключаются на уровне SQL: бумаги в статусах дефолта/делистинга,
    с YTM > 100% (аномалия данных или дистресс) и «дистрибуция»
    (цена < 80% номинала при YTM > 30%).
    """
    stmt = (
        select(BondScoreORM)
        .join(BondORM, BondScoreORM.internal_id == BondORM.internal_id)
        .where(BondORM.status.notin_(EXCLUDED_STATUSES))
        .where(
            or_(
                BondORM.yield_to_maturity.is_(None),
                BondORM.yield_to_maturity <= EXTREME_MAX_YTM_PCT,
            )
        )
        .where(
            not_(
                and_(
                    BondORM.price < DISTRIBUTION_MAX_PRICE_PCT,
                    BondORM.yield_to_maturity > DISTRIBUTION_MIN_YTM_PCT,
                )
            )
        )
    )
    if market:
        stmt = stmt.where(func.lower(BondORM.market) == market.lower())
    stmt = stmt.order_by(BondScoreORM.score.desc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_scores(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(BondScoreORM))
    return int(result.scalar_one())


async def recompute_all(session: AsyncSession) -> int:
    """Пересчитать Score для всех облигаций в БД."""
    from datetime import date

    from desk.ytm import sane_yield, to_price_pct, ytm_from_price

    result = await session.execute(select(BondORM))
    bonds = list(result.scalars().all())
    scores: list[BondScore] = []
    for b in bonds:
        raw_ytm = b.yield_to_maturity
        ytm = None
        if raw_ytm is not None and float(raw_ytm) > 0:
            ytm_val = float(raw_ytm)
            price_pct = to_price_pct(b.price, b.nominal)
            computed = None
            if price_pct is not None and b.coupon_rate is not None and b.maturity_date is not None:
                try:
                    computed = ytm_from_price(
                        price_pct=price_pct,
                        coupon_rate_pct=float(b.coupon_rate),
                        coupon_frequency=int(b.coupon_frequency or 2),
                        maturity=b.maturity_date,
                        asof=date.today(),
                    )
                except Exception:
                    computed = None
            if computed is not None and sane_yield(ytm_val, computed):
                ytm = ytm_val
            elif computed is not None and computed > 0:
                # Source yield disagrees with the coupon/price-implied yield:
                # trust our own estimate instead of the garbage value.
                ytm = round(computed, 4)
            elif ytm_val < 100:
                # No price to cross-check; keep only plausible stored yields.
                ytm = ytm_val
            else:
                # Unvalidatable extreme yield — treat as missing data.
                ytm = None
        if (
            ytm is None
            and raw_ytm is None
            and b.price is not None
            and b.coupon_rate is not None
            and b.maturity_date is not None
        ):
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
            except Exception:
                pass
        # Persist the (corrected) yield so downstream portfolios and
        # recommendations never consume an unvalidated extreme value.
        if ytm is not None:
            b.yield_to_maturity = Decimal(str(ytm))
        elif raw_ytm is not None:
            b.yield_to_maturity = None
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
