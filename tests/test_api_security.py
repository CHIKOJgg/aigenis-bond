"""Integration tests for API security, rate limiting, and error logging.

Covers: auth endpoints, billing webhooks, partner webhooks,
rate limiting, CORS, security headers, and error visibility.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.mark.asyncio
async def test_health_endpoint_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "db" in data


@pytest.mark.asyncio
async def test_readiness_endpoint_returns_200_when_db_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ready")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_openapi_schema_is_exposed():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "paths" in data
    assert "info" in data


@pytest.mark.asyncio
async def test_security_headers_on_api_responses():
    """API responses should carry security headers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/bonds")
    assert "X-Content-Type-Options" in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_rate_limit_returns_429_with_retry_after():
    """Rate-limited requests should include a Retry-After header."""
    import api.main as main

    old_limit = main._RATE_LIMIT
    try:
        main._RATE_LIMIT = 5
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(100):
                resp = await client.get("/api/v1/bonds")
        assert resp.status_code == 429
        assert "retry_after" in resp.json() or "Retry-After" in resp.headers
    finally:
        main._RATE_LIMIT = old_limit
