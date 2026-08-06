"""
MarketDataProvider — абстрактный интерфейс источника рыночных данных.

Реализации:
- AigenisOfficialProvider  — официальный API/feed Aigenis (целевой)
- MoexProvider              — публичный MOEX ISS (резервный)
- DemoFixtureProvider       — демо-фикстуры (для встреч)

Все провайдеры возвращают данные в канонической модели Bond (scraper.models.Bond).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class DataLineage:
    """Метаданные происхождения данных для каждого snapshot."""

    source: str
    license_contract_id: str | None = None
    as_of: datetime = field(default_factory=lambda: datetime.now(UTC))
    ingestion_run: str | None = None
    quality_status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "license_contract_id": self.license_contract_id,
            "as_of": self.as_of.isoformat(),
            "ingestion_run": self.ingestion_run,
            "quality_status": self.quality_status,
        }


class MarketDataProvider(ABC):
    """
    Абстрактный провайдер рыночных данных.

    Каждая реализация предоставляет:
    - fetch_bonds(market: str)        -> list[dict]  (список облигаций)
    - health_check()                  -> bool        (доступность источника)
    - data_lineage                    -> DataLineage (происхождение данных)
    """

    @property
    @abstractmethod
    def data_lineage(self) -> DataLineage:
        """Метаданные источника данных."""

    @abstractmethod
    async def fetch_bonds(self, market: str) -> list[dict[str, Any]]:
        """Получить список облигаций для указанного рынка (bcse / moex)."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Проверить доступность источника."""

    async def fetch_bonds_all_markets(self) -> dict[str, list[dict[str, Any]]]:
        """Получить облигации для всех рынков."""
        result: dict[str, list[dict[str, Any]]] = {}
        for market in ("bcse", "moex"):
            try:
                result[market] = await self.fetch_bonds(market)
            except Exception:
                result[market] = []
        return result
