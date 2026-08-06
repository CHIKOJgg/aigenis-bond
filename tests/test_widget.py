"""Tests for the public widget endpoints (api.widget).

Covers: /widget/embed.js serving REAL JavaScript (not a JSON-encoded string),
and the /widget/top payload shape.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.mark.asyncio
async def test_embed_js_is_raw_javascript():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/widget/embed.js")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/javascript")
    body = resp.text
    # Raw executable JS — NOT a JSON-encoded string literal.
    assert body.lstrip().startswith("(function(){")
    assert body.rstrip().endswith("})();")
    assert '"' not in body[:10]
    assert "createElement('iframe')" in body


@pytest.mark.asyncio
async def test_widget_top_returns_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/widget/top?limit=5")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
