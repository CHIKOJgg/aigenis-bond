"""Tests for the positions + rebalance-history repository and total_value math."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from ml.models import RebalanceAction, RebalancePlan
from portfolio.positions_repository import (
    get_position,
    list_positions,
    list_rebalance_history,
    mark_rebalance_applied,
    remove_position,
    save_rebalance_plan,
    total_value,
    upsert_position,
)
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, PortfolioPositionORM, UserORM


def _run(coro_fn):
    async def wrapper():
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            await coro_fn()
        finally:
            await dispose()

    asyncio.run(wrapper())


async def _make_user(uid: int):
    async with session_scope() as s:
        s.add(
            UserORM(
                email=f"pos_{uid}@local",
                name="Pos",
                password_hash="x",
                role="user",
                is_active=True,
                subscription_tier="pro",
                subscription_expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )


def test_upsert_and_get_position():
    async def run():
        await _make_user(8201)
        async with session_scope() as s:
            await upsert_position(s, 8201, "P1", Decimal("1000"))
        pos = await _get(8201, "P1")
        assert pos is not None
        assert pos.amount == Decimal("1000")

    async def _get(uid, iid):
        async with session_scope() as s:
            return await get_position(s, uid, iid)

    _run(run)


def test_upsert_replaces_amount_on_conflict():
    async def run():
        await _make_user(8202)
        async with session_scope() as s:
            await upsert_position(s, 8202, "P1", Decimal("1000"))
            await upsert_position(s, 8202, "P1", Decimal("2500"))
        async with session_scope() as s:
            pos = await get_position(s, 8202, "P1")
            assert pos.amount == Decimal("2500")
            all_rows = await list_positions(s, 8202)
            assert len(all_rows) == 1

    _run(run)


def test_remove_position():
    async def run():
        await _make_user(8203)
        async with session_scope() as s:
            await upsert_position(s, 8203, "P1", Decimal("1000"))
        async with session_scope() as s:
            await remove_position(s, 8203, "P1")
        async with session_scope() as s:
            assert await get_position(s, 8203, "P1") is None

    _run(run)


def test_list_positions_returns_only_user_rows():
    async def run():
        await _make_user(8204)
        await _make_user(8205)
        async with session_scope() as s:
            await upsert_position(s, 8204, "A", Decimal("10"))
            await upsert_position(s, 8204, "B", Decimal("20"))
            await upsert_position(s, 8205, "C", Decimal("30"))
        async with session_scope() as s:
            mine = await list_positions(s, 8204)
            ids = {p.internal_id for p in mine}
            assert ids == {"A", "B"}

    _run(run)


def test_total_value_without_fx_returns_sum_of_amounts():
    bonds = [
        PortfolioPositionORM(user_id=0, internal_id="A", amount=Decimal("100")),
        PortfolioPositionORM(user_id=0, internal_id="B", amount=Decimal("250")),
    ]
    assert total_value(bonds) == Decimal("350")


def test_total_value_applies_fx_rates_by_currency():
    class _Bond:
        def __init__(self, currency):
            self.currency = currency

    bonds = [
        PortfolioPositionORM(user_id=0, internal_id="A", amount=Decimal("100")),
        PortfolioPositionORM(user_id=0, internal_id="B", amount=Decimal("200")),
    ]
    bonds_by_id = {"A": _Bond("USD"), "B": _Bond("BYN")}
    fx_rates = {"USD": 3.0, "BYN": 1.0}
    # 100*3 (USD) + 200*1 (BYN) = 500
    assert total_value(bonds, bonds_by_id, fx_rates) == Decimal("500")


def test_total_value_missing_bond_or_fx_falls_back_to_amount():
    class _Bond:
        def __init__(self, currency):
            self.currency = currency

    bonds = [PortfolioPositionORM(user_id=0, internal_id="A", amount=Decimal("100"))]
    # bond present but fx rate missing for its currency -> uses amount * 1.0
    assert total_value(bonds, {"A": _Bond("XYZ")}, {"USD": 3.0}) == Decimal("100")


def _make_plan(strategy="Balanced"):
    return RebalancePlan(
        strategy=strategy,
        drift_threshold=0.05,
        max_drift_observed=0.08,
        actions=[
            RebalanceAction(
                internal_id="A", side="buy", amount=Decimal("1000"),
                weight_before=0.1, weight_after=0.2, reason="drift",
            )
        ],
        expected_return=0.11,
        estimated_cost=Decimal("5.00"),
        created_at=datetime.now(UTC),
    )


def test_save_rebalance_plan_list_and_mark_applied():
    async def run():
        await _make_user(8230)
        async with session_scope() as s:
            pid = await save_rebalance_plan(s, 8230, _make_plan())
            assert pid > 0
        async with session_scope() as s:
            history = await list_rebalance_history(s, 8230)
            assert len(history) == 1
            assert history[0].strategy == "Balanced"
            assert history[0].applied is False
            assert history[0].actions[0]["internal_id"] == "A"
        async with session_scope() as s:
            await mark_rebalance_applied(s, pid)
        async with session_scope() as s:
            history = await list_rebalance_history(s, 8230)
            assert history[0].applied is True

    _run(run)


def test_rebalance_history_isolated_per_user():
    async def run():
        await _make_user(8231)
        await _make_user(8232)
        async with session_scope() as s:
            await save_rebalance_plan(s, 8231, _make_plan("Conservative"))
            await save_rebalance_plan(s, 8232, _make_plan("Aggressive"))
        async with session_scope() as s:
            mine = await list_rebalance_history(s, 8231)
            assert len(mine) == 1
            assert mine[0].strategy == "Conservative"

    _run(run)
