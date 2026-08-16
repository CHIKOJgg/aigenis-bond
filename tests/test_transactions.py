"""Tests for the transaction-log repository (portfolio buy/sell CRUD)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from portfolio.transactions import (
    delete_transaction,
    get_bond_transactions,
    list_transactions,
    record_transaction,
    total_bought_sold,
)
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, UserORM


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
                email=f"tx_{uid}@local",
                name="Tx",
                password_hash="x",
                role="user",
                is_active=True,
                subscription_tier="pro",
                subscription_expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )


async def _gather_list(uid):
    async with session_scope() as s:
        return await list_transactions(s, uid)


def test_record_and_list_transactions():
    async def run():
        await _make_user(8101)
        async with session_scope() as s:
            await record_transaction(
                s, user_id=8101, internal_id="B1", side="buy",
                amount=Decimal("1000"), price=Decimal("100"), currency="BYN",
            )
        rows = await _gather_list(8101)
        assert len(rows) == 1
        assert rows[0].internal_id == "B1"
        assert rows[0].side == "buy"
        assert rows[0].amount == Decimal("1000")
        assert rows[0].price == Decimal("100")
        assert rows[0].currency == "BYN"

    _run(run)


def test_list_transactions_ordered_desc_and_paginated():
    async def run():
        await _make_user(8102)
        async with session_scope() as s:
            for i in range(3):
                await record_transaction(
                    s, user_id=8102, internal_id=f"B{i}", side="buy",
                    amount=Decimal("100"), price=Decimal("100"), currency="BYN",
                )
        async with session_scope() as s:
            first = await list_transactions(s, 8102, limit=2)
            assert len(first) == 2
            second_page = await list_transactions(s, 8102, limit=2, offset=2)
            assert len(second_page) == 1
            # the two pages together cover all three bonds
            seen = {t.internal_id for t in first} | {t.internal_id for t in second_page}
            assert seen == {"B0", "B1", "B2"}

    _run(run)


def test_get_bond_transactions_filters_by_bond():
    async def run():
        await _make_user(8103)
        async with session_scope() as s:
            await record_transaction(
                s, user_id=8103, internal_id="X", side="buy",
                amount=Decimal("500"), price=Decimal("100"), currency="BYN",
            )
            await record_transaction(
                s, user_id=8103, internal_id="Y", side="sell",
                amount=Decimal("200"), price=Decimal("101"), currency="BYN",
            )
        async with session_scope() as s:
            xs = await get_bond_transactions(s, 8103, "X")
            assert len(xs) == 1
            assert xs[0].internal_id == "X"
            assert xs[0].side == "buy"

    _run(run)


def test_total_bought_sold_aggregates():
    async def run():
        await _make_user(8104)
        async with session_scope() as s:
            await record_transaction(
                s, user_id=8104, internal_id="Z", side="buy",
                amount=Decimal("1000"), price=Decimal("100"), currency="BYN",
            )
            await record_transaction(
                s, user_id=8104, internal_id="Z", side="buy",
                amount=Decimal("500"), price=Decimal("100"), currency="BYN",
            )
            await record_transaction(
                s, user_id=8104, internal_id="Z", side="sell",
                amount=Decimal("300"), price=Decimal("100"), currency="BYN",
            )
        async with session_scope() as s:
            agg = await total_bought_sold(s, 8104, "Z")
            assert agg["bought"] == Decimal("1500")
            assert agg["sold"] == Decimal("300")
            assert agg["buy_count"] == 2
            assert agg["sell_count"] == 1

    _run(run)


def test_delete_transaction_removes_own_and_not_others():
    async def run():
        await _make_user(8105)
        async with session_scope() as s:
            tx = await record_transaction(
                s, user_id=8105, internal_id="D", side="buy",
                amount=Decimal("100"), price=Decimal("100"), currency="BYN",
            )
            tx_id = int(tx.id)
        # wrong user cannot delete
        async with session_scope() as s:
            assert await delete_transaction(s, 999999, tx_id) is False
        # correct user can delete
        async with session_scope() as s:
            assert await delete_transaction(s, 8105, tx_id) is True
        async with session_scope() as s:
            remaining = await list_transactions(s, 8105)
            assert remaining == []

    _run(run)


def test_record_transaction_accepts_note():
    async def run():
        await _make_user(8106)
        async with session_scope() as s:
            await record_transaction(
                s, user_id=8106, internal_id="N", side="buy",
                amount=Decimal("100"), price=Decimal("100"), currency="BYN",
                note="manual",
            )
        async with session_scope() as s:
            rows = await list_transactions(s, 8106)
            assert rows[0].note == "manual"

    _run(run)
