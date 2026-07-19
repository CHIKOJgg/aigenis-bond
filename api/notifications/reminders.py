"""Expiring trial / subscription reminders (email + Telegram).

Run from the scheduler (``scraper.scheduler``) once per day. Sends a reminder
3 and 1 day before a user's trial or paid subscription expires. Telegram
delivery reuses the live bot instance registered by ``telegram_bot.bot.main``
via ``telegram_bot._bot_instance``.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from scraper.db import session_scope
from scraper.logging import get_logger
from scraper.orm import UserORM

logger = get_logger("api.reminders")

# Days before expiry to send a reminder.
_REMINDER_DAYS = (3, 1)


def _days_until(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = dt - datetime.now(UTC)
    if delta.total_seconds() <= 0:
        return 0
    return max(1, (delta.total_seconds() + 86399) // 86400)


async def notify_expiring_trials() -> int:
    """Send reminders to users whose trial/subscription expires soon.

    Returns the number of reminders sent.
    """
    now = datetime.now(UTC)
    sent = 0
    async with session_scope() as session:
        users = (
            await session.execute(select(UserORM).where(UserORM.is_active.is_(True)))
        ).scalars().all()

        # Resolve the live Telegram bot, if registered.
        bot = _get_bot()
        reminders: list[tuple[UserORM, int, str]] = []
        for u in users:
            targets = []
            if u.trial_end and (u.subscription_tier == "free"):
                targets.append((u.trial_end, "Pro (trial)"))
            if u.subscription_tier in ("pro", "enterprise") and u.subscription_expires_at:
                targets.append((u.subscription_expires_at, u.subscription_tier.capitalize()))
            for exp, tier_label in targets:
                dleft = _days_until(exp)
                if dleft in _REMINDER_DAYS:
                    reminders.append((u, dleft, tier_label))

        for u, dleft, tier_label in reminders:
            # Email reminder.
            if u.email:
                try:
                    from api.notifications.email import send_subscription_expiring_email

                    send_subscription_expiring_email(u.email, tier_label, dleft)
                except Exception as exc:
                    logger.warning("reminder_email_failed", user=u.id, error=str(exc))
            # Telegram reminder.
            if bot is not None and u.telegram_id:
                try:
                    await bot.send_message(
                        chat_id=u.telegram_id,
                        text=(
                            f"⏳ <b>Напоминание</b>\n\n"
                            f"Ваш доступ уровня <b>{tier_label}</b> истекает через "
                            f"<b>{dleft} дн.</b>. Продлите подписку, чтобы не потерять "
                            f"аналитику:\n/subscribe"
                        ),
                    )
                except Exception as exc:
                    logger.warning("reminder_tg_failed", user=u.id, error=str(exc))
            sent += 1
    logger.info("reminders_sent", count=sent)
    return sent


def _get_bot():
    try:
        from telegram_bot._bot_instance import get_bot

        return get_bot()
    except Exception:
        return None
