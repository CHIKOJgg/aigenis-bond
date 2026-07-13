"""Tests for goal-based allocation, rebalance endpoints, and user alerts.

Run against in-memory SQLite. Uses an async HTTP client (ASGITransport) so the
full request path (gating + repositories + optimizer) runs in one event loop.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx

from api.auth.service import create_access_token
from api.main import app
from notifications.alerts_repository import create_rule, list_events
from notifications.alerts_service import run_alert_checks
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


def test_allocate_requires_pro():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/allocate", json={"amount": 10000})
            assert resp.status_code == 402

    _run(run)


def test_goal_allocation_returns_basket():
    async def run():
        await _seed()
        headers = _auth(1)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/allocate",
                headers=headers,
                json={"amount": 10000, "horizon_years": 3, "risk": "Balanced"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["strategy"] == "Balanced"
            assert body["total_allocated"] > 0
            assert len(body["basket"]) > 0
            # Each basket line has a concrete amount + weight.
            assert "amount" in body["basket"][0] and "weight" in body["basket"][0]
            assert body["projection"]["horizon_years"] == 3
            assert body["projection"]["expected_capital"] > 10000

            # Unknown risk is rejected.
            resp = await client.post(
                "/api/v1/allocate", headers=headers, json={"risk": "Nope"}
            )
            assert resp.status_code == 400

    _run(run)


def test_build_plan_and_rebalance():
    async def run():
        await _seed()
        headers = _auth(1)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/build_plan",
                headers=headers,
                json={"positions": [{"internal_id": "OP-1", "amount": 5000},
                                    {"internal_id": "OP-2", "amount": 3000}]},
            )
            assert resp.status_code == 200
            plan = resp.json()
            assert plan["mode"] in ("plan", "ok")
            assert "actions" in plan

            # Rebalance applies to the user's stored positions.
            await client.post(
                "/api/v1/positions", headers=headers,
                json={"internal_id": "OP-1", "amount": 5000},
            )
            await client.post(
                "/api/v1/positions", headers=headers,
                json={"internal_id": "OP-2", "amount": 3000},
            )
            resp = await client.post("/api/v1/rebalance", headers=headers)
            assert resp.status_code == 200
            assert "rebalanced" in resp.json()

    _run(run)


def test_alert_rules_crud_and_feed():
    async def run():
        await _seed()
        headers = _auth(1)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Unknown bond rejected.
            resp = await client.post(
                "/api/v1/alerts/rules",
                headers=headers,
                json={"internal_id": "NOPE", "metric": "price", "direction": "below", "threshold": 95},
            )
            assert resp.status_code == 404

            # Create a rule.
            resp = await client.post(
                "/api/v1/alerts/rules",
                headers=headers,
                json={"internal_id": "OP-1", "metric": "price", "direction": "below", "threshold": 95},
            )
            assert resp.status_code == 200
            rule_id = resp.json()["id"]
            assert resp.json()["threshold"] == 95.0

            # Listed.
            resp = await client.get("/api/v1/alerts/rules", headers=headers)
            assert resp.status_code == 200
            assert len(resp.json()) == 1

            # Feed is empty before the check runs.
            resp = await client.get("/api/v1/alerts/feed", headers=headers)
            assert resp.status_code == 200
            assert resp.json() == []

            # Delete.
            resp = await client.delete(f"/api/v1/alerts/rules/{rule_id}", headers=headers)
            assert resp.status_code == 200
            resp = await client.get("/api/v1/alerts/rules", headers=headers)
            assert resp.json() == []

    _run(run)


def test_alert_service_fires_and_dedupes():
    async def run():
        await _seed()
        async with session_scope() as s:
            await create_rule(
                s, user_id=1, internal_id="OP-1", metric="price",
                direction="below", threshold=101,  # 100 <= 101 -> fires
            )
        fired = await run_alert_checks()
        assert fired == 1
        async with session_scope() as s:
            events = await list_events(s, 1)
            assert len(events) == 1
            assert "OP-1" in events[0].message

        # Second run within 24h must not duplicate.
        fired = await run_alert_checks()
        assert fired == 0
        async with session_scope() as s:
            assert len(await list_events(s, 1)) == 1

    _run(run)
