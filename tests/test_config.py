from __future__ import annotations

from scraper.config import AppSettings, DatabaseSettings, RedisSettings, Settings, TelegramSettings


def test_settings_defaults():
    s = Settings()
    assert s.base_url == "https://aigenis.by"
    assert s.headless is True
    assert s.max_retries == 3
    assert len(s.currencies) == 6


def test_settings_validation():
    s = Settings(delay_between_requests=-1)
    assert s.delay_between_requests == 0.0

    s = Settings(history_backfill_days=5000)
    assert s.history_backfill_days == 3650

    s = Settings(history_backfill_days=0)
    assert s.history_backfill_days >= 1


def test_database_settings_defaults():
    s = DatabaseSettings()
    assert s.pool_size == 10
    assert s.max_overflow == 20
    assert s.max_retries == 3


def test_redis_settings_defaults():
    s = RedisSettings()
    assert s.socket_timeout == 5.0
    assert s.max_connections == 20


def test_telegram_settings_defaults():
    s = TelegramSettings()
    assert s.webhook_path == "/webhook"
    assert s.webhook_port == 8080
    assert s.rate_limit_per_sec == 3


def test_app_settings_validation():
    s = AppSettings()
    assert s.aigenis is not None
    assert s.database is not None
    assert s.redis is not None
    assert s.telegram is not None


def test_app_settings_warnings():
    s = AppSettings()
    s.aigenis.data_api_url = "not-a-url"
    warnings = s.validate_all()
    assert len(warnings) >= 1
    assert any("DATA_API_URL" in w for w in warnings)
