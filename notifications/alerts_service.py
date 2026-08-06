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
from notifications.delivery import deliver_telegram, emit_partner_alert
from scraper.db import session_scope
from scraper.logging import get_logger
from scraper.orm import AlertEventORM, BondORM, StockORM

logger = get_logger("alerts.service")

_DEDUP_WINDOW = timedelta(hours=24)

_METRIC_LABELS = {
    "price": "Цена",
    "ytm": "Доходность",
    "pbr": "P/B",
    "pe": "P/E",
    "dividend_yield": "Див. доходность",
}


def _current_value(orm: object, metric: str) -> Decimal | None:
    if metric == "price":
        return getattr(orm, "price", None)
    if metric == "ytm":
        return getattr(orm, "yield_to_maturity", None)
    if metric == "pbr":
        return getattr(orm, "pbr_ratio", None)
    if metric == "pe":
        return getattr(orm, "pe_ratio", None)
    if metric == "dividend_yield":
        return getattr(orm, "dividend_yield", None)
    return None


def _build_message(rule: object, value: Decimal) -> str:
    verb = "вырос" if rule.direction == "above" else "упал"  # type: ignore[attr-defined]
    metric_name = _METRIC_LABELS.get(  # type: ignore[attr-defined]
        rule.metric,
        rule.metric,  # type: ignore[attr-defined]
    )
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
    return await deliver_telegram(user_id, text)


async def run_alert_checks() -> int:
    """Проверить все активные правила; вернуть число новых срабатываний."""
    async with session_scope() as session:
        rules = await list_active_rules(session)
        if not rules:
            return 0
        bonds = (await session.execute(select(BondORM))).scalars().all()
        stocks = (await session.execute(select(StockORM))).scalars().all()
        by_id = {b.internal_id: b for b in bonds}
        by_id.update({s.internal_id: s for s in stocks})

        recent = (
            (
                await session.execute(
                    select(AlertEventORM.rule_id).where(
                        AlertEventORM.created_at >= datetime.now(UTC) - _DEDUP_WINDOW
                    )
                )
            )
            .scalars()
            .all()
        )
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
                    update(AlertEventORM).where(AlertEventORM.id == event.id).values(delivered=True)
                )
            # B2B partners subscribed to alert.triggered also get the event.
            await emit_partner_alert(
                kind=f"user_rule:{rule.metric}:{rule.direction}",
                title=message.splitlines()[0] if message else "Alert",
                message=message,
                internal_id=rule.internal_id,
                alert_id=event.id,
            )
            fired += 1
        logger.info("alert_checks_done", fired=fired, rules=len(rules))
        return fired
