"""
Provider registry — конфигурируемая фабрика MarketDataProvider (plan item 5.5).

Выбор провайдера:
- ``DATA_PROVIDER=aigenis_official`` — официальный feed Aigenis (заглушка до
  получения API; fail-closed: без URL/key провайдер не активен).
- ``DATA_PROVIDER=moex``          — публичный MOEX ISS.
- ``DATA_PROVIDER=demo_fixtures`` — демо-фикстуры (презентации).
- пусто (default)                 — резерв по profile:
    * profile=aigenis -> aigenis_official (fail-closed: возвращает пусто,
      пока feed не настроен);
    * profile=saas    -> moex.

Fail-closed политика (plan item 5.7): в profile=aigenis browser scraping
запрещён — если ``DATA_SOURCE=aigenis`` (browser-клиент) и провайдер не
сконфигурирован, run/scrape отказывает заранее, а не тихо скрейпит сайт.
"""

from __future__ import annotations

import os

from scraper.logging import get_logger
from scraper.providers import MarketDataProvider

logger = get_logger("scraper.providers.registry")


class ProviderNotConfiguredError(RuntimeError):
    """Провайдер запрошен, но не сконфигурирован (fail-closed)."""


def _profile() -> str:
    return (os.getenv("DEPLOYMENT_PROFILE") or "saas").strip().lower()


def get_provider(name: str = "") -> MarketDataProvider:
    """Фабрика провайдера по имени (или по profile-дефолту)."""
    provider_name = name.strip().lower() if name.strip() else _default_provider_name()
    if provider_name == "aigenis_official":
        from scraper.providers.aigenis_official import AigenisOfficialProvider

        return AigenisOfficialProvider(
            api_url=os.getenv("DATA_PROVIDER_API_URL", ""),
            api_key=os.getenv("DATA_PROVIDER_API_KEY", ""),
        )
    if provider_name in ("moex", "moex_iss"):
        from scraper.providers.moex import MoexProvider

        return MoexProvider()
    if provider_name in ("demo", "demo_fixtures"):
        from scraper.providers.demo import DemoFixtureProvider

        return DemoFixtureProvider()
    raise ProviderNotConfiguredError(f"Unknown DATA_PROVIDER: {provider_name!r}")


def _default_provider_name() -> str:
    if _profile() == "aigenis":
        return "aigenis_official"
    return "moex"


def assert_browser_scraping_allowed() -> None:
    """Fail-closed: запретить browser scraping в profile=aigenis (plan 5.7).

    Вызывается перед запуском browser-клиента (scraper.client.AigenisClient).
    В profile=aigenis scraping официального сайта Aigenis запрещён —
    данные должны приходить через официальный feed.
    """
    if _profile() != "aigenis":
        return
    source = (os.getenv("DATA_SOURCE") or "aigenis").strip().lower()
    if source in ("aigenis", "both"):
        raise ProviderNotConfiguredError(
            "DEPLOYMENT_PROFILE=aigenis forbids browser scraping of aigenis.by. "
            "Configure the official data feed (DATA_PROVIDER_API_URL + "
            "DATA_PROVIDER_API_KEY) or set DATA_SOURCE=moex."
        )
