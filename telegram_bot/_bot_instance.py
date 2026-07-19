"""Shared handle to the running Telegram bot instance.

The bot is created inside ``telegram_bot.bot.main``; background jobs (scheduler,
reminders) need to reach it to push messages. We keep a single module-level
reference set at startup and cleared on shutdown.
"""
from __future__ import annotations

from typing import Optional

_bot = None


def set_bot(instance) -> None:
    global _bot
    _bot = instance


def get_bot():
    return _bot


def clear_bot() -> None:
    global _bot
    _bot = None
