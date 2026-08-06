"""
AigenisOfficialProvider — заглушка до получения официального data feed.

Будет реализован после предоставления Aigenis API/экспорта данных.
В production запрещает любой browser scraping через fail-closed политику.

Конфигурация:
    DATA_PROVIDER=aigenis_official
    DATA_PROVIDER_API_URL=https://api.aigenis.by/v1/market-data
    DATA_PROVIDER_API_KEY=<key>
"""

from __future__ import annotations

from typing import Any

from . import DataLineage, MarketDataProvider


class AigenisOfficialProvider(MarketDataProvider):
    """
    Провайдер официального data feed Aigenis.

    В текущей версии — заглушка. Будет активирован после:
    1. Подписания NDA/пилотного соглашения.
    2. Получения URL, API key и schema contract.
    3. Имплементации HTTP-клиента с retry, circuit breaker и валидацией.

    До этого использует AigenisDemoProvider (в demo-mode) или MoexProvider (для MOEX).
    """

    def __init__(self, api_url: str = "", api_key: str = "") -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._active = bool(api_url and api_key)

    @property
    def data_lineage(self) -> DataLineage:
        return DataLineage(
            source="aigenis_official",
            license_contract_id="pending",  # Будет заменён на реальный contract_id
            quality_status="ok",
        )

    async def fetch_bonds(self, market: str) -> list[dict[str, Any]]:  # noqa: ARG002 — контракт MarketDataProvider
        if not self._active:
            return []
        # TODO: имплементировать HTTP-запрос к DATA_PROVIDER_API_URL
        # с заголовком Authorization: Bearer {DATA_PROVIDER_API_KEY}
        return []

    async def health_check(self) -> bool:
        if not self._active:
            return False
        # TODO: имплементировать /health check источника
        return False
