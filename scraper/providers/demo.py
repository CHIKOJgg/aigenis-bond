"""
DemoFixtureProvider — демо-фикстуры для презентаций.

Детерминированный источник канонических Bond-словарей (без сети, без API).
Используется в demo/presentation-выдачах (profile по умолчанию не активирован).

Только демо-данные: не сид "боевой" БД продакшна. В profile=aigenis источник
запрещён fail-closed политикой (registry.assert_browser_scraping_allowed).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from . import DataLineage, MarketDataProvider


def _bond(
    internal_id: str,
    name: str,
    isin: str,
    issuer: str,
    currency: str,
    market: str,
    coupon_rate: str,
    maturity: str,
    ytm: str,
) -> dict[str, Any]:
    return {
        "internal_id": internal_id,
        "name": name,
        "isin": isin,
        "issuer": issuer,
        "currency": currency,
        "market": market,
        "coupon_rate": Decimal(coupon_rate),
        "coupon_frequency": 2,
        "maturity_date": date.fromisoformat(maturity),
        "price": Decimal("100.00"),
        "yield_to_maturity": Decimal(ytm),
        "nominal": Decimal("1000.00"),
        "amortization": "none",
        "status": "active",
        "is_government": issuer in ("Минфин РБ", "Минфин РФ"),
        "fetched_at": datetime.now(UTC),
    }


_BCSE_FIXTURES = [
    _bond(
        "BCSE_DE0001",
        "ДЕЛЬТА 001",
        "BY0000000001",
        "ЗАО «ДЕЛЬТА»",
        "BYN",
        "bcse",
        "11.00",
        "2027-03-01",
        "9.8",
    ),
    _bond(
        "BCSE_MINSK",
        "МИНСК 1",
        "BY0000000002",
        "Мингорисполком",
        "BYN",
        "bcse",
        "12.00",
        "2026-06-01",
        "10.2",
    ),
    _bond(
        "BCSE_OMEGA",
        "ОМЕГА Б",
        "BY0000000003",
        "ОАО «Омега»",
        "BYN",
        "bcse",
        "10.0",
        "2027-09-15",
        "9.1",
    ),
]

_MOEX_FIXTURES = [
    _bond(
        "MOEX_OFZ1",
        "ОФЗ 26238",
        "RU000A1011Y2",
        "Минфин РФ",
        "RUB",
        "moex",
        "10.00",
        "2035-05-12",
        "9.3",
    ),
    _bond(
        "MOEX_GAZP",
        "Газпром К28",
        "RU000A100CZ5",
        "ПАО «Газпром»",
        "RUB",
        "moex",
        "12.40",
        "2028-11-10",
        "11.0",
    ),
]


def default_fixtures() -> list[dict[str, Any]]:
    """Канонический набор демо-фикстур (BCSE + MOEX).

    Возвращает глубокие копии markdown-словарей, чтобы вызывающий код мог
    мутировать результат (например, добавлять свои поля).
    """
    out: list[dict[str, Any]] = []
    for fixture in [*_BCSE_FIXTURES, *_MOEX_FIXTURES]:
        out.append(dict(fixture))
    return out


class DemoFixtureProvider(MarketDataProvider):
    """Детерминированный источник демо-облигаций (BCSE и MOEX)."""

    def __init__(self, fixtures: list[dict[str, Any]] | None = None) -> None:
        self._fixtures = fixtures if fixtures is not None else default_fixtures()

    def _fixtures_for(self, market: str) -> list[dict[str, Any]]:
        return [b for b in self._fixtures if b["market"] == market]

    @property
    def data_lineage(self) -> DataLineage:
        return DataLineage(
            source="demo_fixtures",
            license_contract_id="demo",
            quality_status="ok",
        )

    async def fetch_bonds(self, market: str) -> list[dict[str, Any]]:
        return self._fixtures_for(market)

    async def health_check(self) -> bool:
        return True
