"""Интеграционные тесты клиента через mock HTTP-сервер (без обращений к сети)."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.async_api import async_playwright
from pytest_httpserver import HTTPServer

from scraper.client import AigenisClient
from scraper.config import get_settings


@pytest.fixture
async def playwright_server(fixtures_dir: Path):
    httpserver: HTTPServer = HTTPServer()
    httpserver.start()

    listing_html = (fixtures_dir / "listing.html").read_text(encoding="utf-8")

    # aigenis.by: единый каталог /bonds/ для listing, детальная страница тоже /bonds/
    httpserver.expect_request("/bonds/").respond_with_data(listing_html, content_type="text/html")
    httpserver.expect_request("/bonds").respond_with_data(listing_html, content_type="text/html")

    pw = await async_playwright().start()
    try:
        yield httpserver, pw
    finally:
        await pw.stop()
        httpserver.stop()


@pytest.mark.asyncio
async def test_client_fetches_json(playwright_server) -> None:
    httpserver, pw = playwright_server
    base_url = httpserver.url_for("/")

    settings = get_settings()
    settings.base_url = base_url
    settings.data_api_url = None
    settings.use_stealth = False
    settings.delay_between_requests = 0
    settings.max_concurrency = 2

    browser = await pw.chromium.launch(headless=True)
    try:
        client = AigenisClient(settings)
        client._playwright = pw
        client._browser = browser
        client._context = await browser.new_context()
        try:
            items = await client.fetch_listing("USD")
            assert isinstance(items, list)
            assert len(items) >= 1
            first = items[0]
            assert "internal_id" in first
            assert first["currency"] in {"USD", "BYN", "EUR", "XAU", "XAG", "XPT"}
        finally:
            await client.close()
    finally:
        await browser.close()
