"""Tests for the personalized web portfolio (positions + portfolio + plan).

Run against the project's in-memory SQLite default. Uses an async HTTP client
(ASGITransport) so the whole request path — auth gating, repositories, the
optimizer — is exercised in a single event loop against one shared SQLite
connection.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx

from api.auth.service import create_access_token
from api.main import app
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


def _auth_headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _seed():
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
                name="USD Bond 1",
                currency="USD",
                yield_to_maturity=10.0,
                price=100.0,
                status="active",
                maturity_date=date(2030, 1, 1),
                fetched_at=datetime.now(UTC),
            )
        )
        s.add(
            BondORM(
                internal_id="OP-2",
                name="BYN Bond 2",
                currency="BYN",
                yield_to_maturity=8.0,
                price=99.0,
                status="active",
                maturity_date=date(2029, 1, 1),
                fetched_at=datetime.now(UTC),
            )
        )


def test_positions_require_pro_tier():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/positions")
            assert resp.status_code == 402
            assert resp.headers.get("X-Upgrade-Required") == "true"

    _run(run)


def test_personal_portfolio_flow():
    async def run():
        await _seed()
        headers = _auth_headers(1)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # No positions yet -> recommendation mode (not the old hard-coded default).
            resp = await client.get("/api/v1/portfolio", headers=headers)
            assert resp.status_code == 200
            assert resp.json()["mode"] == "recommendation"

            # Add two positions.
            resp = await client.post(
                "/api/v1/positions", headers=headers, json={"internal_id": "OP-1", "amount": 5000}
            )
            assert resp.status_code == 200
            resp = await client.post(
                "/api/v1/positions", headers=headers, json={"internal_id": "OP-2", "amount": 3000}
            )
            assert resp.status_code == 200

            # List reflects real holdings + total.
            resp = await client.get("/api/v1/positions", headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            assert body["total_invested"] == 8000.0
            assert {p["internal_id"] for p in body["positions"]} == {"OP-1", "OP-2"}

            # Portfolio endpoint now reports the user's actual holdings.
            resp = await client.get("/api/v1/portfolio", headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            assert body["mode"] == "portfolio"
            assert body["positions_count"] == 2
            assert body["total_invested"] == 8000.0
            assert len(body["holdings"]) == 2
            assert body["strategy"]  # personalized, non-empty

            # Rebalance plan is produced from real positions.
            resp = await client.get("/api/v1/portfolio/plan", headers=headers)
            assert resp.status_code == 200
            plan = resp.json()
            assert plan["mode"] == "portfolio"

            # Unknown bond is rejected.
            resp = await client.post(
                "/api/v1/positions", headers=headers, json={"internal_id": "NOPE", "amount": 100}
            )
            assert resp.status_code == 404

            # Delete a position.
            resp = await client.delete("/api/v1/positions/OP-1", headers=headers)
            assert resp.status_code == 200
            resp = await client.get("/api/v1/positions", headers=headers)
            assert resp.json()["total_invested"] == 3000.0

    _run(run)


def test_forecast_uses_user_preferences():
    async def run():
        await _seed()
        # Give the user a distinct capital so the forecast reflects it.
        from scoring.models import UserPreferences
        from telegram_bot.preferences_repository import upsert_preferences

        async with session_scope() as s:
            await upsert_preferences(
                s,
                UserPreferences(
                    user_id=1,
                    initial_capital=12345,
                    monthly_contribution=100,
                    strategy="Balanced",
                ),
            )

        headers = _auth_headers(1)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/forecast", headers=headers)
            assert resp.status_code == 200
            expected = resp.json()[0]["expected_capital"]
            # 12345 growing at 7%/yr over 1y + monthly 100 must exceed the principal.
            assert expected > 12345

    _run(run)
