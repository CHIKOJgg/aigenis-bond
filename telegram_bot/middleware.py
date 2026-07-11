from __future__ import annotations

import contextlib
import time
import uuid
from collections import defaultdict

from aiogram.dispatcher.middlewares.base import BaseMiddleware

from scraper import repositories
from scraper.db import session_scope

# Команды, доступные всегда (до и после парсинга)
ALLOWED_BEFORE_PARSE = {"start", "help", "menu", "parse", "subscribe", "rates"}


async def db_has_bonds() -> bool:
    """True, если в БД есть хотя бы одна облигация (признак завершённого парсинга)."""
    async with session_scope() as session:
        count = await repositories.bonds.count_bonds(session)
    return count > 0


def locked_message_text() -> str:
    return (
        "🔒 База облигаций пуста.\n"
        "Сначала запустите парсинг командой /parse (или кнопкой 🚀 Старт парсинга), "
        "после этого станут доступны остальные команды."
    )


class ParseLockMiddleware(BaseMiddleware):
    """Блокирует все команды, кроме разрешённых, пока облигации не загружены в БД.

    Проверка опирается на БД (наличие облигаций), а не на in-memory состояние,
    поэтому корректно работает после перезапуска процесса и между сервисами.
    """

    async def __call__(self, handler, event, data):
        message = event
        text = getattr(message, "text", None)
        if not text or not text.startswith("/"):
            return await handler(event, data)

        cmd = text.split(maxsplit=1)[0].lstrip("/").lower().split("@")[0]
        if cmd in ALLOWED_BEFORE_PARSE:
            return await handler(event, data)

        if await db_has_bonds():
            return await handler(event, data)

        await message.answer(locked_message_text())
        return


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate: int = 3, per_seconds: int = 1) -> None:
        self.rate = rate
        self.per_seconds = per_seconds
        self._users: dict[int, list[float]] = defaultdict(list)

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user is not None:
            now = time.monotonic()
            uid = user.id
            timestamps = self._users[uid]
            cutoff = now - self.per_seconds
            timestamps[:] = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= self.rate:
                return
            timestamps.append(now)
        return await handler(event, data)


class RequestIdMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        data["request_id"] = uuid.uuid4().hex[:8]
        return await handler(event, data)


def _command_label(event) -> str:
    """Extract a stable command label for metrics ('/top a b' -> 'top')."""
    text = getattr(event, "text", None)
    if text and text.startswith("/"):
        return text.split(maxsplit=1)[0].lstrip("/").lower().split("@")[0]
    if getattr(event, "successful_payment", None) is not None:
        return "successful_payment"
    if getattr(event, "refunded_payment", None) is not None:
        return "refunded_payment"
    return "message"


class MetricsMiddleware(BaseMiddleware):
    """Emit Prometheus metrics for every handled message.

    Counts commands (`bot_commands_total`), errors (`bot_errors_total`) and
    latency (`bot_command_seconds`) so the bot is observable alongside the API.
    Metric failures never break message handling.
    """

    async def __call__(self, handler, event, data):
        from telegram_bot import metrics

        label = _command_label(event)
        with contextlib.suppress(Exception):  # pragma: no cover - metrics must never break the bot
            metrics.bot_commands.labels(command=label).inc()
        start = time.monotonic()
        try:
            return await handler(event, data)
        except Exception as exc:
            with contextlib.suppress(Exception):  # pragma: no cover
                metrics.bot_errors.labels(error_type=type(exc).__name__).inc()
            raise
        finally:
            with contextlib.suppress(Exception):  # pragma: no cover
                metrics.bot_latency.labels(command=label).observe(time.monotonic() - start)


# Commands that require a paid (Pro/Enterprise) subscription.
PRO_COMMANDS = {
    "rv", "duration", "carry", "repo", "stress",
    "buy", "predict", "ml",
    "rebalance", "rebalance_auto",
    "portfolio", "forecast", "scenario", "desk_status", "alerts",
}

# Commands always allowed regardless of tier (free market overview + account).
_ALWAYS_ALLOWED = {
    "start", "help", "menu", "parse", "subscribe", "rates", "curve",
    "top", "usd", "byn", "metals", "new", "stats",
    "settings", "set", "cancel", "watchlist", "watch", "unwatch",
}


def _subscription_upsell() -> str:
    return (
        "⭐ <b>Эта функция доступна в подписке Pro / Enterprise.</b>\n\n"
        "Откройте аналитику Desk, рекомендации, портфель, ML-прогнозы и алерты "
        "по подписке через Telegram Stars.\n"
        "Нажмите /subscribe, чтобы выбрать тариф."
    )


class SubscriptionMiddleware(BaseMiddleware):
    """Блокирует PRO_COMMANDS для пользователей с тарифом free.

    Тариф хранится в users.subscription_tier и связан с Telegram через
    telegram_id (см. telegram_bot.subscriptions). Грантится оплатой Stars.
    """

    async def __call__(self, handler, event, data):
        message = event
        text = getattr(message, "text", None)
        if not text or not text.startswith("/"):
            return await handler(event, data)

        cmd = text.split(maxsplit=1)[0].lstrip("/").lower().split("@")[0]
        if cmd in _ALWAYS_ALLOWED or cmd not in PRO_COMMANDS:
            return await handler(event, data)

        from telegram_bot.subscriptions import get_tier_by_telegram

        user = getattr(message, "from_user", None)
        uid = user.id if user else 0
        tier = await get_tier_by_telegram(uid)
        if tier in ("pro", "enterprise"):
            return await handler(event, data)

        await message.answer(_subscription_upsell(), parse_mode="HTML")
        return
