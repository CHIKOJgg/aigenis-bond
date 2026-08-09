"""Tests for scoring/repository.py (upsert, top_scores, recompute_all, ...)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scoring.models import BondScore, ScoreBreakdown
from scoring.repository import (
    count_scores,
    get_score,
    recompute_all,
    score_from_orm,
    top_scores,
    upsert_score,
    upsert_scores_batch,
)
from scraper.db import session_scope
from scraper.orm import BondORM


def _score(internal_id: str, value: float, *, breakdown: ScoreBreakdown | None = None) -> BondScore:
    return BondScore(
        internal_id=internal_id,
        score=value,
        breakdown=breakdown or ScoreBreakdown(yield_component=value),
        computed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def _add_bond(
    session,
    internal_id: str,
    *,
    market: str = "bcse",
    currency: str = "USD",
    ytm: str = "8.0",
) -> None:
    session.add(
        BondORM(
            internal_id=internal_id,
            name=f"Bond {internal_id}",
            currency=currency,
            market=market,
            status="active",
            yield_to_maturity=Decimal(ytm),
            price=Decimal("100"),
            coupon_rate=Decimal("5.0"),
            maturity_date=date(2030, 1, 1),
            fetched_at=datetime.now(UTC),
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_upsert_score_and_get():
    async with session_scope() as session:
        await upsert_score(session, _score("R-1", 80.5))
        await session.flush()
        found = await get_score(session, "R-1")
        assert found is not None
        assert float(found.score) == 80.5
        assert found.tier == "A"
        assert found.breakdown["yield_component"] == 80.5
        assert await get_score(session, "R-MISSING") is None


@pytest.mark.asyncio
async def test_upsert_score_overwrites():
    async with session_scope() as session:
        await upsert_score(session, _score("R-2", 50.0))
        await upsert_score(session, _score("R-2", 90.0))
        await session.flush()
        found = await get_score(session, "R-2")
        assert found is not None and float(found.score) == 90.0


@pytest.mark.asyncio
async def test_upsert_scores_batch_empty_and_full():
    async with session_scope() as session:
        assert await upsert_scores_batch(session, []) == 0
        n = await upsert_scores_batch(
            session, [_score("B-1", 10.0), _score("B-2", 20.0), _score("B-3", 30.0)]
        )
        assert n == 3
        assert await count_scores(session) >= 3


@pytest.mark.asyncio
async def test_count_scores():
    async with session_scope() as session:
        await upsert_scores_batch(session, [_score("C-1", 5.0), _score("C-2", 6.0)])
        assert await count_scores(session) >= 2


@pytest.mark.asyncio
async def test_top_scores_ordering_and_offset():
    from sqlalchemy import delete

    from scraper.orm import BondScoreORM

    async with session_scope() as session:
        await session.execute(delete(BondScoreORM))
        await session.flush()
        await upsert_scores_batch(
            session,
            [_score("T-1", 70.0), _score("T-2", 90.0), _score("T-3", 80.0)],
        )
        top = await top_scores(session)
        assert [b.internal_id for b in top[:3]] == ["T-2", "T-3", "T-1"]
        first_two = await top_scores(session, limit=2, offset=1)
        assert [b.internal_id for b in first_two] == ["T-3", "T-1"]


@pytest.mark.asyncio
async def test_top_scores_market_filter():
    async with session_scope() as session:
        await _add_bond(session, "M-1", market="bcse")
        await _add_bond(session, "M-2", market="moex")
        await upsert_scores_batch(session, [_score("M-1", 10.0), _score("M-2", 99.0)])

        moex = await top_scores(session, market="moex")
        assert [b.internal_id for b in moex] == ["M-2"]
        bcse = await top_scores(session, market="bcse")
        assert [b.internal_id for b in bcse] == ["M-1"]
        unknown = await top_scores(session, market="nope")
        assert unknown == []


@pytest.mark.asyncio
async def test_recompute_all_empty_and_with_bonds():
    from sqlalchemy import delete

    from scraper.orm import BondScoreORM

    async with session_scope() as session:
        await session.execute(delete(BondScoreORM))
        await session.execute(delete(BondORM))
        await session.flush()
        assert await recompute_all(session) == 0
        await _add_bond(session, "R-10", market="bcse", currency="BYN")
        await _add_bond(session, "R-11", market="moex", currency="RUB", ytm="12.5")
        n = await recompute_all(session)
        assert n == 2
        found = await get_score(session, "R-10")
        assert found is not None and found.breakdown is not None


@pytest.mark.asyncio
async def test_score_from_orm():
    async with session_scope() as session:
        await upsert_scores_batch(
            session,
            [
                _score(
                    "F-1",
                    77.0,
                    breakdown=ScoreBreakdown(yield_component=10.0, currency_component=20.0),
                )
            ],
        )
        await session.flush()
        orm = await get_score(session, "F-1")
        assert orm is not None
        back = score_from_orm(orm)
        assert back.internal_id == "F-1"
        assert back.score == 77.0
        assert back.breakdown.yield_component == 10.0
        assert back.breakdown.currency_component == 20.0
        assert back.computed_at is not None
