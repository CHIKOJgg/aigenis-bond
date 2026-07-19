"""Доставка алертов: Telegram (пользователям) и партнёрские webhook-и.

Единая точка, через которую проходят обе ветки алертов проекта:

* системные алерты мониторинга (``AlertORM``) — доставляются партнёрам через
  webhook-событие ``alert.triggered`` (пользователя у системного алерта нет);
* пользовательские правила (``AlertEventORM``) — доставляются в Telegram
  владельцу правила и, при наличии подписок, партнёрам через ``alert.triggered``.

Всё best-effort: сбой доставки логируется, но не ломает основной поток
формирования алертов.
"""

from __future__ import annotations

from scraper.config import get_settings
from scraper.logging import get_logger
from scraper.orm import UserORM

logger = get_logger("notifications.delivery")

_WEBHOOK_EVENT = "alert.triggered"


async def deliver_telegram(user_id: int, text: str) -> bool:
    """Отправить сообщение пользователю в Telegram. True — при успехе."""
    token = get_settings().telegram.bot_token
    if not token:
        return False
    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from sqlalchemy import select

        from scraper.db import session_scope

        async with session_scope() as session:
            user = (
                await session.execute(select(UserORM).where(UserORM.id == user_id))
            ).scalar_one_or_none()
        if user is None or user.telegram_id is None:
            return False
        bot = Bot(token=token, default=DefaultBotProperties(parse_mode="HTML"))
        try:
            await bot.send_message(chat_id=user.telegram_id, text=text)
            return True
        finally:
            await bot.session.close()
    except Exception as exc:  # pragma: no cover - network / dependency dependent
        logger.warning("telegram_delivery_failed", user_id=user_id, error=str(exc))
        return False


async def emit_partner_alert(
    *,
    kind: str,
    title: str,
    message: str,
    internal_id: str | None = None,
    alert_id: int | None = None,
    wait: bool = True,
) -> int:
    """Отправить партнёрам webhook-событие ``alert.triggered``.

    Возвращает число webhook-подписок, которым событие было разослано.
    """
    payload: dict = {"kind": kind, "title": title, "message": message}
    if internal_id is not None:
        payload["internal_id"] = internal_id
    if alert_id is not None:
        payload["alert_id"] = alert_id
    try:
        from api.partner.webhooks import emit_webhook_event

        return await emit_webhook_event(_WEBHOOK_EVENT, payload, wait=wait)
    except Exception as exc:  # pragma: no cover - dependency / network dependent
        logger.warning("partner_alert_emit_failed", kind=kind, error=str(exc))
        return 0
