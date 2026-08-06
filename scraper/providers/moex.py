"""
MoexProvider — публичный MOEX ISS источник рыночных данных (резервный).

Статус: заглушка до подтверждения права на ретрансляцию MOEX-данных в B2B
выдаче (plan item 5.5). Интерфейс соответствует контракту MarketDataProvider,
но не выполняет сетевых вызовов: fetch_bonds возвращает [] до юридического
разрешения и конфигурации (DATA_PROVIDER=moex_iss).

Демо-фикстуры для презентаций предоставляет DemoFixtureProvider.
"""

from __future__ import annotations

from typing import Any

from scraper.logging import get_logger

from . import DataLineage, MarketDataProvider

logger = get_logger("scraper.providers.moex")


class MoexProvider(MarketDataProvider):
    """Провайдер публичного MOEX ISS для бондов рынка moex."""

    def __init__(self, active: bool = False) -> None:
        self._active = active

    @property
    def data_lineage(self) -> DataLineage:
        return DataLineage(
            source="moex_iss",
            license_contract_id="public",
            quality_status="ok",
        )

    async def fetch_bonds(self, market: str) -> list[dict[str, Any]]:  # noqa: ARG002 — контракт MarketDataProvider
        if not self._active:
            return []
        # TODO: имплементировать HTTP-запрос к iss.moex.com после подтверждения
        # права на ретрансляцию (plan item 5.5).
        return []

    async def health_check(self) -> bool:
        return self._active
