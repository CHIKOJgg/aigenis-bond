"""Integration tests for the Telegram Stars subscription flow.

Uses an in-memory SQLite database (the project default) and a fake aiogram
``Message`` so no real Telegram/Bot is needed. Covers:

* expiry-aware effective tier;
* granting a tier with a duration window;
* idempotent ``successful_payment`` handling (duplicate charge id);
* refund revoking the subscription;
* the ``successful_payment`` handler end-to-end.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, UserORM
from telegram_bot import stars_payments
from telegram_bot import subscriptions as subs


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _run(coro_fn):
    """Run an async test body with a fresh in-memory engine per event loop."""
    import asyncio as _asyncio

    async def wrapper():
        await _ensure_schema()
        try:
            await coro_fn()
        finally:
            await dispose()

    _asyncio.run(wrapper())


# --- Pure expiry logic ------------------------------------------------------
def test_effective_tier_expiry():
    future = datetime.now(UTC) + timedelta(days=1)
    past = datetime.now(UTC) - timedelta(days=1)
    assert subs.effective_tier("free", None) == "free"
    assert subs.effective_tier("pro", future) == "pro"
    assert subs.effective_tier("pro", past) == "free"
    assert subs.effective_tier("pro", None) == "pro"
    # naive datetimes (SQLite) are treated as UTC
    assert subs.effective_tier("pro", past.replace(tzinfo=None)) == "free"


# --- Grant + idempotency ----------------------------------------------------
def test_grant_and_idempotent_charge():
    async def run():
        tg = 100_001
        async with session_scope() as s:
            await subs.get_or_create_user_by_telegram(s, tg)

        applied = await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-1")
        assert applied is True
        assert await subs.get_tier_by_telegram(tg) == "pro"

        # Duplicate delivery of the same charge must be ignored.
        applied_again = await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-1")
        assert applied_again is False

        async with session_scope() as s:
            user = (
                await s.execute(UserORM.__table__.select().where(UserORM.telegram_id == tg))
            ).first()
            assert user is not None

    _run(run)


def test_expiry_downgrades_effective_tier():
    async def run():
        tg = 100_002
        async with session_scope() as s:
            user = await subs.get_or_create_user_by_telegram(s, tg)
            user.subscription_tier = "pro"
            user.subscription_expires_at = datetime.now(UTC) - timedelta(days=1)
        # Stored tier is "pro" but it lapsed -> effective is "free".
        assert await subs.get_tier_by_telegram(tg) == "free"

    _run(run)


def test_refund_revokes_subscription():
    async def run():
        tg = 100_003
        async with session_scope() as s:
            await subs.get_or_create_user_by_telegram(s, tg)
        await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-refund")
        assert await subs.get_tier_by_telegram(tg) == "pro"

        await subs.clear_subscription_by_telegram(tg, charge_id="chg-refund")
        assert await subs.get_tier_by_telegram(tg) == "free"

    _run(run)


# --- Handler end-to-end -----------------------------------------------------
class _FakePayment:
    def __init__(self, payload: str, charge: str):
        self.invoice_payload = payload
        self.telegram_payment_charge_id = charge


class _FakeUser:
    def __init__(self, uid: int):
        self.id = uid


class _FakeMessage:
    def __init__(self, payment, uid: int = 100_004):
        self.successful_payment = payment
        self.refunded_payment = None
        self.from_user = _FakeUser(uid)
        self.answers: list = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


def test_successful_payment_handler_grants_and_dedupes():
    async def run():
        async with session_scope() as s:
            await subs.get_or_create_user_by_telegram(s, 100_004)

        msg = _FakeMessage(_FakePayment("stars_sub:pro", "chg-handler"))
        await stars_payments.on_successful_payment(msg)
        assert await subs.get_tier_by_telegram(100_004) == "pro"
        assert len(msg.answers) == 1

        # Same charge redelivered: no second confirmation message.
        msg2 = _FakeMessage(_FakePayment("stars_sub:pro", "chg-handler"))
        await stars_payments.on_successful_payment(msg2)
        assert len(msg2.answers) == 0

    _run(run)


def test_successful_payment_rejects_unknown_tier_payload():
    """A forged/unknown tier in the payload must not grant any default tier."""

    async def run():
        async with session_scope() as s:
            await subs.get_or_create_user_by_telegram(s, 100_005)

        msg = _FakeMessage(_FakePayment("stars_sub:ultra", "chg-forged"), uid=100_005)
        await stars_payments.on_successful_payment(msg)
        # No paid tier stored, no charge recorded, no confirmation sent.
        async with session_scope() as s:
            user = (
                await s.execute(
                    UserORM.__table__.select().where(UserORM.telegram_id == 100_005)
                )
            ).mappings().first()
        assert user["subscription_tier"] == "free"
        assert user["last_charge_id"] is None
        assert len(msg.answers) == 0

    _run(run)


def test_successful_payment_ignores_non_subscription_payload():
    async def run():
        async with session_scope() as s:
            await subs.get_or_create_user_by_telegram(s, 100_006)

        msg = _FakeMessage(_FakePayment("something_else", "chg-x"), uid=100_006)
        await stars_payments.on_successful_payment(msg)
        async with session_scope() as s:
            user = (
                await s.execute(
                    UserORM.__table__.select().where(UserORM.telegram_id == 100_006)
                )
            ).mappings().first()
        assert user["subscription_tier"] == "free"
        assert user["last_charge_id"] is None
        assert len(msg.answers) == 0

    _run(run)
