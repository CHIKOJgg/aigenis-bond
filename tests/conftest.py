from __future__ import annotations

import asyncio
import os

import pytest

# Force in-memory SQLite for all tests (overrides .env file).
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
# High rate-limit so tests don't trigger 429.
os.environ["API_RATE_LIMIT"] = "100000"
os.environ["API_RATE_WINDOW"] = "60"
os.environ["RATE_LIMIT_BACKEND"] = "memory"
os.environ["DEMO_MODE"] = ""
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-that-is-long-enough-for-testing-12345678"


@pytest.fixture(autouse=True)
def _ensure_schema():
    """Ensure the in-memory DB has the full schema before every test.

    Some tests dispose the shared engine (see test_auth._run), which drops the
    in-memory DB; running create_all idempotently per test makes HTTP tests
    order-independent.
    """
    from scraper.db import get_engine
    from scraper.orm import Base

    async def _create():
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from api.main import _rate_limit_store

    _rate_limit_store.clear()
    yield
