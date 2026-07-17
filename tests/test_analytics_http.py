"""HTTP-level tests for the analytics API: public subscribe-info and gating.

These use FastAPI's TestClient. The gated endpoints reject anonymous (free)
callers with 402 *before* touching the database, so no DB is required.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_subscribe_info_is_public_and_lists_star_plans():
    resp = client.get("/api/v1/subscribe-info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "telegram_stars"
    tiers = {p["tier"] for p in data["plans"]}
    assert tiers == {"pro", "enterprise"}
    for plan in data["plans"]:
        assert plan["stars"] > 0
        assert plan["duration_days"] > 0


def test_gated_endpoints_return_402_for_anonymous():
    for path in (
        "/api/v1/desk/rv",
        "/api/v1/desk/curve",
        "/api/v1/portfolio",
        "/api/v1/forecast",
        "/api/v1/alerts",
    ):
        resp = client.get(path)
        assert resp.status_code == 402, f"{path} should be gated"
        assert resp.headers.get("X-Upgrade-Required") == "true"


def test_yookassa_billing_plans():
    # YooKassa billing is always mounted; plans endpoint must return lists.
    resp = client.get("/billing/plans")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    plan_ids = {p["id"] for p in data}
    assert "pro" in plan_ids
    assert "enterprise" in plan_ids
