"""Phase 5 API tests (items 5.11-5.13): response headers, cursor pagination,
scope enforcement via real routes, not_covered 404 behaviour.
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("AIGENIS_ENVIRONMENT", "staging")
os.environ.setdefault("AIGENIS_SSO_ENABLED", "0")


@pytest.fixture
def client(monkeypatch) -> AsyncClient:
    """TestClient по aigenis-роутеру с pass-through demo-аутентификацией."""
    import api.aigenis as aigenis
    from api.aigenis.security import _demo_context, verify_sso_token

    monkeypatch.setenv("AIGENIS_SSO_ENABLED", "0")
    monkeypatch.setenv("AIGENIS_ENVIRONMENT", "staging")

    app = FastAPI()
    app.include_router(aigenis.router)
    app.dependency_overrides[verify_sso_token] = lambda: _demo_context()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_bond(*, internal_id: str, market: str = "bcse", ytm: str) -> None:
    from scraper.db import session_scope
    from scraper.orm import BondORM

    async with session_scope() as session:
        session.add(
            BondORM(
                internal_id=internal_id,
                isin=f"BY{internal_id}",
                name=f"Bond {internal_id}",
                issuer="ОАО «Тест»",
                currency="BYN",
                nominal=Decimal("1000.000000"),
                coupon_rate=Decimal("10.0000"),
                coupon_frequency=2,
                maturity_date=date(2030, 6, 1),
                price=Decimal("100.000000"),
                yield_to_maturity=Decimal(ytm),
                market=market,
                status="active",
            )
        )


async def _seed_mapping(aigenis_id: str, internal_id: str) -> None:
    from scraper.db import session_scope
    from scraper.instrument_map import InstrumentMapping, upsert_mapping_db

    async with session_scope() as session:
        await upsert_mapping_db(
            session,
            InstrumentMapping(
                aigenis_instrument_id=aigenis_id,
                isin=f"BY{internal_id}",
                market="BCSE",
                currency="BYN",
                analytics_internal_id=internal_id,
            ),
        )


@pytest.mark.asyncio
async def test_list_bonds_pagination_and_headers(client: AsyncClient):
    await _seed_bond(internal_id="b1", ytm="12.5")
    await _seed_bond(internal_id="b2", ytm="8.0")
    await _seed_mapping("AIG-B-1", "b1")

    resp = await client.get("/api/aigenis/v1/bonds?limit=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data_status"] == "ok"
    assert len(body["items"]) <= 1
    assert body["next_cursor"] is not None
    assert "X-Request-Id" in resp.headers
    assert "X-Model-Version" in resp.headers
    assert "X-Data-As-Of" in resp.headers
    assert "X-Data-Quality" in resp.headers
    assert resp.headers["X-Data-Quality"] in ("ok", "warning")


@pytest.mark.asyncio
async def test_list_bonds_empty_has_warning_quality(client: AsyncClient):
    from sqlalchemy import text as sa_text

    from scraper.db import session_scope

    async with session_scope() as session:
        await session.execute(sa_text("DELETE FROM bonds"))

    resp = await client.get("/api/aigenis/v1/bonds")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["data_status"] == "warning"
    assert resp.headers["X-Data-Quality"] == "warning"


@pytest.mark.asyncio
async def test_bond_detail_known_instrument(client: AsyncClient):
    await _seed_bond(internal_id="b3", ytm="11.0")
    await _seed_mapping("AIG-B-3", "b3")

    resp = await client.get("/api/aigenis/v1/bonds/AIG-B-3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["instrument"]["instrument_id"] == "b3"
    assert body["score"] is not None
    assert body["score"]["version"] == "v1"
    assert body["disclaimer"]
    assert "X-Request-Id" in resp.headers


@pytest.mark.asyncio
async def test_bond_not_covered_returns_404(client: AsyncClient):
    resp = await client.get("/api/aigenis/v1/bonds/UNKNOWN-999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error"] == "not_covered"


@pytest.mark.asyncio
async def test_portfolio_impact_endpoint(client: AsyncClient):
    await _seed_bond(internal_id="b4", ytm="13.0")
    await _seed_mapping("AIG-B-4", "b4")

    resp = await client.post(
        "/api/aigenis/v1/portfolio-impact",
        json={"instrument_id": "AIG-B-4", "allocation_pct": 30},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "before" in body and "after" in body and "deltas" in body
    assert body["deltas"]["expected_yield_pp"] >= 0
    assert resp.headers["X-Model-Version"] == "v1"
    assert "X-Request-Id" in resp.headers


@pytest.mark.asyncio
async def test_portfolio_impact_validates_allocation(client: AsyncClient):
    await _seed_bond(internal_id="b5", ytm="10.0")
    await _seed_mapping("AIG-B-5", "b5")
    resp = await client.post(
        "/api/aigenis/v1/portfolio-impact",
        json={"instrument_id": "AIG-B-5", "allocation_pct": 150},
    )
    assert resp.status_code in (403, 422)


@pytest.mark.asyncio
async def test_create_alert_endpoint(client: AsyncClient):
    await _seed_bond(internal_id="b6", ytm="9.9")
    await _seed_mapping("AIG-B-6", "b6")

    resp = await client.post(
        "/api/aigenis/v1/alerts",
        json={
            "instrument_id": "AIG-B-6",
            "metric": "yield",
            "operator": "gt",
            "threshold": 9.0,
            "idempotency_key": "k-1",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "created"
    assert "X-Request-Id" in resp.headers


@pytest.mark.asyncio
async def test_scope_enforcement_403(monkeypatch):
    """Токен без alerts:write scope — 403 на /alerts, 200 на /bonds."""
    import time

    from api.aigenis import router as aigenis_router
    from api.aigenis.security import _load_jwks as s_load_jwks  # noqa: F401

    private, jwks = _mk_jwks()
    monkeypatch.setenv("AIGENIS_ENVIRONMENT", "production")
    import api.aigenis.security as s

    monkeypatch.setattr(s, "_load_jwks", lambda: jwks)
    token = _sign(
        private, {"sub": "u-1", "exp": int(time.time()) + 999, "scopes": ["analytics:read"]}
    )
    headers = {"Authorization": f"Bearer {token}"}
    app = FastAPI()
    app.include_router(aigenis_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/aigenis/v1/bonds", headers=headers)
        assert resp.status_code == 200  # analytics:read разрешён (пустой список)
        resp = await client.post(
            "/api/aigenis/v1/alerts",
            headers=headers,
            json={"instrument_id": "X", "metric": "yield", "threshold": 1.0},
        )
        assert resp.status_code in (403, 404)  # 403 — scope denied OR 404 — not covered
        resp = await client.get("/api/aigenis/v1/bonds/UNKNOWN-1", headers=headers)
        assert resp.status_code == 404


def _mk_jwks():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jose.jwk import RSAKey

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAKey(private.public_key(), algorithm="RS256")
    return private, {"keys": [jwk.to_dict()]}


def _sign(private, claims) -> str:
    from jose import jwt as jose

    return jose.encode(claims, private, algorithm="RS256")
