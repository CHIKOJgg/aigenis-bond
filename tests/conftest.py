from __future__ import annotations

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
def _reset_rate_limiter():
    from api.main import _rate_limit_store

    _rate_limit_store.clear()
    yield
