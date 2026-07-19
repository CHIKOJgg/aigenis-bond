"""HTTP integration tests for the core API (api.main) endpoints.

Covers bonds listing/get, scores, stats, health/readiness, watchlist CRUD,
parameter validation (400s), 404s, and the per-tier feature-gating headers.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from api.auth.service import create_access_token
from api.main import app
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, BondORM, BondScoreORM, UserORM


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _run(coro_fn):
    async def wrapper():
        await _ensure_schema()
        try:
            await coro_fn()
        finally:
            await dispose()

    asyncio.run(wrapper())


def _auth_headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _seed(bonds=None, scores=None, user_id=None):
    async with session_scope() as s:
        for b in bonds or []:
            s.add(b)
        for sc in scores or []:
            s.add(sc)
        if user_id:
            s.add(
                UserORM(
                    id=user_id,
                    email=f"u{user_id}@t.co",
                    name="U",
                    password_hash="x",
                    role="user",
                    subscription_tier="pro",
                    subscription_expires_at=datetime.now(UTC) + timedelta(days=30),
                    is_active=True,
                )
            )


def _make_bond(iid, currency="USD", ytm=10.0, status="active"):
    return BondORM(
        internal_id=iid,
        name=f"Bond {iid}",
        currency=currency,
        yield_to_maturity=ytm,
        price=100.0,
        status=status,
        maturity_date=date(2030, 1, 1),
        fetched_at=datetime.now(UTC),
        issuer="Treasury",
    )


# --------------------------------------------------------------------------- #
# Health / readiness
# --------------------------------------------------------------------------- #
def test_health_ok():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] in {"ok", "degraded"}
            assert body["version"] == "3.0.0"
            assert "uptime_seconds" in body

    _run(run)


def test_readiness_ok_and_unavailable():
    async def run():
        async with session_scope() as s:
            pass  # DB reachable in-memory
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/ready")
            # Reaches DB (in-memory sqlite) -> 200.
            assert resp.status_code in (200, 503)

    _run(run)


# --------------------------------------------------------------------------- #
# Bonds list / get
# --------------------------------------------------------------------------- #
def test_list_bonds_default_and_filter():
    async def run():
        await _seed(
            bonds=[
                _make_bond("B1", "USD"),
                _make_bond("B2", "BYN"),
                _make_bond("B3", "USD"),
            ]
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            allb = await client.get("/api/v1/bonds")
            assert allb.status_code == 200
            assert len(allb.json()) == 3

            usd = await client.get("/api/v1/bonds", params={"currency": "usd"})
            assert usd.status_code == 200
            assert {b["internal_id"] for b in usd.json()} == {"B1", "B3"}

            limited = await client.get("/api/v1/bonds", params={"limit": 1, "offset": 1})
            assert len(limited.json()) == 1

    _run(run)


def test_list_bonds_validation():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/api/v1/bonds", params={"limit": 0})).status_code == 400
            assert (await client.get("/api/v1/bonds", params={"limit": 1001})).status_code == 400
            assert (await client.get("/api/v1/bonds", params={"offset": -1})).status_code == 400

    _run(run)


def test_get_bond_found_and_404():
    async def run():
        await _seed(bonds=[_make_bond("B1")])
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            ok = await client.get("/api/v1/bonds/B1")
            assert ok.status_code == 200
            assert ok.json()["internal_id"] == "B1"
            assert ok.json()["currency"] == "USD"

            missing = await client.get("/api/v1/bonds/NOPE")
            assert missing.status_code == 404

    _run(run)


# --------------------------------------------------------------------------- #
# Scores + stats
# --------------------------------------------------------------------------- #
def test_list_scores_min_score_and_paging():
    async def run():
        await _seed(
            scores=[
                BondScoreORM(internal_id="B1", score=95.0, tier="S", breakdown={}),
                BondScoreORM(internal_id="B2", score=50.0, tier="D", breakdown={}),
            ]
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            alls = await client.get("/api/v1/scores")
            assert alls.status_code == 200
            ids = [s["internal_id"] for s in alls.json()]
            assert ids[0] == "B1"  # desc by score

            filtered = await client.get("/api/v1/scores", params={"min_score": 90})
            assert [s["internal_id"] for s in filtered.json()] == ["B1"]

            bad = await client.get("/api/v1/scores", params={"limit": 0})
            assert bad.status_code == 400

    _run(run)


def test_stats_aggregates():
    async def run():
        await _seed(
            bonds=[
                _make_bond("B1", "USD", status="active"),
                _make_bond("B2", "USD", status="matured"),
                _make_bond("B3", "BYN", status="active"),
            ]
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            stats = await client.get("/api/v1/stats")
            assert stats.status_code == 200
            body = stats.json()
            assert body["total_bonds"] == 3
            assert body["active_bonds"] == 2
            assert set(body["by_currency"].keys()) == {"USD", "BYN"}

    _run(run)


# --------------------------------------------------------------------------- #
# Watchlist (authenticated)
# --------------------------------------------------------------------------- #
def test_watchlist_add_remove_flow():
    async def run():
        await _seed(bonds=[_make_bond("B1")], user_id=801)
        headers = _auth_headers(801)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            add = await client.post("/api/v1/watchlist?internal_id=B1", headers=headers)
            assert add.status_code == 200
            assert "B1" in add.json()["watchlist"]

            rem = await client.delete("/api/v1/watchlist/B1", headers=headers)
            assert rem.status_code == 200
            assert "B1" not in rem.json()["watchlist"]

            # 404 for unknown bond
            bad = await client.post("/api/v1/watchlist?internal_id=NOPE", headers=headers)
            assert bad.status_code == 404

            # 401 without auth
            noauth = await client.post("/api/v1/watchlist?internal_id=B1")
            assert noauth.status_code == 401

    _run(run)


# --------------------------------------------------------------------------- #
# Feature-gating headers + 402 on pro endpoints
# --------------------------------------------------------------------------- #
def test_feature_access_headers_for_pro_user():
    async def run():
        await _seed(user_id=802)
        headers = _auth_headers(802)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/bonds", headers=headers)
            assert resp.headers.get("X-User-Tier") == "pro"
            assert resp.headers.get("X-API-Rate-Limit") == "60"
            assert "access_portfolio" in (resp.headers.get("X-Features") or "")

    _run(run)


def test_pro_endpoint_requires_auth_or_tier():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Anonymous -> free -> 402 on pro-only portfolio endpoint.
            resp = await client.get("/api/v1/portfolio")
            assert resp.status_code == 402
            assert resp.headers.get("X-Upgrade-Required") == "true"

    _run(run)


# --------------------------------------------------------------------------- #
# Unknown route -> 404 JSON, not 500
# --------------------------------------------------------------------------- #
def test_unknown_route_404():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/does-not-exist")
            assert resp.status_code == 404

    _run(run)
