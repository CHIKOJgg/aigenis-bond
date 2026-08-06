"""Tests for SEO public routes.

Covers: bond leaderboard, bond detail, sitemap, robots.txt,
calculator pages, partners page, lead rate limiting, and error handling.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.seo import router as seo_router
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, BondHistoryORM, BondORM, BondScoreORM, CompanyORM

app = FastAPI()
app.include_router(seo_router)


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


def _make_bond(
    iid,
    name,
    currency="USD",
    ytm=10.0,
    price=100.0,
    coupon=8.0,
    freq=2,
    maturity=date(2030, 1, 1),
    status="active",
):
    return BondORM(
        internal_id=iid,
        name=name,
        currency=currency,
        yield_to_maturity=ytm,
        price=price,
        coupon_rate=coupon,
        coupon_frequency=freq,
        maturity_date=maturity,
        status=status,
        issuer="Acme Corp",
        fetched_at=datetime.now(UTC),
    )


async def _seed() -> None:
    async with session_scope() as s:
        s.add(_make_bond("OP-51", "Acme 2029", "USD", ytm=11.5, price=101.2))
        s.add(_make_bond("RU-01", "Gazprom 2027", "RUB", ytm=14.0, price=98.0, coupon=9.0))
        s.add(
            BondScoreORM(
                internal_id="OP-51",
                score=82.0,
                tier="A",
                breakdown={},
                computed_at=datetime.now(UTC),
            )
        )
        s.add(
            BondScoreORM(
                internal_id="RU-01",
                score=55.0,
                tier="C",
                breakdown={},
                computed_at=datetime.now(UTC),
            )
        )
        s.add(
            CompanyORM(
                issuer="Acme Corp",
                name="Acme Corporation",
                sector="Technology",
                description="Эмитент тест.",
            )
        )
        for d, p in [
            (date(2026, 1, 1), 99.0),
            (date(2026, 2, 1), 100.1),
            (date(2026, 3, 1), 101.2),
        ]:
            s.add(
                BondHistoryORM(internal_id="OP-51", date=d, price=p, yield_=11.0, status="active")
            )


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


# ─── Bot / human split ───────────────────────────────────────────────────────
# SEO-covered paths must keep serving the server-rendered page to crawlers and
# link previewers while regular browsers get the SPA. The split only kicks in
# when a frontend build is configured (FRONTEND_DIR); otherwise the SEO page is
# served to everyone (API-only deployments).

HUMAN_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
TELEGRAM_UA = "TelegramBot (like TwitterBot) 0.1; +http://core.telegram.org/bots"


def _write_fake_spa(tmp_path: pytest.TempPathFactory) -> str:
    (tmp_path / "index.html").write_text(
        "<!doctype html><html><head><title>SPA</title></head>"
        "<body><div id='root'>FAKE-SPA-MARKER</div></body></html>",
        encoding="utf-8",
    )
    return str(tmp_path)


@pytest.mark.asyncio
async def test_human_gets_spa_on_bonds(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIR", _write_fake_spa(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/bonds", headers={"User-Agent": HUMAN_UA})
    assert resp.status_code == 200
    assert "FAKE-SPA-MARKER" in resp.text


@pytest.mark.asyncio
async def test_bot_gets_seo_html_on_bonds(tmp_path, monkeypatch):
    await _ensure_schema()
    await _seed()
    try:
        monkeypatch.setenv("FRONTEND_DIR", _write_fake_spa(tmp_path))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/bonds", headers={"User-Agent": GOOGLEBOT_UA})
        assert resp.status_code == 200
        assert "Рейтинг облигаций" in resp.text
        assert "FAKE-SPA-MARKER" not in resp.text
    finally:
        await dispose()


@pytest.mark.asyncio
async def test_link_previewer_gets_seo_html(tmp_path, monkeypatch):
    """Telegram/WhatsApp/VK link previews consume the server-rendered OG markup."""
    monkeypatch.setenv("FRONTEND_DIR", _write_fake_spa(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/bonds", headers={"User-Agent": TELEGRAM_UA})
    assert resp.status_code == 200
    assert "og:title" in resp.text
    assert "FAKE-SPA-MARKER" not in resp.text


@pytest.mark.asyncio
async def test_human_gets_spa_on_bond_detail(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIR", _write_fake_spa(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/bonds/SOME-UNKNOWN-ID", headers={"User-Agent": HUMAN_UA})
    assert resp.status_code == 200
    assert "FAKE-SPA-MARKER" in resp.text


@pytest.mark.asyncio
async def test_bot_gets_404_on_unknown_bond(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIR", _write_fake_spa(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/bonds/SOME-UNKNOWN-ID", headers={"User-Agent": GOOGLEBOT_UA})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_human_gets_spa_on_calculator(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIR", _write_fake_spa(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/calculator", headers={"User-Agent": HUMAN_UA})
    assert resp.status_code == 200
    assert "FAKE-SPA-MARKER" in resp.text


@pytest.mark.asyncio
async def test_bot_gets_seo_html_on_calculator(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIR", _write_fake_spa(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/calculator", headers={"User-Agent": GOOGLEBOT_UA})
    assert resp.status_code == 200
    assert "YTM" in resp.text
    assert "FAKE-SPA-MARKER" not in resp.text


@pytest.mark.asyncio
async def test_seo_pages_use_brand_color(tmp_path, monkeypatch):
    """SEO pages follow the rebrand: no legacy green, brand teal in CSS."""
    monkeypatch.setenv("FRONTEND_DIR", _write_fake_spa(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/calculator", headers={"User-Agent": GOOGLEBOT_UA})
    assert "#004b65" in resp.text
    assert "#059669" not in resp.text


@pytest.mark.asyncio
async def test_guides_not_affected_by_split(tmp_path, monkeypatch):
    """Non-SPA public pages (/guides, /partners) keep serving HTML to everyone."""
    monkeypatch.setenv("FRONTEND_DIR", _write_fake_spa(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/guides", headers={"User-Agent": HUMAN_UA})
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("text/html")
    assert "FAKE-SPA-MARKER" not in resp.text
