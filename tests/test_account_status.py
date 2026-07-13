"""Tests for account status / onboarding trial logic and the /status callback."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, UserORM
from telegram_bot.subscriptions import (
    _days_left,
    get_account_status,
    get_or_create_user_by_telegram,
    set_tier_by_telegram,
)


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _run(coro_fn):
    async def wrapper():
        await _ensure_schema()
        try:
            await coro_fn()
        finally:
            await dispose()

    asyncio.run(wrapper())


def test_days_left_rounds_up_and_handles_past():
    assert _days_left(None) is None
    assert _days_left(datetime.now(UTC) - timedelta(days=1)) == 0
    assert _days_left(datetime.now(UTC) + timedelta(days=3, hours=1)) == 4
    assert _days_left(datetime.now(UTC) + timedelta(hours=2)) == 1


def test_new_user_gets_pro_trial():
    async def run():
        status = await get_account_status(4242)
        assert status.tier == "pro"
        assert status.is_trial is True
        assert status.days_left == 7

    _run(run)


def test_paid_user_is_not_trial():
    async def run():
        await get_account_status(4343)  # create with trial
        await set_tier_by_telegram(4343, "pro", duration_days=30)
        status = await get_account_status(4343)
        assert status.tier == "pro"
        assert status.is_trial is False
        assert status.days_left == 30

    _run(run)


def test_expired_trial_falls_back_to_free():
    async def run():
        await get_account_status(4444)
        async with session_scope() as s:
            user = (
                await s.execute(select(UserORM).where(UserORM.telegram_id == 4444))
            ).scalar_one()
            user.trial_end = datetime.now(UTC) - timedelta(days=1)
            user.subscription_tier = "free"
        status = await get_account_status(4444)
        assert status.tier == "free"
        assert status.is_trial is False
        assert status.days_left is None

    _run(run)


def test_get_or_create_is_idempotent():
    async def run():
        async with session_scope() as s:
            u1 = await get_or_create_user_by_telegram(s, 4545)
            first_id = u1.id
        async with session_scope() as s:
            u2 = await get_or_create_user_by_telegram(s, 4545)
            assert u2.id == first_id

    _run(run)
