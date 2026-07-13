"""Сервис проверки пользовательских алертов.

Периодически (по расписанию / вручную через ``python -m scraper alerts-check``)
сверяет активные правила с актуальными котировками, сохраняет срабатывания в
``alert_events`` и, при наличии настроенного Telegram-бота, отправляет
пользователю уведомление. Дедуп — не чаще одного события в 24 часа на правило,
чтобы не спамить при удержании порога.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from notifications.alerts_repository import (
    list_active_rules,
    mark_rule_triggered,
    record_event,
)
from scraper.config import get_settings
from scraper.db import session_scope
from scraper.logging import get_logger
from scraper.orm import AlertEventORM, BondORM, UserORM

logger = get_logger("alerts.service")

_DEDUP_WINDOW = timedelta(hours=24)


def _current_value(orm_bond: BondORM, metric: str) -> Decimal | None:
    if metric == "price":
        return orm_bond.price
    if metric == "ytm":
        return orm_bond.yield_to_maturity
    return None


def _build_message(rule: object, value: Decimal) -> str:
    verb = "выросла" if rule.direction == "above" else "упала"  # type: ignore[attr-defined]
    metric_name = "Цена" if rule.metric == "price" else "Доходность"  # type: ignore[attr-defined]
    return (
        f"🔔 {metric_name} {rule.internal_id} {verb} до {value:.2f} "  # type: ignore[attr-defined]
        f"(порог {rule.threshold:.2f})"  # type: ignore[attr-defined]
    )


def _is_fired(rule: object, value: Decimal | None) -> tuple[bool, str | None]:
    if value is None:
        return False, None
    direction = rule.direction  # type: ignore[attr-defined]
    threshold = rule.threshold  # type: ignore[attr-defined]
    if direction == "above":
        ok = value >= threshold
    elif direction == "below":
        ok = value <= threshold
    else:
        return False, None
    if not ok:
        return False, None
    return True, _build_message(rule, value)


async def _deliver(user_id: int, text: str) -> bool:
    """Best-effort Telegram-уведомление. Возвращает True при успешной отправке."""
    token = get_settings().telegram.bot_token
    if not token:
        return False
    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties

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
    except Exception as exc:  # pragma: no cover - network/dependency dependent
        logger.warning("alert_delivery_failed", user_id=user_id, error=str(exc))
        return False


async def run_alert_checks() -> int:
    """Проверить все активные правила; вернуть число новых срабатываний."""
    async with session_scope() as session:
        rules = await list_active_rules(session)
        if not rules:
            return 0
        bonds = (await session.execute(select(BondORM))).scalars().all()
        by_id = {b.internal_id: b for b in bonds}

        recent = (
            await session.execute(
                select(AlertEventORM.rule_id).where(
                    AlertEventORM.created_at >= datetime.now(UTC) - _DEDUP_WINDOW
                )
            )
        ).scalars().all()
        recent_rules = set(recent)

        fired = 0
        for rule in rules:
            bond = by_id.get(rule.internal_id)
            if bond is None:
                continue
            value = _current_value(bond, rule.metric)
            is_fired, message = _is_fired(rule, value)
            if not is_fired:
                continue
            if rule.id in recent_rules:
                await mark_rule_triggered(session, rule.id, value)
                continue
            event = await record_event(
                session,
                user_id=rule.user_id,
                rule_id=rule.id,
                internal_id=rule.internal_id,
                metric=rule.metric,
                message=message,
                value=value,
            )
            await mark_rule_triggered(session, rule.id, value)
            delivered = await _deliver(rule.user_id, message)
            if delivered:
                from sqlalchemy import update

                await session.execute(
                    update(AlertEventORM)
                    .where(AlertEventORM.id == event.id)
                    .values(delivered=True)
                )
            fired += 1
        logger.info("alert_checks_done", fired=fired, rules=len(rules))
        return fired
