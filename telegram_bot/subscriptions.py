"""Subscriptions for the Telegram bot, powered by Telegram Stars.

A single source of truth (`users.subscription_tier`) is shared between the bot
and the future web app. The bot links a Telegram user to a `users` row via the
`telegram_id` column (see alembic a1b2c3d4e5f0). Pro/Enterprise tiers are
granted by Stars payments handled in `telegram_bot.stars_payments`.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.db import session_scope
from scraper.orm import UserORM

# --- Plans (paid via Telegram Stars) ---------------------------------------
# Free tier is implicit (no payment). Stars amounts are configurable via env.
PRO_STARS = int(os.environ.get("STARS_PRO", "150"))
ENT_STARS = int(os.environ.get("STARS_ENTERPRISE", "500"))


@dataclass(frozen=True)
class StarPlan:
    tier: str
    name: str
    stars: int
    duration_days: int
    blurb: str


STAR_PLANS: dict[str, StarPlan] = {
    "pro": StarPlan(
        tier="pro",
        name="Pro",
        stars=PRO_STARS,
        duration_days=30,
        blurb="Вся аналитика Desk, рекомендации, портфель, ML-прогнозы и алерты.",
    ),
    "enterprise": StarPlan(
        tier="enterprise",
        name="Enterprise",
        stars=ENT_STARS,
        duration_days=30,
        blurb="Всё из Pro + максимальные лимиты и приоритетная поддержка.",
    ),
}

# Free trial duration for new users (in days)
TRIAL_DAYS = int(os.environ.get("TRIAL_DAYS", "7"))

FREE_TIER = "free"
_PAID_TIERS = ("pro", "enterprise")
# Tiers ordered by capability (free < pro < enterprise).
_TIER_RANK = {"free": 0, "pro": 1, "enterprise": 2}


def is_paid(tier: str) -> bool:
    return tier in _PAID_TIERS


def tier_rank(tier: str) -> int:
    return _TIER_RANK.get(tier, 0)


def meets_tier(actual: str, required: str) -> bool:
    """True if `actual` tier is at least as capable as `required`."""
    return tier_rank(actual) >= tier_rank(required)


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(dt: datetime | None) -> datetime | None:
    """Normalise possibly naive datetimes (SQLite loses tzinfo) to UTC-aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def effective_tier(tier: str | None, expires_at: datetime | None, trial_end: datetime | None = None) -> str:
    """Return the tier the user is *actually* entitled to right now.

    Paid tiers lapse to ``free`` once ``expires_at`` is in the past. Because
    Stars payments in aiogram 3.29 are one-off (no ``subscription_period``),
    every purchase grants a fixed ``duration_days`` window; expiry is enforced
    here so the bot and web stay consistent without a background job.

    If the user has no active paid tier but has an active trial (``trial_end``
    is in the future), they are treated as ``pro`` during the trial period.
    """
    tier = tier or FREE_TIER
    if is_paid(tier):
        exp = _as_aware(expires_at)
        if exp is not None and exp <= _now():
            return FREE_TIER
        return tier
    # Free or expired — check for active trial
    trial = _as_aware(trial_end)
    if trial is not None and trial > _now():
        return "pro"
    return tier


async def get_or_create_user_by_telegram(
    session: AsyncSession,
    telegram_id: int,
    name: str | None = None,
    username: str | None = None,
) -> UserORM:
    existing = (
        await session.execute(select(UserORM).where(UserORM.telegram_id == telegram_id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    display = name or username or f"tg_{telegram_id}"
    user = UserORM(
        email=f"tg_{telegram_id}@telegram.local",
        name=display,
        telegram_id=telegram_id,
        subscription_tier=FREE_TIER,
        trial_end=_now() + timedelta(days=TRIAL_DAYS),
        role="user",
        is_active=True,
        is_verified=False,
    )
    session.add(user)
    await session.flush()
    return user


async def get_tier_by_telegram(telegram_id: int) -> str:
    """Return the *effective* tier (expiry-aware) for a Telegram user."""
    async with session_scope() as session:
        user = (
            await session.execute(select(UserORM).where(UserORM.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if user is None:
            return FREE_TIER
        return effective_tier(user.subscription_tier, user.subscription_expires_at, user.trial_end)


def _days_left(dt: datetime | None) -> int | None:
    """Whole days remaining until ``dt`` (rounded up), or ``None``/0 in the past."""
    dt = _as_aware(dt)
    if dt is None:
        return None
    delta = dt - _now()
    if delta.total_seconds() <= 0:
        return 0
    return max(1, math.ceil(delta.total_seconds() / 86400))


@dataclass(frozen=True)
class AccountStatus:
    tier: str            # effective tier right now (free / pro / enterprise)
    is_trial: bool       # True if access comes from the free trial
    days_left: int | None  # days until trial/paid access ends
    expires_at: datetime | None


async def get_account_status(telegram_id: int) -> AccountStatus:
    """Account snapshot for onboarding banners and /status.

    Creates the user row on first contact (which starts the trial clock), then
    reports the effective tier and how long access lasts.
    """
    async with session_scope() as session:
        user = await get_or_create_user_by_telegram(session, telegram_id)
        tier = effective_tier(user.subscription_tier, user.subscription_expires_at, user.trial_end)
        if is_paid(user.subscription_tier) and tier != FREE_TIER:
            expires = _as_aware(user.subscription_expires_at)
            return AccountStatus(tier, False, _days_left(expires), expires)
        if tier == "pro":  # entitled via trial
            expires = _as_aware(user.trial_end)
            return AccountStatus(tier, True, _days_left(expires), expires)
        return AccountStatus(FREE_TIER, False, None, None)


async def set_tier_by_telegram(
    telegram_id: int,
    tier: str,
    *,
    duration_days: int | None = None,
    charge_id: str | None = None,
) -> bool:
    """Grant `tier` to a Telegram user.

    Returns ``True`` if the tier was applied, ``False`` if the payment was a
    duplicate (same ``charge_id`` already processed) — this makes
    ``successful_payment`` handling idempotent against Telegram redelivery.
    Paid tiers get an expiry ``duration_days`` in the future.
    """
    async with session_scope() as session:
        user = (
            await session.execute(select(UserORM).where(UserORM.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if user is None:
            user = await get_or_create_user_by_telegram(session, telegram_id)
        if charge_id and user.last_charge_id == charge_id:
            logger.info("stars_payment_duplicate_ignored", telegram_id=telegram_id, charge_id=charge_id)
            return False
        user.subscription_tier = tier
        if is_paid(tier) and duration_days:
            base = _as_aware(user.subscription_expires_at)
            # Extend from the later of "now" or an existing unexpired window.
            start = base if base and base > _now() else _now()
            user.subscription_expires_at = start + timedelta(days=duration_days)
        elif not is_paid(tier):
            user.subscription_expires_at = None
        if charge_id:
            user.last_charge_id = charge_id
        await session.flush()
    logger.info(
        "subscription_tier_updated",
        telegram_id=telegram_id,
        tier=tier,
        duration_days=duration_days,
    )
    return True


async def clear_subscription_by_telegram(telegram_id: int, charge_id: str | None = None) -> None:
    """Revoke a paid subscription (e.g. after a Stars refund)."""
    async with session_scope() as session:
        user = (
            await session.execute(select(UserORM).where(UserORM.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if user is None:
            return
        # Only revoke if the refunded charge matches the active one (or no id given).
        if charge_id and user.last_charge_id and user.last_charge_id != charge_id:
            return
        user.subscription_tier = FREE_TIER
        user.subscription_expires_at = None
        user.last_charge_id = None
        # A refund fully revokes access — also drop any promotional trial so the
        # user does not silently keep `pro` via the trial window.
        user.trial_end = None
        await session.flush()
    logger.info("subscription_revoked", telegram_id=telegram_id, charge_id=charge_id)
