"""Regression tests for audit-driven fixes:

1. Bot referral must never (re)arm a trial from scratch — otherwise throwaway
   Telegram accounts would farm unlimited Pro access (monetization bypass).
   Mirrors the web behavior in api/auth/service.py:_grant_referral_bonus.
2. YooKassa webhook replay: a redelivered payment.succeeded for an older
   payment (after a newer purchase) must NOT extend the subscription again.
3. Regular web users get a shareable referral_code (web referral program).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from scraper.db import session_scope
from scraper.orm import UserORM


def _run(coro):
    return asyncio.run(coro)


def _aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def _make_user(
    email: str,
    *,
    telegram_id: int | None = None,
    trial_end: datetime | None = None,
    expires_at: datetime | None = None,
    tier: str = "free",
) -> UserORM:
    async with session_scope() as s:
        u = UserORM(
            email=email,
            password_hash="x",
            name=email,
            telegram_id=telegram_id,
            subscription_tier=tier,
            subscription_expires_at=expires_at,
            trial_end=trial_end,
            is_active=True,
        )
        s.add(u)
        await s.flush()
        return u


# --------------------------------------------------------------------------- #
# 1. Bot referral farming
# --------------------------------------------------------------------------- #
def test_referral_never_rearms_expired_trial():
    """Referrer with no active window must NOT get a fresh trial."""
    from telegram_bot.subscriptions import attach_referrer

    async def scenario():
        referrer = await _make_user(
            "ref@farm.io",
            telegram_id=1001,
            trial_end=datetime.now(UTC) - timedelta(days=5),  # expired
        )
        await _make_user("inv@farm.io", telegram_id=1002)
        await attach_referrer(1002, referrer.id)
        async with session_scope() as s:
            ref = (
                await s.execute(
                    __import__("sqlalchemy").select(UserORM).where(UserORM.id == referrer.id)
                )
            ).scalar_one()
            assert _aware(ref.trial_end) is not None
            # Trial must NOT have been re-armed: still the original expired date.
            assert _aware(ref.trial_end) <= datetime.now(UTC)
            assert ref.subscription_tier == "free"

    _run(scenario())


def test_referral_extends_only_active_window():
    """Referrer with an ACTIVE trial gets it extended by the bonus days."""
    from telegram_bot.subscriptions import attach_referrer

    async def scenario():
        now = datetime.now(UTC)
        referrer = await _make_user(
            "ref2@farm.io",
            telegram_id=2001,
            trial_end=now + timedelta(days=2),
        )
        # Invitee is created like the bot does: fresh user with a 7-day trial.
        invitee = await _make_user(
            "inv2@farm.io",
            telegram_id=2002,
            trial_end=now + timedelta(days=7),
        )
        await attach_referrer(2002, referrer.id)
        async with session_scope() as s:
            ref = (
                await s.execute(
                    __import__("sqlalchemy").select(UserORM).where(UserORM.id == referrer.id)
                )
            ).scalar_one()
            import os

            bonus = int(os.getenv("REFERRAL_BONUS_DAYS", "3"))
            assert _aware(ref.trial_end) is not None
            assert _aware(ref.trial_end) >= now + timedelta(days=2 + bonus) - timedelta(minutes=1)
            inv = (
                await s.execute(
                    __import__("sqlalchemy").select(UserORM).where(UserORM.id == invitee.id)
                )
            ).scalar_one()
            assert _aware(inv.trial_end) is not None and _aware(inv.trial_end) > now + timedelta(days=7) - timedelta(minutes=1)

    _run(scenario())


# --------------------------------------------------------------------------- #
# 2. YooKassa replay guard
# --------------------------------------------------------------------------- #
def test_yookassa_replay_old_payment_does_not_extend():
    """Redelivery of an OLD payment.succeeded after a newer purchase must be ignored."""
    from api import billing as billing_pkg

    billing_service = billing_pkg.service
    import json

    from api.billing.service import handle_webhook

    async def scenario():
        uid = await _make_user("replay@io")

        async def fake_fetch_payment(pid):
            return {
                "id": pid,
                "status": "succeeded",
                "amount": {"value": "29.00", "currency": "BYN"},
                "metadata": {"user_id": str(uid.id), "plan": "pro"},
            }

        original = billing_service.fetch_payment
        billing_service.fetch_payment = fake_fetch_payment
        try:
            # Payment X succeeds -> activates subscription (30 days).
            body = json.dumps(
                {"event": "payment.succeeded", "object": {"id": "pay-OLD", "status": "succeeded"}}
            ).encode()
            await handle_webhook(body)

            async with session_scope() as s:
                u1 = (
                    await s.execute(
                        __import__("sqlalchemy").select(UserORM).where(UserORM.id == uid.id)
                    )
                ).scalar_one()
                expires_after_first = u1.subscription_expires_at
                assert u1.subscription_tier == "pro"

            body_y = json.dumps(
                {"event": "payment.succeeded", "object": {"id": "pay-NEW", "status": "succeeded"}}
            ).encode()
            await handle_webhook(body_y)

            async with session_scope() as s:
                u2 = (
                    await s.execute(
                        __import__("sqlalchemy").select(UserORM).where(UserORM.id == uid.id)
                    )
                ).scalar_one()
                expires_after_second = u2.subscription_expires_at

                # Now YooKassa REDELIVERS the old payment X — must be skipped.
                await handle_webhook(body)

                u3 = (
                    await s.execute(
                        __import__("sqlalchemy").select(UserORM).where(UserORM.id == uid.id)
                    )
                ).scalar_one()
                assert u3.subscription_expires_at == expires_after_second
                assert u3.subscription_expires_at > expires_after_first
        finally:
            billing_service.fetch_payment = original

    _run(scenario())


def test_yookassa_replay_duplicate_delivery_skipped():
    """The very same payment.succeeded redelivered twice must not double-extend."""
    from api import billing as billing_pkg

    billing_service = billing_pkg.service
    import json

    from api.billing.service import handle_webhook

    async def scenario():
        uid = await _make_user("replay2@io")

        async def fake_fetch_payment(pid):
            return {
                "id": pid,
                "status": "succeeded",
                "amount": {"value": "29.00", "currency": "BYN"},
                "metadata": {"user_id": str(uid.id), "plan": "pro"},
            }

        original = billing_service.fetch_payment
        billing_service.fetch_payment = fake_fetch_payment
        try:
            body = json.dumps(
                {"event": "payment.succeeded", "object": {"id": "pay-DUP", "status": "succeeded"}}
            ).encode()
            await handle_webhook(body)
            await handle_webhook(body)  # redelivery

            async with session_scope() as s:
                u = (
                    await s.execute(
                        __import__("sqlalchemy").select(UserORM).where(UserORM.id == uid.id)
                    )
                ).scalar_one()
                assert u.subscription_tier == "pro"
                assert u.subscription_expires_at is not None
        finally:
            billing_service.fetch_payment = original

    _run(scenario())


# --------------------------------------------------------------------------- #
# 3. Web referral codes for regular users
# --------------------------------------------------------------------------- #
def test_register_generates_referral_code():
    from api.auth.service import register_user

    async def scenario():
        async with session_scope() as s:
            user, err = await register_user(s, "webcode@io", "Str0ngPass1", "Web User")
            assert err is None
            assert user.referral_code and len(user.referral_code) == 10
            assert "/" not in user.referral_code

    _run(scenario())


def test_referral_stats_endpoint_returns_user_code():
    from api.auth.service import register_user
    from api.partner.router import partner_referral_stats

    async def scenario():
        async with session_scope() as s:
            user, _ = await register_user(s, "webcode2@io", "Str0ngPass1", "Web User 2")
            stats = await partner_referral_stats(user.id)
            assert stats.referral_code == user.referral_code
            assert stats.total_referrals == 0

    _run(scenario())


def test_register_with_user_referral_code_rewards_referrer():
    from api.auth.service import register_user

    async def scenario():
        async with session_scope() as s:
            referrer, _ = await register_user(s, "refweb@io", "Str0ngPass1", "Ref Web")
            assert referrer.referral_code
            trial_before = referrer.trial_end
            friend, _ = await register_user(
                s, "friend@io", "Str0ngPass1", "Friend", referral_code=referrer.referral_code
            )
            assert friend.referred_by == referrer.id
            async with session_scope() as s2:
                from sqlalchemy import select as sa_select

                ref2 = (
                    await s2.execute(sa_select(UserORM).where(UserORM.id == referrer.id))
                ).scalar_one()
                assert ref2.trial_end is not None
                assert ref2.trial_end > trial_before

    _run(scenario())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
