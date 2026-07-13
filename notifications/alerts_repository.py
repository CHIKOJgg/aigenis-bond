"""Репозиторий пользовательских алертов (правила + срабатывания).

Правила создаёт сам пользователь (через API/бот): «цена облигации OP-51
упала ниже 95» или «доходность BYN-облигации выросла выше 12%». Сервис
проверки (notifications.alerts_service) периодически сверяет правила с
актуальными котировками и складывает срабатывания в ``alert_events`` —
отдельную ленту, не смешивая с системными алертами качества данных.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.orm import AlertEventORM, AlertRuleORM


async def create_rule(
    session: AsyncSession,
    *,
    user_id: int,
    internal_id: str,
    metric: str,
    direction: str,
    threshold: Decimal,
    note: str | None = None,
) -> AlertRuleORM:
    rule = AlertRuleORM(
        user_id=user_id,
        internal_id=internal_id,
        metric=metric,
        direction=direction,
        threshold=threshold,
        note=note,
        active=True,
    )
    session.add(rule)
    await session.flush()
    return rule


async def list_rules(
    session: AsyncSession, user_id: int, *, active_only: bool = True
) -> list[AlertRuleORM]:
    stmt = select(AlertRuleORM).where(AlertRuleORM.user_id == user_id)
    if active_only:
        stmt = stmt.where(AlertRuleORM.active.is_(True))
    stmt = stmt.order_by(AlertRuleORM.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_rule(session: AsyncSession, user_id: int, rule_id: int) -> bool:
    rule = (
        await session.execute(
            select(AlertRuleORM).where(
                AlertRuleORM.id == rule_id, AlertRuleORM.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if rule is None:
        return False
    await session.delete(rule)
    return True


async def list_active_rules(session: AsyncSession) -> list[AlertRuleORM]:
    result = await session.execute(
        select(AlertRuleORM).where(AlertRuleORM.active.is_(True))
    )
    return list(result.scalars().all())


async def record_event(
    session: AsyncSession,
    *,
    user_id: int,
    rule_id: int | None,
    internal_id: str,
    metric: str,
    message: str,
    value: Decimal | None,
) -> AlertEventORM:
    event = AlertEventORM(
        user_id=user_id,
        rule_id=rule_id,
        internal_id=internal_id,
        metric=metric,
        message=message,
        value=value,
        delivered=False,
    )
    session.add(event)
    await session.flush()
    return event


async def mark_rule_triggered(session: AsyncSession, rule_id: int, value: Decimal) -> None:
    from sqlalchemy import update

    await session.execute(
        update(AlertRuleORM)
        .where(AlertRuleORM.id == rule_id)
        .values(triggered_at=datetime.now(UTC), last_value=value)
    )


async def list_events(
    session: AsyncSession, user_id: int, *, limit: int = 50
) -> list[AlertEventORM]:
    result = await session.execute(
        select(AlertEventORM)
        .where(AlertEventORM.user_id == user_id)
        .order_by(AlertEventORM.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
