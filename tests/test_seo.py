"""Tests for the public, server-rendered SEO pages (api.seo).

Covers the bond leaderboard, per-bond page, sitemap and robots.txt. These are
the free organic acquisition surface described in docs/sales/cmo_audit.md (§2/§6).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import select

from api.main import app
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, BondHistoryORM, BondORM, BondScoreORM, CompanyORM


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        # Reset first: the cached :memory: engine can leak tables between
        # tests, so drop + create keeps each test hermetic.
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


def _run(coro_fn):
    async def wrapper():
        await _ensure_schema()
        try:
            await coro_fn()
        finally:
            await dispose()

    asyncio.run(wrapper())


def _make_bond(iid, name, currency="USD", ytm=10.0, price=100.0, coupon=8.0,
               freq=2, maturity=date(2030, 1, 1), status="active"):
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


async def _seed():
    async with session_scope() as s:
        s.add(_make_bond("OP-51", "Acme 2029", "USD", ytm=11.5, price=101.2))
        s.add(_make_bond("RU-01", "Gazprom 2027", "RUB", ytm=14.0, price=98.0, coupon=9.0))
        s.add(BondScoreORM(internal_id="OP-51", score=82.0, tier="A",
                           breakdown={}, computed_at=datetime.now(UTC)))
        s.add(BondScoreORM(internal_id="RU-01", score=55.0, tier="C",
                           breakdown={}, computed_at=datetime.now(UTC)))
        s.add(CompanyORM(issuer="Acme Corp", name="Acme Corporation",
                         sector="Technology", description="Эмитент тест."))
        for d, p in [(date(2026, 1, 1), 99.0), (date(2026, 2, 1), 100.1),
                     (date(2026, 3, 1), 101.2)]:
            s.add(BondHistoryORM(internal_id="OP-51", date=d, price=p,
                                 yield_=11.0, status="active"))


def test_seo_bonds_leaderboard():
    async def run():
        await _seed()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/bonds")
            assert resp.status_code == 200
            assert "text/html" in resp.headers["content-type"]
            body = resp.text
            assert "Рейтинг облигаций" in body
            assert "Acme 2029" in body
            assert "OP-51" in body  # internal link to per-bond page
            assert "/bonds/OP-51" in body
            assert "application/ld+json" in body  # structured data

            # Currency filter
            resp = await client.get("/bonds?currency=RUB")
            assert resp.status_code == 200
            assert "Gazprom 2027" in resp.text
            assert "Acme 2029" not in resp.text

    _run(run)


def test_seo_bond_detail():
    async def run():
        await _seed()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/bonds/OP-51")
            assert resp.status_code == 200
            body = resp.text
            assert "Acme 2029" in body
            assert "11.50" in body  # YTM
            assert "82.0" in body or "82" in body  # Score
            assert "Acme Corporation" in body  # issuer from companies
            assert "application/ld+json" in body
            assert "BreadcrumbList" in body
            # CTA funnel to bot / app
            assert "t.me/" in body or "Открыть в" in body

            # Unknown bond -> 404
            resp = await client.get("/bonds/NOPE-999")
            assert resp.status_code == 404

    _run(run)


def test_seo_sitemap_and_robots():
    async def run():
        await _seed()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/sitemap.xml")
            assert resp.status_code == 200
            assert "application/xml" in resp.headers["content-type"]
            assert "<loc>http://test/bonds</loc>" in resp.text
            assert "<loc>http://test/bonds/OP-51</loc>" in resp.text

            resp = await client.get("/robots.txt")
            assert resp.status_code == 200
            assert "Sitemap: http://test/sitemap.xml" in resp.text
            assert "Disallow: /api/" in resp.text

    _run(run)


def test_seo_partners_page():
    # /partners hits no DB, so it validates without the hermetic schema.
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/partners")
            assert resp.status_code == 200
            body = resp.text
            assert "для бизнеса" in body
            assert "Bond API" in body
            assert "Партнёрская программа" in body
            assert "Service" in body  # JSON-LD
            assert "/bonds" in body  # cross-link / funnel

    asyncio.run(run())


def test_seo_partners_lead_form_and_validation():
    # The /partners lead form and its validation hit no DB.
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            page = await client.get("/partners")
            assert page.status_code == 200
            assert 'action="/partners/request"' in page.text
            assert 'name="name"' in page.text
            assert 'name="email"' in page.text
            assert 'name="telegram"' in page.text
            assert 'name="interest"' in page.text
            assert "white-label" in page.text

            # Validation: empty name -> 400 (no DB touched).
            resp = await client.post("/partners/request", data={"name": ""})
            assert resp.status_code == 400

            # Validation: name but no contact -> 400.
            resp = await client.post("/partners/request", data={"name": "Ivan"})
            assert resp.status_code == 400

            # Valid (name + email) would persist to DB; covered by hermetic
            # DB tests in CI. Here we only assert the validation wiring.

    asyncio.run(run())


def test_seo_partners_lead_success():
    # Valid submission self-serves a live Partner API key (onboarding) and links
    # the issued key to the lead. Requires the hermetic schema.
    async def run():
        await _seed()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/partners/request",
                data={
                    "name": "Иван Петров",
                    "email": "ivan@acme.com",
                    "telegram": "ivan_acme",
                    "company": "Acme Invest",
                    "interest": "white-label",
                    "message": "Хотим white-label",
                },
            )
            assert resp.status_code == 200
            body = resp.text
            assert "ak_" in body  # raw key shown once
            assert "/widget/embed.js" in body  # widget snippet
            assert "referral_code=" in body  # affiliate link

            from scraper.orm import PartnerKeyORM, PartnerLeadORM

            async with session_scope() as s:
                leads = (await s.execute(select(PartnerLeadORM))).scalars().all()
                keys = (await s.execute(select(PartnerKeyORM))).scalars().all()
                assert len(leads) == 1
                assert len(keys) == 1
                assert leads[0].partner_key_id == keys[0].id
                assert keys[0].active is True
                assert keys[0].referral_code

    _run(run)


def test_seo_guides():
    # Top-of-funnel guide pages are static (no DB) and cross-link to /bonds + /partners.
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            idx = await client.get("/guides")
            assert idx.status_code == 200
            assert "Гайды по облигациям" in idx.text
            for slug in ("kak-vybrat-obligaciyu", "duration-i-repo-prosto", "obligacii-vs-depozit"):
                assert f"/guides/{slug}" in idx.text

            detail = await client.get("/guides/kak-vybrat-obligaciyu")
            assert detail.status_code == 200
            assert "Как выбрать облигацию" in detail.text
            assert "/bonds" in detail.text
            assert "/partners" in detail.text
            assert "Article" in detail.text  # JSON-LD

            # Unknown guide -> 404
            miss = await client.get("/guides/nope")
            assert miss.status_code == 404

            # Sitemap lists guide pages (resilient even without DB schema).
            sm = await client.get("/sitemap.xml")
            assert sm.status_code == 200
            assert "/guides" in sm.text
            assert "/guides/kak-vybrat-obligaciyu" in sm.text

    asyncio.run(run())


def test_seo_calculator():
    # Calculator is static (no DB). Validates YTM/price/duration math + cross-links.
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # GET page
            resp = await client.get("/calculator")
            assert resp.status_code == 200
            body = resp.text
            assert "Калькулятор облигаций" in body
            assert "YTM" in body
            assert "дюрация" in body
            assert "WebApplication" in body  # JSON-LD

            # YTM from price mode
            resp = await client.get(
                "/calculator",
                params={
                    "mode": "ytm",
                    "face": "1000",
                    "coupon": "8",
                    "freq": "2",
                    "maturity": "5",
                    "price": "1020",
                },
            )
            assert resp.status_code == 200
            assert "7.51" in resp.text or "7.50" in resp.text  # YTM ~7.51%
            assert "дюрация" in resp.text.lower()

            # Price from YTM mode
            resp = await client.get(
                "/calculator",
                params={
                    "mode": "price",
                    "face": "1000",
                    "coupon": "8",
                    "freq": "2",
                    "maturity": "5",
                    "ytm": "7.5",
                },
            )
            assert resp.status_code == 200
            assert "1020" in resp.text or "1021" in resp.text  # price ~1020

            # Sitemap includes /calculator
            sm = await client.get("/sitemap.xml")
            assert sm.status_code == 200
            assert "/calculator" in sm.text

            # Robots allows /calculator
            robots = await client.get("/robots.txt")
            assert robots.status_code == 200
            assert "Allow: /calculator" in robots.text

    asyncio.run(run())


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
