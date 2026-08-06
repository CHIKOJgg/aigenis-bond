"""
Instrument mapping table — связь идентификаторов инструментов.

Модель:
    instrument_map
    aigenis_instrument_id -> isin -> analytics_internal_id

Правила:
- ISIN — предпочтительный стабильный ключ.
- Нельзя сопоставлять только по display name.
- Поддержка делистинга, переименования, дублей тикеров.
- Mapping версионирован и проверяем.
- Неизвестный инструмент возвращает not_covered, не 500.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


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
    market: str
    currency: str | None = None
    analytics_internal_id: str | None = None
    status: InstrumentStatus = InstrumentStatus.active
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    version: int = 1


# In-memory mapping for demo/pilot (will be replaced with DB table)
_INSTRUMENT_MAP: dict[str, InstrumentMapping] = {}


def resolve_aigenis_id(aigenis_instrument_id: str) -> InstrumentMapping:
    """
    Разрешить Aigenis ID в аналитический internal_id.

    Возвращает InstrumentMapping со статусом not_covered,
    если инструмент не найден в маппинге (вместо 500).
    """
    mapping = _INSTRUMENT_MAP.get(aigenis_instrument_id)
    if mapping is None:
        return InstrumentMapping(
            aigenis_instrument_id=aigenis_instrument_id,
            status=InstrumentStatus.not_covered,
        )
    return mapping


def resolve_isin(isin: str) -> InstrumentMapping | None:
    """Найти маппинг по ISIN."""
    for mapping in _INSTRUMENT_MAP.values():
        if mapping.isin == isin:
            return mapping
    return None


def add_mapping(mapping: InstrumentMapping) -> None:
    """Добавить запись в маппинг."""
    _INSTRUMENT_MAP[mapping.aigenis_instrument_id] = mapping


def load_mappings(mappings: list[InstrumentMapping]) -> None:
    """Массовая загрузка маппингов."""
    for m in mappings:
        _INSTRUMENT_MAP[m.aigenis_instrument_id] = m


def get_mapping_stats() -> dict[str, int]:
    """Статистика по маппингам."""
    stats: dict[str, int] = {}
    for m in _INSTRUMENT_MAP.values():
        key = m.status.value
        stats[key] = stats.get(key, 0) + 1
    return stats
