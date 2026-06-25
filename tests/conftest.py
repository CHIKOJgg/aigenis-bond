from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIGENIS_HEADLESS", "true")
    monkeypatch.setenv("AIGENIS_USE_STEALTH", "false")
    monkeypatch.setenv("AIGENIS_DELAY_BETWEEN_REQUESTS", "0")
    monkeypatch.setenv("AIGENIS_MAX_CONCURRENCY", "1")
    monkeypatch.setenv("AIGENIS_LOG_JSON", "false")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(autouse=True)
async def _reset_db_engine() -> None:
    from scraper import db as scraper_db

    yield

    if scraper_db._engine is not None:
        await scraper_db._engine.dispose()
    scraper_db._engine = None
    scraper_db._session_factory = None


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    from scraper import config as scraper_config

    scraper_config._settings = None


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
async def db_session():
    from scraper.db import session_scope

    async with session_scope() as session:
        yield session
