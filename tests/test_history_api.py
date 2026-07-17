"""Tests for API-mode history fetching (scraper.client._api_fetch_history).

Previously ``fetch_history`` raised ``HistoryUnavailable`` unconditionally in
API mode, so history (and therefore ML/forecast/RV that depend on it) never
populated in production. These tests exercise the new API path with a stubbed
``_api_request`` — no browser or network involved.
"""
from __future__ import annotations

import asyncio
from datetime import date

from scraper.client import AigenisClient
from scraper.errors import HistoryUnavailable, NotFoundError


def _client() -> AigenisClient:
    c = AigenisClient()

    async def _noop_browser():
        return None

    # Avoid launching Playwright / auth in tests.
    c._ensure_browser = _noop_browser  # type: ignore[method-assign]
    c._id_by_internal = {"OP-1": 42}
    return c


def test_api_history_normalizes_and_paginates():
    c = _client()
    pages = {
        1: {"results": [{"date": f"2025-01-{i:02d}", "close": 100 + i, "instr_yield": 5 + i * 0.1}
                        for i in range(1, 32)] * 17},  # >500 -> forces page 2
        2: {"results": [{"trade_date": "2025-06-01", "last": 99.5, "yield": 6.2, "coupon": 5.0}]},
    }

    async def fake_api_request(method, path, params=None):
        return pages.get(params["page"], {"results": []})

    c._api_request = fake_api_request  # type: ignore[method-assign]

    async def run():
        rows = await c.fetch_history("OP-1", since=date(2025, 1, 1), until=date(2025, 12, 31))
        return rows

    rows = asyncio.run(run())
    assert len(rows) > 500  # two pages merged
    # Field mapping: close->price, instr_yield->yield.
    first = rows[0]
    assert first["date"] == "2025-01-01"
    assert first["price"] == 101
    assert abs(first["yield"] - 5.1) < 1e-6
    # Last page row uses alternative field names.
    last = rows[-1]
    assert last["price"] == 99.5
    assert last["yield"] == 6.2
    assert last["coupon"] == 5.0


def test_api_history_missing_listing_raises_notfound():
    c = _client()
    c._id_by_internal = {}  # listing not run

    async def run():
        await c.fetch_history("OP-1", since=date(2025, 1, 1))

    try:
        asyncio.run(run())
        raise AssertionError("expected NotFoundError")
    except NotFoundError:
        pass


def test_api_history_404_degrades_to_unavailable():
    c = _client()

    async def fake_api_request(method, path, params=None):
        raise NotFoundError("404")

    c._api_request = fake_api_request  # type: ignore[method-assign]

    async def run():
        await c.fetch_history("OP-1", since=date(2025, 1, 1))

    try:
        asyncio.run(run())
        raise AssertionError("expected HistoryUnavailable")
    except HistoryUnavailable:
        pass


def test_api_history_disabled_when_path_empty():
    c = _client()
    original = c.settings.api_history_path
    c.settings.api_history_path = ""

    async def run():
        await c.fetch_history("OP-1", since=date(2025, 1, 1))

    try:
        asyncio.run(run())
        raise AssertionError("expected HistoryUnavailable")
    except HistoryUnavailable:
        pass
    finally:
        c.settings.api_history_path = original
