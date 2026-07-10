"""Subscriptions for the Telegram bot, powered by Telegram Stars.

A single source of truth (`users.subscription_tier`) is shared between the bot
and the future web app. The bot links a Telegram user to a `users` row via the
`telegram_id` column (see alembic a1b2c3d4e5f0). Pro/Enterprise tiers are
granted by Stars payments handled in `telegram_bot.stars_payments`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loguru import logger
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
    # Also handle the case where a web user row exists with the same telegram_id
    # but wasn't linked yet (not expected, but safe).
    display = name or username or f"tg_{telegram_id}"
    user = UserORM(
        email=f"tg_{telegram_id}@telegram.local",
        name=display,
        telegram_id=telegram_id,
        subscription_tier=FREE_TIER,
    )
    session.add(user)
    await session.flush()
    return user


async def get_tier_by_telegram(telegram_id: int) -> str:
    async with session_scope() as session:
        user = (
            await session.execute(select(UserORM).where(UserORM.telegram_id == telegram_id))
        ).scalar_one_or_none()
        return user.subscription_tier if user else FREE_TIER


async def set_tier_by_telegram(telegram_id: int, tier: str) -> None:
    async with session_scope() as session:
        user = (
            await session.execute(select(UserORM).where(UserORM.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if user is None:
            user = await get_or_create_user_by_telegram(session, telegram_id)
        user.subscription_tier = tier
        await session.flush()
    logger.info("subscription_tier_updated", telegram_id=telegram_id, tier=tier)
