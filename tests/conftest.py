from __future__ import annotations

import os
from pathlib import Path

import pytest

# Set test env vars BEFORE any imports that might trigger get_settings()
os.environ.setdefault("AIGENIS_HEADLESS", "true")
os.environ.setdefault("AIGENIS_USE_STEALTH", "false")
os.environ.setdefault("AIGENIS_DELAY_BETWEEN_REQUESTS", "0")
os.environ.setdefault("AIGENIS_MAX_CONCURRENCY", "1")
os.environ.setdefault("AIGENIS_LOG_JSON", "false")
os.environ.setdefault("AIGENIS_LOG_LEVEL", "ERROR")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    from scraper import config as scraper_config
    scraper_config._settings = None


@pytest.fixture(autouse=True)
async def _reset_db_engine() -> None:
    from scraper import db as scraper_db
    from scraper.orm import Base

    # Create all tables for in-memory SQLite
    engine = scraper_db.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    if scraper_db._engine is not None:
        await scraper_db._engine.dispose()
    scraper_db._engine = None
    scraper_db._session_factory = None


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
async def db_session():
    from scraper.db import session_scope

    async with session_scope() as session:
        yield session
