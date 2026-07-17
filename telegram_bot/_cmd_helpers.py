"""Shared pure helpers for the Telegram command handlers.

Extracted from ``telegram_bot/commands.py`` to keep that router module focused
on handler wiring rather than carrying every small helper inline.
"""

from __future__ import annotations

from aiogram.types import Message

from telegram_bot.middleware import db_has_bonds, locked_message_text


def user_id(message: Message) -> int:
    return message.from_user.id if message.from_user else 0


async def is_unlocked(message: Message) -> bool:  # noqa: ARG001 - mirrors original signature
    return await db_has_bonds()


def locked_message() -> str:
    return locked_message_text()


def account_banner(status) -> str | None:
    """Short line about the user's current access, shown on /start."""
    if status.is_trial and status.days_left:
        return (
            f"🎁 <b>Пробный Pro активен</b> — осталось {status.days_left} дн.\n"
            "Все функции открыты: аналитика, прогнозы, доход по купонам и алерты."
        )
    if status.tier in ("pro", "enterprise") and status.days_left:
        name = "Enterprise" if status.tier == "enterprise" else "Pro"
        return f"⭐ <b>Тариф {name}</b> — активен ещё {status.days_left} дн."
    return (
        "🔓 <b>Тариф Free.</b> Оформите Pro (/subscribe), чтобы открыть аналитику, "
        "ML-прогнозы, доход по купонам и персональные алерты."
    )
