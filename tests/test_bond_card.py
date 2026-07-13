"""Tests for the single-bond deep-dive card and its Pro/free gating."""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx

from api.auth.service import create_access_token
from api.main import app
from scoring.engine import score_bond
from scoring.explain import explain_score
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, BondORM, UserORM


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


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _seed_pro_user_and_bond():
    async with session_scope() as s:
        s.add(
            UserORM(
                id=1,
                email="pro@example.com",
                name="Pro",
                password_hash="x",
                role="user",
                is_active=True,
                is_verified=False,
                subscription_tier="pro",
                subscription_expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        )
        s.add(
            BondORM(
                internal_id="OP-1",
                name="USD Gov Bond",
                currency="USD",
                yield_to_maturity=12.0,
                price=100.0,
                status="active",
                issuer="Министерство финансов",
                maturity_date=date(2031, 1, 1),
                fetched_at=datetime.now(UTC),
            )
        )


def test_explain_score_is_human_readable():
    score = score_bond(
        internal_id="OP-1",
        yield_to_maturity=12.0,
        currency="USD",
        maturity_date=date(2031, 1, 1),
        status="active",
        issuer="Министерство финансов",
        price=100.0,
    )
    explained = explain_score(score, currency="USD", ytm_pct=12.0)
    assert explained.verdict
    assert explained.summary
    assert len(explained.factors) >= 5
    # Factors are sorted by absolute impact.
    impacts = [abs(f.points) for f in explained.factors]
    assert impacts == sorted(impacts, reverse=True)
    # A USD gov bond with 12% yield should have strengths.
    assert explained.strengths


def test_bond_card_free_locks_analysis():
    async def run():
        await _seed_pro_user_and_bond()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # No auth -> free tier -> analysis locked but facts + score visible.
            resp = await client.get("/api/v1/bond/OP-1")
            assert resp.status_code == 200
            body = resp.json()
            assert body["bond"]["internal_id"] == "OP-1"
            assert body["score"] is not None
            assert body["tier"]
            assert body["analysis"] is None
            assert body["analysis_locked"] is True
            assert "upgrade_hint" in body

            # Unknown bond -> 404.
            resp = await client.get("/api/v1/bond/NOPE")
            assert resp.status_code == 404

    _run(run)


def test_bond_card_pro_includes_analysis():
    async def run():
        await _seed_pro_user_and_bond()
        headers = _auth(1)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/bond/OP-1", headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            assert body["analysis_locked"] is False
            assert body["analysis"]["verdict"]
            assert body["analysis"]["factors"]


def test_bond_analysis_endpoint_gated_and_full():
    async def run():
        await _seed_pro_user_and_bond()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Free -> 402.
            resp = await client.get("/api/v1/bond/OP-1/analysis")
            assert resp.status_code == 402

            # Pro -> full payload.
            resp = await client.get("/api/v1/bond/OP-1/analysis", headers=_auth(1))
            assert resp.status_code == 200
            body = resp.json()
            assert body["analysis"]["summary"]
            assert "relative_value" in body
            assert "ml_prediction" in body

    _run(run)
