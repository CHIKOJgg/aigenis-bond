"""Tests for the demo blueprint — deterministic, fixtures-only responses."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _enable_demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_DISABLE_SIDE_EFFECTS", "1")
    monkeypatch.delenv("AIGENIS_ENV", raising=False)


def test_portfolio_impact_deterministic() -> None:
    resp = client.post(
        "/api/v1/demo/portfolio-impact",
        json={"bond_id": "demo-bond-001", "allocation_pct": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["bond_id"] == "demo-bond-001"
    assert body["allocation_pct"] == 10
    assert body["fixtures_version"] == "v1"
    assert "expected_yield_pct" in body["before"]
    assert "expected_yield_pct" in body["after"]
    assert body["delta_expected_yield_bps"] > 0
    assert body["risk_profile_fit"] in {"ok", "borderline", "off"}


def test_portfolio_impact_unknown_bond_404() -> None:
    resp = client.post(
        "/api/v1/demo/portfolio-impact",
        json={"bond_id": "demo-bond-XXX", "allocation_pct": 5},
    )
    assert resp.status_code == 404


def test_portfolio_impact_invalid_allocation_422() -> None:
    resp = client.post(
        "/api/v1/demo/portfolio-impact",
        json={"bond_id": "demo-bond-001", "allocation_pct": 50},
    )
    assert resp.status_code == 422


def test_portfolio_impact_blocks_in_production() -> None:
    import os

    os.environ["AIGENIS_ENV"] = "production"
    os.environ.pop("DEMO_DISABLE_SIDE_EFFECTS", None)
    try:
        resp = client.post(
            "/api/v1/demo/portfolio-impact",
            json={"bond_id": "demo-bond-001", "allocation_pct": 5},
        )
        assert resp.status_code == 403
    finally:
        os.environ.pop("AIGENIS_ENV", None)
        os.environ["DEMO_DISABLE_SIDE_EFFECTS"] = "1"
