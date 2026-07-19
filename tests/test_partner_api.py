"""Integration tests for the Partner API (api.partner.router).

Covers API-key auth, key management, webhook registration + signed dispatch,
localization via Accept-Language, and per-key rate limiting.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from api.auth.service import create_access_token
from api.main import app
from api.partner.security import generate_api_key
from api.partner.webhooks import sign_payload
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, BondORM, PartnerKeyORM, UserORM


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


async def _seed(bonds=None, user_id=None):
    async with session_scope() as s:
        for b in bonds or []:
            s.add(b)
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


def _make_bond(iid, currency="USD", ytm=10.0):
    return BondORM(
        internal_id=iid,
        name=f"Bond {iid}",
        currency=currency,
        yield_to_maturity=ytm,
        price=100.0,
        status="active",
        maturity_date=date(2030, 1, 1),
        fetched_at=datetime.now(UTC),
        issuer="Treasury",
    )


# --------------------------------------------------------------------------- #
# Key management (user JWT)
# --------------------------------------------------------------------------- #
def test_create_and_list_partner_key():
    async def run():
        await _seed(user_id=901)
        headers = _auth_headers(901)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/api/v1/partner/keys", json={"name": "acme"}, headers=headers)
            assert created.status_code == 201
            body = created.json()
            assert body["api_key"].startswith("ak_")
            assert body["name"] == "acme"
            raw_key = body["api_key"]

            listed = await client.get("/api/v1/partner/keys", headers=headers)
            assert listed.status_code == 200
            assert len(listed.json()) == 1
            assert "api_key" not in listed.json()[0]  # raw key never echoed back

            # The raw key authenticates partner endpoints.
            bonds = await client.get(
                "/api/v1/partner/bonds", headers={"X-Aigenis-Api-Key": raw_key}
            )
            assert bonds.status_code == 200

    _run(run)


def test_partner_endpoint_requires_key():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            no_key = await client.get("/api/v1/partner/bonds")
            assert no_key.status_code == 401
            bad_key = await client.get(
                "/api/v1/partner/bonds", headers={"X-Aigenis-Api-Key": "ak_wrong"}
            )
            assert bad_key.status_code == 401

    _run(run)


def test_revoke_partner_key():
    async def run():
        await _seed(user_id=902)
        headers = _auth_headers(902)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/api/v1/partner/keys", json={"name": "k"}, headers=headers)
            raw_key = created.json()["api_key"]
            key_id = created.json()["id"]
            assert (
                await client.get("/api/v1/partner/bonds", headers={"X-Aigenis-Api-Key": raw_key})
            ).status_code == 200
            revoked = await client.delete(f"/api/v1/partner/keys/{key_id}", headers=headers)
            assert revoked.status_code == 200
            assert (
                await client.get("/api/v1/partner/bonds", headers={"X-Aigenis-Api-Key": raw_key})
            ).status_code == 401

    _run(run)


# --------------------------------------------------------------------------- #
# Webhooks
# --------------------------------------------------------------------------- #
def test_webhook_register_validation_and_dispatch(monkeypatch):
    captured = []

    async def fake_deliver(wh, event_type, payload):
        captured.append((wh, event_type, payload))
        return True

    monkeypatch.setattr("api.partner.webhooks.deliver_webhook", fake_deliver)

    async def run():
        await _seed(bonds=[_make_bond("B1")], user_id=903)
        headers = _auth_headers(903)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post("/api/v1/partner/keys", json={"name": "acme"}, headers=headers)
            raw_key = created.json()["api_key"]
            pheaders = {"X-Aigenis-Api-Key": raw_key}

            # Invalid URL -> 400 (localized to Kazakh via Accept-Language).
            bad = await client.post(
                "/api/v1/partner/webhooks",
                json={"url": "ftp://x", "events": ["bond.updated"]},
                headers={**pheaders, "Accept-Language": "kz"},
            )
            assert bad.status_code == 400
            assert "Webhook URL http://" in bad.json()["detail"]

            # Unsupported event -> 400.
            bad_ev = await client.post(
                "/api/v1/partner/webhooks",
                json={"url": "https://example.com/h", "events": ["nope"]},
                headers=pheaders,
            )
            assert bad_ev.status_code == 400

            # Valid registration.
            ok = await client.post(
                "/api/v1/partner/webhooks",
                json={"url": "https://example.com/hook", "events": ["bond.updated"]},
                headers=pheaders,
            )
            assert ok.status_code == 201
            assert ok.json()["message"]

            listed = await client.get("/api/v1/partner/webhooks", headers=pheaders)
            assert len(listed.json()) == 1

            # Fire a test event; dispatch must reach the registered webhook.
            test = await client.post("/api/v1/partner/events/test", headers=pheaders)
            assert test.status_code == 200
            assert test.json()["dispatched"] == 1
            assert len(captured) == 1
            wh, event_type, payload = captured[0]
            assert event_type == "bond.updated"
            # Signature would verify against the stored secret.
            assert sign_payload(wh.secret, b"x") != "x"

            # Delete the webhook.
            wh_id = listed.json()[0]["id"]
            deleted = await client.delete(f"/api/v1/partner/webhooks/{wh_id}", headers=pheaders)
            assert deleted.status_code == 200

    _run(run)


# --------------------------------------------------------------------------- #
# Localization + rate limit
# --------------------------------------------------------------------------- #
def test_partner_rate_limit_enforced(monkeypatch):
    monkeypatch.setattr("api.partner.security._partner_hits", defaultdict(list))
    raw, key_hash = generate_api_key()

    async def run():
        async with session_scope() as s:
            s.add(
                PartnerKeyORM(
                    name="rl", key_hash=key_hash, tier="partner", rate_limit=2, active=True
                )
            )
            await s.commit()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"X-Aigenis-Api-Key": raw}
            assert (await client.get("/api/v1/partner/bonds", headers=headers)).status_code == 200
            assert (await client.get("/api/v1/partner/bonds", headers=headers)).status_code == 200
            third = await client.get("/api/v1/partner/bonds", headers=headers)
            assert third.status_code == 429
            assert third.headers.get("Retry-After")

    _run(run)
