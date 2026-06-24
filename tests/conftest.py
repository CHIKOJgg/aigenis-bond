"""Pytest configuration & fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIGENIS_HEADLESS", "true")
    monkeypatch.setenv("AIGENIS_USE_STEALTH", "false")
    monkeypatch.setenv("AIGENIS_DELAY_BETWEEN_REQUESTS", "0")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture(autouse=True)
async def _reset_db_engine() -> None:
    from scraper import db as scraper_db

    yield

    if scraper_db._engine is not None:
        await scraper_db._engine.dispose()
    scraper_db._engine = None
    scraper_db._session_factory = None


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
