"""Репозиторий для алертов (notifications)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.orm import AlertORM


def _to_orm(alert: dict[str, Any]) -> dict:
    return {
        "user_id": alert.get("user_id"),
        "kind": alert["kind"],
        "title": alert["title"],
        "message": alert["message"],
        "internal_id": alert.get("internal_id"),
        "payload": alert.get("payload"),
        "dedup_key": alert.get("dedup_key"),
    }


async def add_alert(session: AsyncSession, alert: dict[str, Any]) -> int | None:
    """Сохранить алерт с защитой от дублей по dedup_key (за последние 24ч)."""
    dedup_key = alert.get("dedup_key")
    if dedup_key:
        cutoff = datetime.now(UTC) - timedelta(hours=24)
        existing = await session.execute(
            select(AlertORM.id)
            .where(AlertORM.dedup_key == dedup_key)
            .where(AlertORM.created_at >= cutoff)
            .limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            return None
    values = _to_orm(alert)
    stmt = pg_insert(AlertORM).values(**values).returning(AlertORM.id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_recent(session: AsyncSession, limit: int = 50) -> list[AlertORM]:
    result = await session.execute(
        select(AlertORM).order_by(AlertORM.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def cleanup_old(session: AsyncSession, days: int = 30) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await session.execute(delete(AlertORM).where(AlertORM.created_at < cutoff))
    return int(result.rowcount or 0)
