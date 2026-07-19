"""Load / rate-limit enforcement tests for the API.

Two concerns, both required by the brief:

1. Rate-limit correctness — the limiter MUST return HTTP 429 once a caller's
   budget is exhausted and MUST NOT breach the budget under burst or concurrent
   load. This guards against the API silently dropping the limit (which would
   let one client exhaust shared resources / hit an upstream rate limit).

2. Server load — a burst of N concurrent requests must all be served (HTTP 2xx)
   as long as the per-key budget is not exceeded, proving the server withstands
   realistic load without crashing or deadlocking.

The in-memory limiter is exercised directly (deterministic) plus via the full
ASGI stack (real middleware) so both the store logic and the wiring are checked.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict

import httpx
import pytest

import api.main as main
from api.auth.service import create_access_token
from scraper.db import get_engine
from scraper.orm import Base


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --------------------------------------------------------------------------- #
# Deterministic unit-level limiter checks
# --------------------------------------------------------------------------- #
def test_memory_limiter_allows_up_to_limit(monkeypatch):
    monkeypatch.setattr(main, "_rate_limit_store", defaultdict(list))
    lim = 5
    for i in range(lim):
        assert main._memory_allow("k", lim) is True
    # Next call must be rejected.
    assert main._memory_allow("k", lim) is False


def test_memory_limiter_window_slides(monkeypatch):
    monkeypatch.setattr(main, "_rate_limit_store", defaultdict(list))
    # Force the window to 1 second so the cutoff is tiny and old stamps expire.
    monkeypatch.setattr(main, "_RATE_WINDOW", 1)
    main._rate_limit_store["k"].append(time.monotonic() - 2.0)  # old stamp
    assert main._memory_allow("k", 1) is True  # expired stamp ignored


def test_memory_limiter_isolated_per_key(monkeypatch):
    monkeypatch.setattr(main, "_rate_limit_store", defaultdict(list))
    for _ in range(3):
        assert main._memory_allow("a", 3) is True
    # A different key has its own budget.
    assert main._memory_allow("b", 3) is True


# --------------------------------------------------------------------------- #
# Full-stack rate limit via ASGI (real middleware)
# --------------------------------------------------------------------------- #
def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test")


async def _drain(client, n, path="/health"):
    return [r.status_code for r in await asyncio.gather(*[client.get(path) for _ in range(n)])]


def test_rate_limit_returns_429_after_budget(monkeypatch):
    """Free anonymous budget is 10 in FEATURE_FLAGS, but the global limiter uses
    API_RATE_LIMIT (default 60). Exercise via the global limiter with a low cap."""
    monkeypatch.setenv("API_RATE_LIMIT", "10")
    monkeypatch.setenv("API_RATE_WINDOW", "60")
    monkeypatch.setattr(main, "_RATE_LIMIT", 10)
    monkeypatch.setattr(main, "_RATE_WINDOW", 60)
    monkeypatch.setattr(main, "_rate_limit_store", defaultdict(list))

    async def run():
        await _ensure_schema()
        async with _client() as client:
            codes = await _drain(client, 10, path="/api/v1/bonds")
            assert all(c == 200 for c in codes)
            # 11th in the same window (non-exempt endpoint) is throttled.
            assert (await client.get("/api/v1/bonds")).status_code == 429
            # Body shape matches the contract consumed by clients.
            body = (await client.get("/api/v1/bonds")).json()
            assert body["error"] == "Too many requests"
            assert "retry_after" in body

    asyncio.run(run())


def test_rate_limit_health_endpoint_is_exempt(monkeypatch):
    """/health must never be throttled even after the budget is blown."""
    monkeypatch.setenv("API_RATE_LIMIT", "1")
    monkeypatch.setenv("API_RATE_WINDOW", "60")
    monkeypatch.setattr(main, "_RATE_LIMIT", 1)
    monkeypatch.setattr(main, "_RATE_WINDOW", 60)
    monkeypatch.setattr(main, "_rate_limit_store", defaultdict(list))

    async def run():
        await _ensure_schema()
        async with _client() as client:
            assert (await client.get("/api/v1/bonds")).status_code == 200
            assert (await client.get("/api/v1/bonds")).status_code == 429
            # Health still works.
            assert (await client.get("/health")).status_code == 200

    asyncio.run(run())


def test_authenticated_users_have_separate_budgets(monkeypatch):
    monkeypatch.setenv("API_RATE_LIMIT", "2")
    monkeypatch.setenv("API_RATE_WINDOW", "60")
    monkeypatch.setattr(main, "_RATE_LIMIT", 2)
    monkeypatch.setattr(main, "_RATE_WINDOW", 60)
    monkeypatch.setattr(main, "_rate_limit_store", defaultdict(list))

    headers_a = {"Authorization": f"Bearer {create_access_token(1)}"}
    headers_b = {"Authorization": f"Bearer {create_access_token(2)}"}

    async def run():
        await _ensure_schema()
        async with _client() as client:
            # User 1 exhausts its budget of 2.
            assert (await client.get("/api/v1/bonds", headers=headers_a)).status_code == 200
            assert (await client.get("/api/v1/bonds", headers=headers_a)).status_code == 200
            assert (await client.get("/api/v1/bonds", headers=headers_a)).status_code == 429
            # User 2 has its OWN budget and is unaffected by user 1's exhaustion.
            assert (await client.get("/api/v1/bonds", headers=headers_b)).status_code == 200
            # And still has a second request available.
            assert (await client.get("/api/v1/bonds", headers=headers_b)).status_code == 200
            assert (await client.get("/api/v1/bonds", headers=headers_b)).status_code == 429

    asyncio.run(run())


# --------------------------------------------------------------------------- #
# Concurrent load: server must survive a burst without errors / deadlock
# --------------------------------------------------------------------------- #
def test_concurrent_burst_under_budget():
    """50 concurrent requests, well under a generous budget, all succeed.

    Verifies the server does not crash, deadlock, or 500 under parallel load."""
    N = 50

    async def run_all():
        async with _client() as client:
            # Pre-warm so the first-request schema creation cost is excluded.
            await client.get("/health")
            tasks = [client.get("/health") for _ in range(N)]
            resps = await asyncio.gather(*tasks)
            return [r.status_code for r in resps]

    results = asyncio.run(run_all())
    assert results.count(200) == N, f"expected all 200, got {results}"


def test_burst_does_not_breach_limit_under_concurrency(monkeypatch):
    """Exactly the budget of concurrent requests is allowed; no over-admission.

    Runs with a tight limit and many more attempts in parallel; asserts the
    number of non-429 responses equals the limit (no race lets extra through).
    """
    LIMIT = 20
    ATTEMPTS = 200
    monkeypatch.setenv("API_RATE_LIMIT", str(LIMIT))
    monkeypatch.setenv("API_RATE_WINDOW", "60")
    monkeypatch.setattr(main, "_RATE_LIMIT", LIMIT)
    monkeypatch.setattr(main, "_RATE_WINDOW", 60)
    monkeypatch.setattr(main, "_rate_limit_store", defaultdict(list))
    # Use distinct IPs so the only limiter is the per-key store on the health
    # path? No — health is exempt. Instead hit a real endpoint with one key.
    monkeypatch.setattr(main, "_TRUSTED_PROXY", False)

    async def run_all():
        await _ensure_schema()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as ac:
            tasks = [ac.get("/api/v1/bonds") for _ in range(ATTEMPTS)]
            resps = await asyncio.gather(*tasks)
            return [r.status_code for r in resps]

    codes = asyncio.run(run_all())
    allowed = sum(1 for c in codes if c == 200)
    throttled = sum(1 for c in codes if c == 429)
    assert allowed == LIMIT, f"allowed={allowed} expected exactly {LIMIT}"
    assert throttled == ATTEMPTS - LIMIT
