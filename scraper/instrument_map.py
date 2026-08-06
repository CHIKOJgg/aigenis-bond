"""
Instrument mapping — связь идентификаторов инструментов.

DB-таблица ``instrument_map`` (см. ``scraper/orm/integration.py`` и миграцию
0028) хранит версионированное соответствие:
    aigenis_instrument_id -> isin -> external_ticker -> analytics_internal_id

Правила (Finalplan §13.6 / plan item 5.14):
- ISIN — предпочтительный стабильный ключ.
- Нельзя сопоставлять только по display name.
- Поддержка делистинга, переименования, дублей тикеров.
- Mapping версионирован и проверяем.
- Неизвестный инструмент возвращает ``not_covered``, не 500.

In-memory API (add_mapping / load_mappings / resolve_*) сохранён для
демо/тестов; производственные пути используют DB-функции ``*_db``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.logging import get_logger

logger = get_logger("scraper.instrument_map")


class InstrumentStatus(StrEnum):
    active = "active"
    delisted = "delisted"
    renamed = "renamed"
    not_covered = "not_covered"


class InstrumentMapping(BaseModel):
    """Запись в таблице сопоставления инструментов."""

    aigenis_instrument_id: str
    isin: str | None = None
    external_ticker: str | None = None
    market: str = "BCSE"
    currency: str | None = None
    analytics_internal_id: str | None = None
    status: InstrumentStatus = InstrumentStatus.active
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    version: int = 1


# In-memory mapping for demo/tests (DB table is the source of truth in prod).
_INSTRUMENT_MAP: dict[str, InstrumentMapping] = {}


def _row_to_mapping(row: Any) -> InstrumentMapping:
    return InstrumentMapping(
        aigenis_instrument_id=row.aigenis_instrument_id,
        isin=row.isin,
        external_ticker=row.external_ticker,
        market=row.market,
        currency=row.currency,
        analytics_internal_id=row.analytics_internal_id,
        status=InstrumentStatus(row.status or "active"),
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        version=row.version or 1,
    )


# ──────────────────────────────────────────────
# DB-backed repository (production path)
# ──────────────────────────────────────────────


async def upsert_mapping_db(
    session: AsyncSession, mapping: InstrumentMapping, *, new_version: bool = False
) -> InstrumentMapping:
    """Upsert записи по aigenis_instrument_id.

    При ``new_version=True`` и изменении целевого ``analytics_internal_id``
    предыдущая версия закрывается (valid_to=now), а новая вставляется с
    инкрементом ``version``. Уникальность построена на паре
    (aigenis_instrument_id, version) — история сохраняется.
    """
    from sqlalchemy import update as sa_update

    from scraper.db import upsert_row
    from scraper.orm import InstrumentMapORM

    now = datetime.now(UTC)
    existing = await resolve_aigenis_id_db(session, mapping.aigenis_instrument_id)
    next_version = max(mapping.version or 1, (existing.version if existing else 0) + 1)

    current: InstrumentMapping | None = existing
    changed = bool(
        new_version
        and current is not None
        and current.analytics_internal_id != mapping.analytics_internal_id
    )
    if changed and current is not None:
        # Закрыть текущую версию и открыть новую с инкрементом.
        await session.execute(
            sa_update(InstrumentMapORM)
            .where(InstrumentMapORM.aigenis_instrument_id == mapping.aigenis_instrument_id)
            .where(InstrumentMapORM.version == current.version)
            .values(valid_to=now)
        )
        next_version = current.version + 1

    values = {
        "aigenis_instrument_id": mapping.aigenis_instrument_id,
        "isin": mapping.isin,
        "external_ticker": mapping.external_ticker,
        "market": mapping.market,
        "currency": mapping.currency,
        "analytics_internal_id": mapping.analytics_internal_id,
        "status": mapping.status.value,
        "valid_from": mapping.valid_from if not changed else now,
        "valid_to": mapping.valid_to if not changed else None,
        "version": next_version,
    }
    await upsert_row(
        session,
        InstrumentMapORM,
        index_elements=["aigenis_instrument_id", "version"],
        values=values,
    )
    await session.flush()
    return mapping.model_copy(update={"version": next_version})


async def resolve_aigenis_id_db(
    session: AsyncSession, aigenis_instrument_id: str
) -> InstrumentMapping | None:
    """Разрешить Aigenis ID в актуальный маппинг (только active, не просроченный)."""
    from scraper.orm import InstrumentMapORM

    now = datetime.now(UTC)
    row = (
        await session.execute(
            select(InstrumentMapORM)
            .where(InstrumentMapORM.aigenis_instrument_id == aigenis_instrument_id)
            .where((InstrumentMapORM.valid_to.is_(None)) | (InstrumentMapORM.valid_to > now))
            .order_by(InstrumentMapORM.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return _row_to_mapping(row) if row is not None else None


async def resolve_isin_db(session: AsyncSession, isin: str) -> InstrumentMapping | None:
    """Найти маппинг по ISIN (актуальную версию)."""
    from scraper.orm import InstrumentMapORM

    row = (
        await session.execute(
            select(InstrumentMapORM)
            .where(InstrumentMapORM.isin == isin)
            .order_by(InstrumentMapORM.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return _row_to_mapping(row) if row is not None else None


async def list_mappings_db(
    session: AsyncSession, *, market: str | None = None, limit: int = 500
) -> list[InstrumentMapping]:
    """Список актуальных маппингов (для reconciliation job)."""
    from scraper.orm import InstrumentMapORM

    stmt = select(InstrumentMapORM).order_by(InstrumentMapORM.aigenis_instrument_id).limit(limit)
    if market:
        stmt = stmt.where(InstrumentMapORM.market == market)
    rows = (await session.execute(stmt)).scalars().all()
    return [_row_to_mapping(r) for r in rows]


# ──────────────────────────────────────────────
# In-memory API (demo/tests)
# ──────────────────────────────────────────────


def resolve_aigenis_id(aigenis_instrument_id: str) -> InstrumentMapping:
    """Разрешить Aigenis ID в аналитический internal_id (in-memory).

    Возвращает InstrumentMapping со статусом not_covered, если инструмент не
    найден в маппинге (вместо 500).
    """
    mapping = _INSTRUMENT_MAP.get(aigenis_instrument_id)
    if mapping is None:
        return InstrumentMapping(
            aigenis_instrument_id=aigenis_instrument_id,
            status=InstrumentStatus.not_covered,
        )
    return mapping


def resolve_isin(isin: str) -> InstrumentMapping | None:
    """Найти маппинг по ISIN (in-memory)."""
    for mapping in _INSTRUMENT_MAP.values():
        if mapping.isin == isin:
            return mapping
    return None


def add_mapping(mapping: InstrumentMapping) -> None:
    """Добавить запись в маппинг (in-memory)."""
    _INSTRUMENT_MAP[mapping.aigenis_instrument_id] = mapping


def load_mappings(mappings: list[InstrumentMapping]) -> None:
    """Массовая загрузка маппингов (in-memory)."""
    for m in mappings:
        _INSTRUMENT_MAP[m.aigenis_instrument_id] = m


def get_mapping_stats() -> dict[str, int]:
    """Статистика по маппингам (in-memory)."""
    stats: dict[str, int] = {}
    for m in _INSTRUMENT_MAP.values():
        key = m.status.value
        stats[key] = stats.get(key, 0) + 1
    return stats
