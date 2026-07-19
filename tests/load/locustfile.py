"""Locust load-test scenario for the Aigenis Bonds API.

Run manually (requires a running server) with e.g.:

    locust -f tests/load/locustfile.py --host http://localhost:8000 \\
           --users 50 --spawn-rate 10 --run-time 1m --headless

The scenario mixes free (read-only) endpoints with an authenticated
endpoint so we exercise the full middleware stack (CORS, rate-limit,
feature-gating headers, DB query path) under realistic mixed traffic.

The CLI also honours these env vars:
    LOAD_USER_ID     — id of a Pro user to authenticate as (default 1)
    LOAD_AUTH_TOKEN  — a pre-generated Bearer token (overrides LOAD_USER_ID)
"""
from __future__ import annotations

import os

from locust import HttpUser, between, task

# A Pro-tier user so the authenticated task can hit gated endpoints.
_USER_ID = int(os.getenv("LOAD_USER_ID", "1"))


def _auth_headers() -> dict[str, str]:
    token = os.getenv("LOAD_AUTH_TOKEN")
    if not token:
        # Generate a token lazily; importing the app pulls in settings but is
        # acceptable for a load-runner process.
        from api.auth.service import create_access_token

        token = create_access_token(_USER_ID)
    return {"Authorization": f"Bearer {token}"}


class ApiUser(HttpUser):
    """Simulates a mix of anonymous browsers and authenticated Pro users."""

    # Think-time between tasks (seconds) to mimic real pacing.
    wait_time = between(0.2, 1.0)

    @task(5)
    def health(self):
        # Cheap liveness probe; should always be 200 (exempt from rate-limit).
        self.client.get("/health", name="GET /health")

    @task(8)
    def list_bonds(self):
        self.client.get("/api/v1/bonds?limit=50", name="GET /api/v1/bonds")

    @task(4)
    def stats(self):
        self.client.get("/api/v1/stats", name="GET /api/v1/stats")

    @task(3)
    def top_scores(self):
        self.client.get("/api/v1/top?limit=20", name="GET /api/v1/top")

    @task(2)
    def bond_card(self):
        # Free tier sees the card without the deep analysis payload.
        self.client.get("/api/v1/bond/B1", name="GET /api/v1/bond/B1")

    @task(2)
    def subscribe_info(self):
        self.client.get("/api/v1/subscribe-info", name="GET /api/v1/subscribe-info")

    @task(3)
    def portfolio_authed(self):
        # Authenticated Pro endpoint — exercises JWT decode + DB + optimizer.
        self.client.get(
            "/api/v1/portfolio",
            headers=_auth_headers(),
            name="GET /api/v1/portfolio (auth)",
        )

    @task(2)
    def recommendations_authed(self):
        self.client.get(
            "/api/v1/recommendations?top_k=10",
            headers=_auth_headers(),
            name="GET /api/v1/recommendations (auth)",
        )
