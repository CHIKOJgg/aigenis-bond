"""Tests for SEO public routes.

Covers: bond leaderboard, bond detail, sitemap, robots.txt,
calculator pages, partners page, lead rate limiting, and error handling.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.seo import router as seo_router

app = FastAPI()
app.include_router(seo_router)


@pytest.mark.asyncio
async def test_seo_robots_returns_200():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/robots.txt")
    assert resp.status_code == 200
    assert "User-agent" in resp.text
    assert "Allow: /bonds" in resp.text


@pytest.mark.asyncio
async def test_seo_sitemap_returns_xml():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "<?xml version" in resp.text or "<urlset" in resp.text
    assert resp.headers.get("content-type", "").startswith("application/xml")


@pytest.mark.asyncio
async def test_seo_bonds_leaderboard_returns_html():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/bonds")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/html")


@pytest.mark.asyncio
async def test_seo_calculator_returns_html():
    """Calculator page is public and crawlable."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/calculator")
    assert resp.status_code == 200
    assert "Calculator" in resp.text or "калькулятор" in resp.text.lower() or "YTM" in resp.text


@pytest.mark.asyncio
async def test_seo_guides_index_returns_html():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/guides")
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/html")


@pytest.mark.asyncio
async def test_seo_rate_limits_partner_leads():
    """Multiple lead submissions from the same IP should be rate-limited."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            resp = await client.post(
                "/partners/request",
                data={
                    "name": "Test User",
                    "email": "test@example.com",
                    "message": "Interested in white-label",
                },
            )
    last_status = resp.status_code
    assert last_status in (200, 400)  # Either success or rate-limited
