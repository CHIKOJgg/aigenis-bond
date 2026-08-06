"""Snapshot lineage persistence (plan item 5.6).

Каждый ingestion run пишет одну строку в ``snapshot_lineage`` с происхождением
данных: источник, идентификатор license/contract, as-of, ingestion_run и статус
качества. REST API (api/aigenis) затем читает последнюю запись для заголовков
``X-Data-As-Of`` / ``X-Data-Quality`` (plan item 5.13).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from scraper.logging import get_logger
from scraper.orm import SnapshotLineageORM

logger = get_logger("scraper.lineage")


async def record_snapshot_lineage(
    session: AsyncSession,
    *,
    source: str,
    as_of: datetime | None = None,
    ingestion_run: str | None = None,
    quality_status: str = "ok",
    market: str | None = None,
    rows_processed: int = 0,
    license_contract_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> SnapshotLineageORM:
    """Записать запись о происхождении данных snapshot.

    Возвращает созданную запись (после flush), чтобы вызывающий код мог
    использовать её id/время в последующих операциях.
    """
    row = SnapshotLineageORM(
        source=source,
        license_contract_id=license_contract_id,
        as_of=as_of or datetime.now(UTC),
        ingestion_run=ingestion_run,
        quality_status=quality_status,
        market=market,
        rows_processed=rows_processed,
    )
    session.add(row)
    await session.flush()
    if extra:
        logger.info("snapshot_lineage_recorded", source=source, **extra)
    return row


async def latest_lineage(session: AsyncSession) -> SnapshotLineageORM | None:
    """Последний зарегистрированный snapshot (по времени as_of)."""
    from sqlalchemy import select

    return (
        await session.execute(
            select(SnapshotLineageORM)
            .order_by(SnapshotLineageORM.as_of.desc(), SnapshotLineageORM.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
