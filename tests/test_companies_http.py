"""HTTP tests for companies, search and detailed recommendations (V6)."""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx

from api.auth.service import create_access_token
from api.main import app
from ml.models import Prediction
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, BondORM, CompanyORM, UserORM


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _seed():
    async with session_scope() as s:
        s.add(UserORM(id=1, email="pro@example.com", name="Pro", password_hash="x",
                      role="user", is_active=True, is_verified=False,
                      subscription_tier="pro",
                      subscription_expires_at=datetime.now(UTC) + timedelta(days=30)))
        s.add(CompanyORM(issuer="ОАО Ромашка", name="ОАО Ромашка", sector="Банки",
                         description="Крупный банк.", why_important="Системно значимый.",
                         updated_at=datetime.now(UTC)))
        for i in range(2):
            s.add(BondORM(internal_id=f"ROM-{i}", name=f"Ромашка {i}", currency="USD",
                          yield_to_maturity=10.0 + i, price=100.0, status="active",
                          issuer="ОАО Ромашка", maturity_date=date(2030, 1, 1),
                          fetched_at=datetime.now(UTC)))


def _stub_predict(monkeypatch):
    def fake(features, *, regressor_path=None, classifier_path=None):
        out = []
        for f in features:
            out.append(Prediction(
                internal_id=f.internal_id, model_version="t", model_kind="ytm_regression",
                asof_date=date(2026, 1, 1), predicted_ytm=5.0, predicted_return_pct=5.0,
                decision="buy", confidence=0.8, feature_importance={},
                explanation=["высокая доходность"], created_at=datetime.now(UTC)))
        return out

    monkeypatch.setattr("recommendations.engine.predict_batch", fake)


def test_companies_endpoint_lists_issuers():
    async def run():
        await _ensure_schema()
        await _seed()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/companies")
            assert resp.status_code == 200
            data = resp.json()
            assert any(c["issuer"] == "ОАО Ромашка" for c in data)
            rom = next(c for c in data if c["issuer"] == "ОАО Ромашка")
            assert rom["bond_count"] == 2
            assert rom["sector"] == "Банки"
        await dispose()

    asyncio.run(run())


def test_company_detail_with_recommendation(monkeypatch):
    _stub_predict(monkeypatch)

    async def run():
        await _ensure_schema()
        await _seed()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/companies/ОАО Ромашка")
            assert resp.status_code == 200
            body = resp.json()
            assert body["name"] == "ОАО Ромашка"
            assert body["why_important"]
            assert len(body["bonds"]) == 2
            assert body["recommendation"] is not None
            assert "reasons" in body["recommendation"]
            assert "risks" in body["recommendation"]
        await dispose()

    asyncio.run(run())


def test_search_finds_bond_and_company():
    async def run():
        await _ensure_schema()
        await _seed()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/search?q=Ромашка")
            assert resp.status_code == 200
            body = resp.json()
            assert any(b["internal_id"].startswith("ROM-") for b in body["bonds"])
            assert any(c["issuer"] == "ОАО Ромашка" for c in body["companies"])
        await dispose()

    asyncio.run(run())


def test_recommendations_include_reasons_risks(monkeypatch):
    _stub_predict(monkeypatch)

    async def run():
        await _ensure_schema()
        await _seed()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/recommendations?top_k=5")
            assert resp.status_code == 200
            data = resp.json()
            assert data
            assert "reasons" in data[0]
            assert "risks" in data[0]
            assert data[0]["decision"] == "buy"
        await dispose()

    asyncio.run(run())
