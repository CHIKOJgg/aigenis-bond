from __future__ import annotations

import contextlib
import time
import uuid
from collections import defaultdict

from aiogram.dispatcher.middlewares.base import BaseMiddleware

from scraper import repositories
from scraper.db import session_scope

# Команды, доступные всегда (до и после парсинга)
ALLOWED_BEFORE_PARSE = {
    "start",
    "help",
    "menu",
    "parse",
    "subscribe",
    "rates",
    "status",
    "renew",
    "refer",
}


async def db_has_bonds() -> bool:
    """True, если в БД есть хотя бы одна облигация (признак завершённого парсинга)."""
    async with session_scope() as session:
        count = await repositories.bonds.count_bonds(session)
    return count > 0


def locked_message_text() -> str:
    return (
        "⏳ Котировки ещё загружаются.\n"
        "Откройте /start и нажмите «🔄 Обновить данные» — через минуту всё будет готово."
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
            # Payment events must NEVER be dropped — a throttled
            # successful_payment would silently fail to grant the subscription.
            if (
                getattr(event, "successful_payment", None) is not None
                or getattr(event, "refunded_payment", None) is not None
            ):
                return await handler(event, data)
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
    "rv",
    "duration",
    "carry",
    "repo",
    "stress",
    "buy",
    "predict",
    "ml",
    "rebalance",
    "rebalance_auto",
    "portfolio",
    "forecast",
    "scenario",
    "desk_status",
    "desk_spreads",
    "alerts",
}

# Commands always allowed regardless of tier (free market overview + account).
_ALWAYS_ALLOWED = {
    "start",
    "help",
    "menu",
    "parse",
    "subscribe",
    "rates",
    "curve",
    "status",
    "top",
    "usd",
    "byn",
    "metals",
    "new",
    "stats",
    "settings",
    "set",
    "cancel",
    "watchlist",
    "watch",
    "unwatch",
    "desk",
    "overview",
    "renew",
    "refer",
}


def _subscription_upsell() -> str:
    return (
        "⭐ <b>Эта функция доступна в подписке Pro / Enterprise.</b>\n\n"
        "Откройте аналитику Desk, рекомендации, портфель, ML-прогнозы и алерты "
        "по подписке через Telegram Stars.\n"
        "Нажмите /subscribe, чтобы выбрать тариф."
    )


async def user_has_pro_tier(uid: int) -> bool:
    """True when the Telegram user holds an active Pro/Enterprise tier."""
    from telegram_bot.subscriptions import get_tier_by_telegram

    tier = await get_tier_by_telegram(uid)
    return tier in ("pro", "enterprise")


async def gate_pro_callback(callback_query) -> bool:
    """Gate an inline-button press behind the Pro tier.

    Inline buttons dispatch handlers directly, bypassing the message
    SubscriptionMiddleware, so every Pro button must go through this gate.
    Replies with an alert + upsell when denied; returns True to proceed.
    """
    user = getattr(callback_query, "from_user", None)
    uid = user.id if user else 0
    if await user_has_pro_tier(uid):
        return True
    with contextlib.suppress(Exception):  # pragma: no cover - never break the bot
        await callback_query.answer("⭐ Доступно в Pro / Enterprise", show_alert=True)
        await callback_query.message.answer(_subscription_upsell(), parse_mode="HTML")
    return False


class SubscriptionMiddleware(BaseMiddleware):
    """Блокирует PRO_COMMANDS для пользователей с тарифом free.

    Тариф хранится в users.subscription_tier и связан с Telegram через
    telegram_id (см. telegram_bot.subscriptions). Грантится оплатой Stars.
    Внимание: inline-кнопки этот middleware не видят — их гейтит
    telegram_bot.middleware.gate_pro_callback в callback-мостах.
    """

    async def __call__(self, handler, event, data):
        message = event
        text = getattr(message, "text", None)
        if not text or not text.startswith("/"):
            return await handler(event, data)

        cmd = text.split(maxsplit=1)[0].lstrip("/").lower().split("@")[0]
        # Normalize separators: users type /rebalance-auto, callbacks use
        # rebalance_auto — both must map to the same gate (prevents bypass).
        cmd = cmd.replace("-", "_")
        if cmd in _ALWAYS_ALLOWED or cmd not in PRO_COMMANDS:
            return await handler(event, data)

        user = getattr(message, "from_user", None)
        uid = user.id if user else 0
        if await user_has_pro_tier(uid):
            return await handler(event, data)

        await message.answer(_subscription_upsell(), parse_mode="HTML")
        return
