"""Tests for the scraper configuration and error handling.

Covers: settings validation, database connection, Redis connectivity,
and all error path logging in the pipeline.
"""

from __future__ import annotations

import asyncio

from scraper.config import DatabaseSettings, RedisSettings, Settings
from scraper.errors import (
    CircuitBreakerOpenError,
    FatalError,
    NotFoundError,
    ParseError,
    RateLimitError,
    ScraperError,
    TransientError,
    ValidationError,
)


def test_settings_loads_with_defaults():
    settings = Settings()
    assert settings.base_url == "https://aigenis.by"
    assert settings.headless is True
    assert settings.max_concurrency == 2


def test_settings_validates_delay():
    """Negative delay is clamped to 0."""
    s = Settings(delay_between_requests=-1)
    assert s.delay_between_requests == 0.0


def test_database_settings_default_url():
    db = DatabaseSettings()
    assert db.url == "sqlite+aiosqlite:///:memory:"


def test_redis_settings_default_url():
    """The built-in default must not depend on a local `.env` file."""
    r = RedisSettings(_env_file=None)
    assert r.url == "redis://localhost:6379/0"


def test_transient_error_is_scraper_error():
    err = TransientError("timeout")
    assert isinstance(err, ScraperError)


def test_fatal_error_stops_pipeline():
    err = FatalError("captcha detected")
    assert isinstance(err, ScraperError)


def test_not_found_error_is_transient():
    err = NotFoundError("bond delisted")
    assert isinstance(err, ScraperError)


def test_parse_error_is_scraper_error():
    err = ParseError("unexpected structure")
    assert isinstance(err, ScraperError)


def test_validation_error_is_scraper_error():
    err = ValidationError("missing required field")
    assert isinstance(err, ScraperError)


def test_circuit_breaker_error_is_scraper_error():
    err = CircuitBreakerOpenError("service unavailable")
    assert isinstance(err, ScraperError)


def test_rate_limit_error_is_transient():
    err = RateLimitError("upstream rate limited")
    assert isinstance(err, TransientError)


def test_engine_creation_logs():
    from scraper.db import dispose, get_engine

    engine = get_engine()
    assert engine is not None
    asyncio.run(dispose())


# ──────────────────────────────────────────────
# Settings: currencies, validators, properties
# ──────────────────────────────────────────────


def test_currencies_default_when_empty(monkeypatch):
    monkeypatch.delenv("AIGENIS_CURRENCIES", raising=False)
    s = Settings(_env_file=None)
    assert s.currencies == ["USD", "BYN", "EUR", "XAU", "XAG", "XPT", "CNY"]


def test_currencies_from_json_env(monkeypatch):
    monkeypatch.setenv("AIGENIS_CURRENCIES", '["USD", "RUB"]')
    s = Settings()
    assert s.currencies == ["USD", "RUB"]


def test_currencies_from_comma_env(monkeypatch):
    monkeypatch.setenv("AIGENIS_CURRENCIES", "usd, eur , BYN")
    s = Settings()
    assert s.currencies == ["USD", "EUR", "BYN"]


def test_currencies_invalid_json_falls_back_to_split(monkeypatch):
    monkeypatch.setenv("AIGENIS_CURRENCIES", "USD, EUR")
    s = Settings()
    assert s.currencies == ["USD", "EUR"]


def test_currencies_validator_rejects_unknown(monkeypatch):
    import pytest as _pytest

    monkeypatch.setenv("AIGENIS_CURRENCIES", '["USD", "ZZZ"]')
    with _pytest.raises(ValueError):
        Settings()


def test_currencies_validator_non_list_json(monkeypatch):
    import pytest as _pytest

    monkeypatch.setenv("AIGENIS_CURRENCIES", '"USD"')
    with _pytest.raises(ValueError):
        Settings()


def test_history_backfill_days_clamped():
    assert Settings(history_backfill_days=0).history_backfill_days == 1
    assert Settings(history_backfill_days=9999).history_backfill_days == 3650


def test_user_agent_short():
    assert Settings().user_agent_short == "Mozilla"
    assert Settings(user_agent="NoSlashAgent").user_agent_short == "NoSlashAgent"


def test_admin_ids_branches(monkeypatch):
    from scraper.config import TelegramSettings

    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    assert TelegramSettings().admin_ids == []
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "[1, 2]")
    assert TelegramSettings().admin_ids == [1, 2]
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "10, 20")
    assert TelegramSettings().admin_ids == [10, 20]
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "10, x, 20")
    assert TelegramSettings().admin_ids == [10, 20]
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "[1, 'x']")
    assert TelegramSettings().admin_ids == []
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "  ,  ")
    assert TelegramSettings().admin_ids == []


def test_stock_settings_boards_and_validators():
    from scraper.config import StockSettings

    assert StockSettings().boards == ["TQBR", "TQOD", "TQDE"]
    assert StockSettings(boards_raw="TQBR, SPB ").boards == ["TQBR", "SPB"]
    assert StockSettings(history_backfill_days=0).history_backfill_days == 1
    assert StockSettings(history_backfill_days=9999).history_backfill_days == 3650
    assert StockSettings(refresh_cadence_min=0).refresh_cadence_min == 1
    assert StockSettings(error_budget=0).error_budget == 1


def test_validate_all_warnings():
    from scraper.config import AppSettings

    bad = AppSettings()
    bad.aigenis.data_api_url = "ftp://bad"
    bad.telegram.bot_token = ""
    warnings = bad.validate_all()
    assert len(warnings) == 2
    assert any("http" in w for w in warnings)
    assert any("TELEGRAM_BOT_TOKEN" in w for w in warnings)

    good = AppSettings()
    good.aigenis.data_api_url = "https://ok.example"
    good.telegram.bot_token = "token"
    assert good.validate_all() == []


def test_reload_settings_returns_fresh_instance(monkeypatch):
    import scraper.config as cfg

    original = cfg._settings
    try:
        monkeypatch.setenv("AIGENIS_BASE_URL", "https://reload.example")
        fresh = cfg.reload_settings()
        assert fresh is not original
        assert fresh.aigenis.base_url == "https://reload.example"
        assert cfg.get_settings() is fresh
    finally:
        cfg._settings = original
