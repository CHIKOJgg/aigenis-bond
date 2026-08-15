"""Comprehensive pytest suite for the money-critical API routers and helpers.

Coverage:
  * api/billing/router.py      — /billing/plans, /billing/create-payment,
                                 /billing/subscription, /billing/webhook and the
                                 webhook IP-allowlist helpers
  * api/partner/webhooks.py    — HMAC payload signing, webhook CRUD, SSRF guard
                                 (_is_private_host / _pin_public_ip), signed
                                 delivery, event emission
  * api/notifications/reminders.py — expiry scheduling math (_days_until) and
                                 notify_expiring_trials (email + Telegram)
  * api/analytics/_helpers.py  — _all_bonds / _get_bond_or_404 / _score_for_bond

Run only this file:
    python -m pytest tests/test_audit_billing_router.py -q -p no:warnings --tb=short

Notes:
  * Tests are plain async functions (pytest-asyncio asyncio_mode=auto).
  * The in-memory DB is shared across the whole run (conftest create_all per
    test, tables are never dropped), so every test seeds DISTINCT user ids and
    its own partner keys/webhooks, and asserts relative counts only.
  * No real network: YooKassa / webhook HTTP clients and DNS resolution are
    monkeypatched; reminder email/bot delivery is faked.
  * Tests that expose genuine source bugs are marked "# KNOWN-FAILING" and
    reported at the bottom of the file.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import socket
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from api.auth.service import create_access_token
from api.billing import service as billing_service
from api.billing.router import (
    _allowed_networks,
    _client_ip,
    _ip_allowed,
)
from api.main import app
from api.notifications import reminders as reminders_mod
from api.partner import webhooks as partner_webhooks
from scraper.db import session_scope
from scraper.orm import (
    BondORM,
    BondScoreORM,
    PartnerKeyORM,
    SubscriptionORM,
    UserORM,
    WebhookORM,
)

# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
_YOOKASSA_IP = "185.71.76.1"  # inside YooKassa's published 185.71.76.0/27
_FOREIGN_IP = "203.0.113.7"


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _seed_user(
    uid: int,
    tier: str = "free",
    expires_days: int | None = None,
    trial_days: int | None = None,
    email: str | None = None,
    telegram_id: int | None = None,
    expires_at: datetime | None = None,
    trial_end: datetime | None = None,
) -> int:
    # Use the reminders module clock: when reminder tests freeze "now" via
    # monkeypatch, seeded expiries stay relative to the frozen instant.
    now = reminders_mod.datetime.now(UTC)
    async with session_scope() as s:
        s.add(
            UserORM(
                id=uid,
                email=email if email is not None else f"br{uid}@t.co",
                name=f"User {uid}",
                password_hash="x",
                role="user",
                subscription_tier=tier,
                subscription_expires_at=(
                    expires_at
                    if expires_at is not None
                    else (now + timedelta(days=expires_days) if expires_days is not None else None)
                ),
                trial_end=(
                    trial_end
                    if trial_end is not None
                    else (now + timedelta(days=trial_days) if trial_days is not None else None)
                ),
                telegram_id=telegram_id,
                is_active=True,
                is_verified=False,
            )
        )
    return uid


async def _seed_subscription(
    uid: int,
    *,
    payment_id: str | None = None,
    plan: str = "pro",
    status: str = "active",
    cancel_at_period_end: bool = False,
) -> None:
    now = datetime.now(UTC)
    async with session_scope() as s:
        s.add(
            SubscriptionORM(
                user_id=uid,
                yookassa_payment_id=payment_id,
                plan=plan,
                status=status,
                current_period_start=now,
                current_period_end=now + timedelta(days=30),
                cancel_at_period_end=cancel_at_period_end,
            )
        )


async def _seed_bond(
    iid: str,
    *,
    currency: str = "USD",
    ytm: float = 10.0,
    price: float = 100.0,
    maturity: date = date(2030, 1, 1),
    issuer: str = "Treasury",
) -> str:
    async with session_scope() as s:
        s.add(
            BondORM(
                internal_id=iid,
                name=f"Bond {iid}",
                currency=currency,
                yield_to_maturity=Decimal(str(ytm)),
                price=Decimal(str(price)),
                coupon_frequency=2,
                maturity_date=maturity,
                issuer=issuer,
                nominal=Decimal("1000"),
                status="active",
            )
        )
    return iid


async def _seed_partner_key(owner_uid: int, name: str, *, rate_limit: int = 120) -> int:
    async with session_scope() as s:
        pk = PartnerKeyORM(
            name=name,
            owner_user_id=owner_uid,
            key_hash=f"h-{name}",
            key_fp=f"fp-{name}",
            tier="partner",
            rate_limit=rate_limit,
            active=True,
            referral_code=f"RC{abs(hash(name)) % 100000}",
        )
        s.add(pk)
        await s.flush()
        return pk.id


async def _count(model, *where) -> int:
    from sqlalchemy import func, select

    stmt = select(func.count()).select_from(model)
    if where:
        stmt = stmt.where(*where)
    async with session_scope() as s:
        return (await s.execute(stmt)).scalar_one()


async def _purge_webhooks() -> None:
    """Remove webhooks left behind by earlier tests in the shared in-memory DB.

    The suite never drops tables, so emission tests that assert absolute
    delivery counts must start from a clean WebhookORM table.
    """
    from sqlalchemy import delete

    async with session_scope() as s:
        await s.execute(delete(WebhookORM))


def _make_client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _webhook_headers(ip: str = _YOOKASSA_IP, **extra) -> dict[str, str]:
    headers = {"X-Forwarded-For": ip}
    headers.update(extra)
    return headers


# =========================================================================== #
# 1. api/billing/router.py
# =========================================================================== #


# --- /billing/plans -------------------------------------------------------- #
async def test_billing_plans_endpoint_shape():
    async with _make_client() as client:
        resp = await client.get("/billing/plans")
        assert resp.status_code == 200
        plans = resp.json()
        assert [p["id"] for p in plans] == ["free", "pro", "enterprise"]
        for p in plans:
            assert p["currency"] == "BYN"
            assert isinstance(p["features"], list) and p["features"]
        assert plans[0]["price"] == 0
        assert plans[1]["price"] == float(billing_service.PLANS["pro"]["price"])
        assert plans[2]["price"] == float(billing_service.PLANS["enterprise"]["price"])


# --- /billing/create-payment ----------------------------------------------- #
async def test_create_payment_requires_auth():
    async with _make_client() as client:
        resp = await client.post("/billing/create-payment", json={"plan": "pro"})
        assert resp.status_code == 401


async def test_create_payment_unconfigured_yookassa_503():
    assert billing_service.is_yookassa_configured() is False  # empty creds in tests
    uid = await _seed_user(20001)
    async with _make_client() as client:
        resp = await client.post(
            "/billing/create-payment",
            json={"plan": "pro", "success_url": "https://aigenis.by/ok"},
            headers=_auth(uid),
        )
        assert resp.status_code == 503
        assert "YOOKASSA_SHOP_ID" in resp.json()["detail"]


async def test_create_payment_unknown_plan_400(monkeypatch):
    monkeypatch.setattr("api.billing.router.is_yookassa_configured", lambda: True)
    uid = await _seed_user(20002)

    async def must_not_call(**kwargs):
        raise AssertionError("service must not be called for an unknown plan")

    monkeypatch.setattr("api.billing.service.create_payment", must_not_call)
    async with _make_client() as client:
        resp = await client.post(
            "/billing/create-payment",
            json={"plan": "gold", "success_url": "https://aigenis.by/ok"},
            headers=_auth(uid),
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Неизвестный тариф"


async def test_create_payment_success_url_validation_400(monkeypatch):
    monkeypatch.setattr("api.billing.router.is_yookassa_configured", lambda: True)
    uid = await _seed_user(20003)
    async with _make_client() as client:
        # Non-HTTPS scheme is rejected.
        r1 = await client.post(
            "/billing/create-payment",
            json={"plan": "pro", "success_url": "http://aigenis.by/ok"},
            headers=_auth(uid),
        )
        assert r1.status_code == 400
        # Absolute URL to a domain outside the allowlist is rejected (open-redirect guard).
        r2 = await client.post(
            "/billing/create-payment",
            json={"plan": "pro", "success_url": "https://evil.example/steal"},
            headers=_auth(uid),
        )
        assert r2.status_code == 400
        assert "success_url domain is not allowed" in r2.json()["detail"]


async def test_create_payment_happy_path_200(monkeypatch):
    monkeypatch.setattr("api.billing.router.is_yookassa_configured", lambda: True)
    uid = await _seed_user(20004)
    calls = []

    async def fake_create(user, plan, success_url, referral_code=None):
        calls.append((user.id, plan, success_url, referral_code))
        return {
            "payment_id": "pay-created-20004",
            "status": "pending",
            "confirmation_url": "https://pay.example/confirm/20004",
        }

    monkeypatch.setattr("api.billing.service.create_payment", fake_create)
    async with _make_client() as client:
        resp = await client.post(
            "/billing/create-payment",
            json={
                "plan": "enterprise",
                "success_url": "https://aigenis.by/ok",
                "referral_code": "P1",
            },
            headers=_auth(uid),
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "payment_id": "pay-created-20004",
            "confirmation_url": "https://pay.example/confirm/20004",
        }
    assert calls == [(uid, "enterprise", "https://aigenis.by/ok", "P1")]


async def test_create_payment_user_not_found_404(monkeypatch):
    monkeypatch.setattr("api.billing.router.is_yookassa_configured", lambda: True)
    async with _make_client() as client:
        resp = await client.post(
            "/billing/create-payment",
            json={"plan": "pro", "success_url": "https://aigenis.by/ok"},
            headers=_auth(299999),  # token is valid but the user does not exist
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Пользователь не найден"


async def test_create_payment_service_failure_500(monkeypatch):
    monkeypatch.setattr("api.billing.router.is_yookassa_configured", lambda: True)
    uid = await _seed_user(20005)
    monkeypatch.setattr("api.billing.service.create_payment", _async_none)
    async with _make_client() as client:
        resp = await client.post(
            "/billing/create-payment",
            json={"plan": "pro", "success_url": "https://aigenis.by/ok"},
            headers=_auth(uid),
        )
        assert resp.status_code == 500


# Regression: the schema's own default success_url must be accepted.
# CreatePaymentRequest.success_url defaults to "/?billing=success", which the
# router resolves against APP_BASE_URL (https://app.aigenis.by). The router
# must allow the APP_BASE_URL host and compare hostnames without ports.
async def test_create_payment_default_success_url_resolved_and_allowed(monkeypatch):
    monkeypatch.setattr("api.billing.router.is_yookassa_configured", lambda: True)
    uid = await _seed_user(20006)
    calls = []

    async def fake_create(user, plan, success_url, referral_code=None):
        calls.append(success_url)
        return {"payment_id": "pay-dflt", "confirmation_url": "https://pay.example/c"}

    monkeypatch.setattr("api.billing.service.create_payment", fake_create)
    async with _make_client() as client:
        resp = await client.post(
            "/billing/create-payment",
            json={"plan": "pro"},  # no success_url -> schema default
            headers=_auth(uid),
        )
        assert resp.status_code == 200
    assert len(calls) == 1
    resolved = calls[0]
    assert resolved.startswith("https://")
    assert resolved.endswith("/?billing=success")
    assert "app.aigenis.by" in resolved or "aigenis.by" in resolved


# --- /billing/subscription ------------------------------------------------- #
async def test_subscription_requires_auth():
    async with _make_client() as client:
        resp = await client.get("/billing/subscription")
        assert resp.status_code == 401


async def test_subscription_no_record_inactive():
    uid = await _seed_user(20007, tier="free")
    async with _make_client() as client:
        resp = await client.get("/billing/subscription", headers=_auth(uid))
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"] == "free"
        assert body["status"] == "inactive"
        assert body["provider"] == "yookassa"
        assert body["current_period_start"] is None
        assert body["current_period_end"] is None


async def test_subscription_trial_grants_pro_label():
    uid = await _seed_user(20008, tier="free", trial_days=7)
    async with _make_client() as client:
        resp = await client.get("/billing/subscription", headers=_auth(uid))
        assert resp.status_code == 200
        body = resp.json()
        # effective_tier treats an active trial as pro.
        assert body["plan"] == "pro"
        assert body["status"] == "inactive"


async def test_subscription_active_record_shape():
    uid = await _seed_user(20009, tier="pro", expires_days=30)
    await _seed_subscription(uid, payment_id="pay-20009", cancel_at_period_end=True)
    async with _make_client() as client:
        resp = await client.get("/billing/subscription", headers=_auth(uid))
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"] == "pro"
        assert body["status"] == "active"
        assert body["cancel_at_period_end"] is True
        assert body["current_period_start"] is not None
        assert body["current_period_end"] is not None


async def test_subscription_user_not_found_404():
    async with _make_client() as client:
        resp = await client.get("/billing/subscription", headers=_auth(299998))
        assert resp.status_code == 404


# --- /billing/webhook + IP allowlist helpers ------------------------------- #
def test_webhook_ip_helper_functions(monkeypatch):
    monkeypatch.delenv("YOOKASSA_WEBHOOK_IPS", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY", raising=False)

    # _allowed_networks defaults to the published YooKassa ranges.
    assert len(_allowed_networks()) == 7

    assert _ip_allowed("185.71.76.1") is True  # inside 185.71.76.0/27
    assert _ip_allowed("185.71.76.33") is False  # just outside /27
    assert _ip_allowed("77.75.156.11") is True  # exact /32 entry
    assert _ip_allowed("77.75.156.12") is False  # outside the /32
    assert _ip_allowed("2a02:5180::1") is True  # IPv6 2a02:5180::/32
    assert _ip_allowed(_FOREIGN_IP) is False
    assert _ip_allowed(None) is False
    assert _ip_allowed("not-an-ip") is False

    # _client_ip: with TRUSTED_PROXY the last XFF hop wins.
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    req = SimpleNamespace(
        client=_FakeAddress("127.0.0.1"),
        headers={"x-forwarded-for": "10.0.0.1, 185.71.76.1"},
    )
    assert _client_ip(req) == "185.71.76.1"
    # Without TRUSTED_PROXY the raw socket peer is used (XFF is ignored).
    monkeypatch.delenv("TRUSTED_PROXY", raising=False)
    assert _client_ip(req) == "127.0.0.1"


def test_allowed_networks_override_and_invalid_cidr(monkeypatch):
    monkeypatch.setenv("YOOKASSA_WEBHOOK_IPS", "10.0.0.0/8, garbage-cidr, 192.168.0.0/16")
    nets = _allowed_networks()  # invalid entry is skipped with a warning
    assert len(nets) == 2
    monkeypatch.setenv("YOOKASSA_WEBHOOK_IPS", "10.0.0.0/8")
    assert _ip_allowed("10.20.30.40") is True
    assert _ip_allowed(_FOREIGN_IP) is False


async def test_webhook_rejects_non_yookassa_ip(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    monkeypatch.delenv("YOOKASSA_WEBHOOK_IPS", raising=False)
    async with _make_client() as client:
        resp = await client.post(
            "/billing/webhook",
            json={"event": "payment.succeeded", "object": {"id": "p1"}},
            headers=_webhook_headers(ip=_FOREIGN_IP),
        )
        assert resp.status_code == 403


async def test_webhook_accepts_allowed_ip_invalid_json_400(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    monkeypatch.delenv("YOOKASSA_WEBHOOK_IPS", raising=False)
    async with _make_client() as client:
        resp = await client.post(
            "/billing/webhook",
            content=b"not json {{{",
            headers=_webhook_headers(),
        )
        assert resp.status_code == 400


async def test_webhook_unknown_event_accepted_200(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    monkeypatch.delenv("YOOKASSA_WEBHOOK_IPS", raising=False)
    async with _make_client() as client:
        resp = await client.post(
            "/billing/webhook",
            content=json.dumps(
                {"event": "payment.something.new", "object": {"id": "p-new"}}
            ).encode(),
            headers=_webhook_headers(),
        )
        assert resp.status_code == 200
        assert resp.json() == {"received": True, "type": "payment.something.new"}


async def test_webhook_unverified_payment_400(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    monkeypatch.delenv("YOOKASSA_WEBHOOK_IPS", raising=False)

    async def fake_fetch_payment(pid):
        return None  # YooKassa API does not confirm this forged id

    monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
    async with _make_client() as client:
        resp = await client.post(
            "/billing/webhook",
            content=json.dumps({"event": "payment.succeeded", "object": {"id": "forged"}}).encode(),
            headers=_webhook_headers(),
        )
        assert resp.status_code == 400


async def test_webhook_ip_override_star_disables_filtering(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    monkeypatch.setenv("YOOKASSA_WEBHOOK_IPS", "*")  # staging override, NOT recommended
    async with _make_client() as client:
        resp = await client.post(
            "/billing/webhook",
            content=json.dumps({"event": "payment.ignored", "object": {"id": "x"}}).encode(),
            headers=_webhook_headers(ip=_FOREIGN_IP),
        )
        assert resp.status_code == 200


# =========================================================================== #
# 2. api/partner/webhooks.py
# =========================================================================== #


# --- HMAC signing ---------------------------------------------------------- #
def test_sign_payload_deterministic_hmac():
    body = b'{"event":"bond.updated","payload":{}}'
    sig = partner_webhooks.sign_payload("s3cret", body)
    expected = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert sig == expected
    assert partner_webhooks.sign_payload("s3cret", body) == sig  # deterministic
    assert partner_webhooks.sign_payload("other", body) != sig  # secret matters
    assert partner_webhooks.sign_payload("s3cret", b"other") != sig  # body matters


# --- CRUD ------------------------------------------------------------------ #
async def test_webhook_register_and_list():
    owner = await _seed_user(20100)
    pk_id = await _seed_partner_key(owner, "crud-1")
    wh = await partner_webhooks.register_webhook(
        partner_key_id=pk_id,
        url="https://hook.example/a",
        events=["bond.updated", "price.crossed"],
        secret="top-secret",
    )
    assert wh.id > 0
    assert wh.secret == "top-secret"
    assert sorted(wh.events) == ["bond.updated", "price.crossed"]
    assert wh.active is True

    rows = await partner_webhooks.list_webhooks(pk_id)
    assert len(rows) == 1
    assert rows[0].id == wh.id

    # A different partner must not see this webhook.
    pk_id_2 = await _seed_partner_key(owner, "crud-2")
    assert await partner_webhooks.list_webhooks(pk_id_2) == []

    await partner_webhooks.delete_webhook(pk_id, wh.id)  # clean up shared DB


async def test_webhook_get_scoped_to_partner():
    owner = await _seed_user(20101)
    pk1 = await _seed_partner_key(owner, "scope-1")
    pk2 = await _seed_partner_key(owner, "scope-2")
    wh = await partner_webhooks.register_webhook(
        partner_key_id=pk1, url="https://hook.example/s", events=["analysis.ready"], secret="s"
    )
    assert (await partner_webhooks.get_webhook(pk1, wh.id)) is not None
    assert await partner_webhooks.get_webhook(pk2, wh.id) is None
    assert await partner_webhooks.get_webhook(pk1, 999999) is None
    await partner_webhooks.delete_webhook(pk1, wh.id)  # clean up shared DB


async def test_webhook_delete_idempotent():
    owner = await _seed_user(20102)
    pk = await _seed_partner_key(owner, "del-1")
    wh = await partner_webhooks.register_webhook(
        partner_key_id=pk, url="https://hook.example/d", events=["bond.updated"], secret="s"
    )
    assert await partner_webhooks.delete_webhook(pk, wh.id) is True
    assert await partner_webhooks.get_webhook(pk, wh.id) is None
    assert await partner_webhooks.delete_webhook(pk, wh.id) is False  # already gone
    # Deleting a webhook owned by another partner is a no-op.
    pk2 = await _seed_partner_key(owner, "del-2")
    assert await partner_webhooks.delete_webhook(pk2, wh.id) is False


# --- SSRF guards ----------------------------------------------------------- #
def test_is_private_host_literals():
    for url in (
        "https://localhost/hook",
        "https://127.0.0.1/hook",
        "https://[::1]/hook",
        "https://0.0.0.0/hook",
        "https://10.1.2.3/hook",
        "https://192.168.1.1/hook",
        "https://172.16.0.1/hook",
        "https://169.254.1.1/hook",
        "https://224.0.0.1/hook",  # multicast
        "http://svc.internal/hook",
        "https://nas.local/hook",
        "https://printer.localhost/hook",
    ):
        assert partner_webhooks._is_private_host(url) is True, url
    assert partner_webhooks._is_private_host("https://8.8.8.8/hook") is False
    assert partner_webhooks._is_private_host("https://93.184.216.34/hook") is False


def test_is_private_host_resolved_dns(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host == "private.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.9", port))]
        if host == "public.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        raise socket.gaierror("no such host")

    monkeypatch.setattr(partner_webhooks.socket, "getaddrinfo", fake_getaddrinfo)
    assert partner_webhooks._is_private_host("https://private.example/hook") is True
    assert partner_webhooks._is_private_host("https://public.example/hook") is False
    assert partner_webhooks._is_private_host("https://doesnotresolve.example/hook") is False


def test_pin_public_ip_literal_and_private():
    assert partner_webhooks._pin_public_ip("8.8.8.8") == ("8.8.8.8", "8.8.8.8")
    assert partner_webhooks._pin_public_ip("10.0.0.1") is None
    assert partner_webhooks._pin_public_ip("") is None


def test_pin_public_ip_dns(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host == "public.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        if host == "ipv6.example":
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1::1", port))]
        if host == "private.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.0.5", port))]
        raise socket.gaierror("no such host")

    monkeypatch.setattr(partner_webhooks.socket, "getaddrinfo", fake_getaddrinfo)
    assert partner_webhooks._pin_public_ip("public.example") == ("93.184.216.34", "public.example")
    assert partner_webhooks._pin_public_ip("ipv6.example") == (
        "[2606:2800:220:1::1]",
        "ipv6.example",
    )
    assert partner_webhooks._pin_public_ip("private.example") is None
    assert partner_webhooks._pin_public_ip("missing.example") is None


# --- delivery -------------------------------------------------------------- #
class _FakeHttpxClient:
    """Drop-in httpx.AsyncClient that records the outgoing request."""

    status: int = 200
    exc: Exception | None = None
    instances: list[_FakeHttpxClient] = []

    def __init__(self, *args, **kwargs):
        self.calls: list[tuple[str, dict]] = []
        _FakeHttpxClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if _FakeHttpxClient.exc is not None:
            raise _FakeHttpxClient.exc
        return SimpleNamespace(status_code=_FakeHttpxClient.status)


def _patch_httpx_client(monkeypatch):
    _FakeHttpxClient.status = 200
    _FakeHttpxClient.exc = None
    _FakeHttpxClient.instances = []
    monkeypatch.setattr(partner_webhooks.httpx, "AsyncClient", _FakeHttpxClient)
    return _FakeHttpxClient


async def test_deliver_webhook_success_records_delivery(monkeypatch):
    fake_cls = _patch_httpx_client(monkeypatch)
    owner = await _seed_user(20103)
    pk = await _seed_partner_key(owner, "dlv-1")
    wh = await partner_webhooks.register_webhook(
        partner_key_id=pk,
        url="https://8.8.8.8/hook",  # literal public IP -> no DNS, no rewrite
        events=["bond.updated"],
        secret="s3cret",
    )

    ok = await partner_webhooks.deliver_webhook(wh, "bond.updated", {"internal_id": "B1"})
    assert ok is True

    client = fake_cls.instances[0]
    url, kwargs = client.calls[0]
    assert url == "https://8.8.8.8/hook"
    body = json.loads(kwargs["content"])
    assert body["event"] == "bond.updated"
    assert body["payload"] == {"internal_id": "B1"}
    assert "timestamp" in body
    assert kwargs["headers"]["Host"] == "8.8.8.8"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["headers"]["X-Aigenis-Event"] == "bond.updated"
    expected_sig = partner_webhooks.sign_payload("s3cret", kwargs["content"])
    assert kwargs["headers"]["X-Aigenis-Signature"] == f"sha256={expected_sig}"

    async with session_scope() as s:
        row = await s.get(WebhookORM, wh.id)
        assert row.last_delivered_at is not None
        assert row.last_error is None


async def test_deliver_webhook_non_2xx_records_error(monkeypatch):
    _patch_httpx_client(monkeypatch)
    _FakeHttpxClient.status = 500
    owner = await _seed_user(20104)
    pk = await _seed_partner_key(owner, "dlv-2")
    wh = await partner_webhooks.register_webhook(
        partner_key_id=pk, url="https://8.8.8.8/hook", events=["bond.updated"], secret="s"
    )

    ok = await partner_webhooks.deliver_webhook(wh, "bond.updated", {})
    assert ok is False
    async with session_scope() as s:
        row = await s.get(WebhookORM, wh.id)
        assert row.last_error == "HTTP 500"
        assert row.last_delivered_at is None


async def test_deliver_webhook_exception_records_error(monkeypatch):
    _patch_httpx_client(monkeypatch)
    _FakeHttpxClient.exc = httpx.ConnectError("connection refused")
    owner = await _seed_user(20105)
    pk = await _seed_partner_key(owner, "dlv-3")
    wh = await partner_webhooks.register_webhook(
        partner_key_id=pk, url="https://8.8.8.8/hook", events=["bond.updated"], secret="s"
    )

    ok = await partner_webhooks.deliver_webhook(wh, "bond.updated", {})
    assert ok is False
    async with session_scope() as s:
        row = await s.get(WebhookORM, wh.id)
        assert row.last_error == "connection refused"
        assert row.last_delivered_at is None


async def test_deliver_webhook_ssrf_blocked_no_call(monkeypatch):
    fake_cls = _patch_httpx_client(monkeypatch)
    owner = await _seed_user(20106)
    pk = await _seed_partner_key(owner, "dlv-4")
    for private_url in (
        "https://127.0.0.1/hook",
        "https://localhost/hook",
        "https://10.0.0.5/hook",
    ):
        wh = await partner_webhooks.register_webhook(
            partner_key_id=pk, url=private_url, events=["bond.updated"], secret="s"
        )
        ok = await partner_webhooks.deliver_webhook(wh, "bond.updated", {})
        assert ok is False, private_url
    assert fake_cls.instances == []  # the HTTP client was never constructed


# --- event emission -------------------------------------------------------- #
async def test_emit_webhook_event_matches_subscriptions(monkeypatch):
    captured = []

    async def fake_deliver(wh, event_type, payload):
        captured.append((wh.id, event_type, payload))
        return True

    monkeypatch.setattr(partner_webhooks, "deliver_webhook", fake_deliver)
    await _purge_webhooks()  # dlv-* tests left active bond.updated webhooks in the shared DB

    owner = await _seed_user(20107)
    pk = await _seed_partner_key(owner, "emit-1")
    wh_a = await partner_webhooks.register_webhook(
        partner_key_id=pk, url="https://8.8.8.8/a", events=["bond.updated"], secret="s"
    )
    wh_b = await partner_webhooks.register_webhook(
        partner_key_id=pk, url="https://8.8.8.8/b", events=["alert.triggered"], secret="s"
    )
    wh_c = await partner_webhooks.register_webhook(
        partner_key_id=pk, url="https://8.8.8.8/c", events=["bond.updated"], secret="s"
    )
    async with session_scope() as s:
        row = await s.get(WebhookORM, wh_c.id)
        row.active = False  # inactive webhook must be skipped

    count = await partner_webhooks.emit_webhook_event("bond.updated", {"k": "v"}, wait=True)
    assert count == 1  # only the active subscribed webhook
    assert captured == [(wh_a.id, "bond.updated", {"k": "v"})]

    count2 = await partner_webhooks.emit_webhook_event("alert.triggered", {}, wait=True)
    assert count2 == 1
    assert captured[-1][0] == wh_b.id


async def test_emit_webhook_event_unsupported_event_zero(monkeypatch):
    called = []

    async def fake_deliver(wh, event_type, payload):
        called.append(event_type)
        return True

    monkeypatch.setattr(partner_webhooks, "deliver_webhook", fake_deliver)
    assert await partner_webhooks.emit_webhook_event("payment.succeeded", {}, wait=True) == 0
    assert called == []


async def test_emit_webhook_event_delivery_failure_swallowed(monkeypatch):
    async def boom(wh, event_type, payload):
        raise RuntimeError("delivery crashed")

    monkeypatch.setattr(partner_webhooks, "deliver_webhook", boom)
    await _purge_webhooks()
    owner = await _seed_user(20108)
    pk = await _seed_partner_key(owner, "emit-2")
    await partner_webhooks.register_webhook(
        partner_key_id=pk, url="https://8.8.8.8/h", events=["bond.updated"], secret="s"
    )
    # _safe_deliver must swallow the failure; emit still reports the target count.
    assert await partner_webhooks.emit_webhook_event("bond.updated", {}, wait=True) == 1


# =========================================================================== #
# 3. api/notifications/reminders.py
# =========================================================================== #
class _FakeDateTime:
    """Replaces datetime in the reminders module to freeze "now"."""

    fixed: datetime | None = None

    @classmethod
    def now(cls, tz=None):  # noqa: ARG003
        assert cls.fixed is not None
        return cls.fixed


_FIXED_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


class _FakeAddress:
    """Mimics Starlette's request.client (an Address with a .host attribute)."""

    def __init__(self, host: str):
        self.host = host


def test_days_until_math(monkeypatch):
    monkeypatch.setattr(reminders_mod, "datetime", _FakeDateTime)
    _FakeDateTime.fixed = _FIXED_NOW

    assert reminders_mod._days_until(None) is None
    assert reminders_mod._days_until(_FIXED_NOW) == 0  # expires right now
    assert reminders_mod._days_until(_FIXED_NOW - timedelta(days=2)) == 0  # already lapsed
    assert reminders_mod._days_until(_FIXED_NOW + timedelta(days=3)) == 3  # exact 3 days
    assert reminders_mod._days_until(_FIXED_NOW + timedelta(days=3, hours=1)) == 4
    assert reminders_mod._days_until(_FIXED_NOW + timedelta(days=2, hours=23)) == 3  # rounds up
    assert reminders_mod._days_until(_FIXED_NOW + timedelta(hours=23)) == 1
    assert reminders_mod._days_until(_FIXED_NOW + timedelta(hours=1)) == 1  # min is 1
    # Naive datetime is treated as UTC.
    naive = datetime(2026, 3, 4, 12, 0, 0)  # == _FIXED_NOW + 3d
    assert reminders_mod._days_until(naive) == 3


async def test_notify_expiring_trials_email_and_telegram(monkeypatch):
    monkeypatch.setattr(reminders_mod, "datetime", _FakeDateTime)
    _FakeDateTime.fixed = _FIXED_NOW

    sent_emails: list[tuple[str, str, int]] = []
    monkeypatch.setattr(
        "api.notifications.email.send_subscription_expiring_email",
        lambda to, tier, days: sent_emails.append((to, tier, days)) or True,
    )

    class FakeBot:
        def __init__(self):
            self.messages: list[tuple[int, str]] = []

        async def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    bot = FakeBot()
    monkeypatch.setattr(reminders_mod, "_get_bot", lambda: bot)

    # u1: free trial expiring in 3 days (email + telegram available).
    u1 = await _seed_user(21001, tier="free", trial_days=3, telegram_id=71001)
    # u2: pro subscription expiring in 1 day.
    u2 = await _seed_user(21002, tier="pro", expires_days=1, telegram_id=71002)
    # u3: enterprise expiring in 3 days, no email -> telegram only.
    await _seed_user(21003, tier="enterprise", expires_days=3, telegram_id=71003, email="")
    # u4: pro expiring in 2 days -> outside the (3, 1) window.
    await _seed_user(21004, tier="pro", expires_days=2, telegram_id=71004)
    # u5: free tier with a paid-window expiry set -> not a reminder target.
    await _seed_user(21005, tier="free", expires_days=3)
    # u6: free without trial -> nothing.
    await _seed_user(21006, tier="free")

    sent = await reminders_mod.notify_expiring_trials()

    assert sent == 3  # u1, u2, u3 — one reminder per user
    assert sent_emails == [
        (f"br{u1}@t.co", "Pro (trial)", 3),
        (f"br{u2}@t.co", "Pro", 1),
    ]
    # Telegram is used for every user that has a telegram_id, regardless of
    # email availability: u1 (email+tg), u2 (email+tg), u3 (tg only).
    tg_ids = {chat_id for chat_id, _ in bot.messages}
    assert tg_ids == {71001, 71002, 71003}
    assert sent_emails == [
        (f"br{u1}@t.co", "Pro (trial)", 3),
        (f"br{u2}@t.co", "Pro", 1),
    ]
    msg_u2 = next(text for chat_id, text in bot.messages if chat_id == 71002)
    assert "истекает через <b>1 дн.</b>" in msg_u2


async def test_notify_expiring_trials_delivery_failures_not_counted(monkeypatch):
    monkeypatch.setattr(reminders_mod, "datetime", _FakeDateTime)
    _FakeDateTime.fixed = _FIXED_NOW

    def broken_email(to, tier, days):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("api.notifications.email.send_subscription_expiring_email", broken_email)

    class BrokenBot:
        async def send_message(self, chat_id, text):
            raise RuntimeError("telegram down")

    monkeypatch.setattr(reminders_mod, "_get_bot", lambda: BrokenBot())

    # u1: email fails, telegram fails -> nothing delivered.
    await _seed_user(21011, tier="pro", expires_days=1, telegram_id=71011)
    # u2: email fails, no telegram id -> nothing delivered.
    await _seed_user(21012, tier="enterprise", expires_days=1, telegram_id=None)

    sent = await reminders_mod.notify_expiring_trials()
    assert sent == 0  # a reminder is only counted when at least one channel delivered


async def test_get_bot_without_instance(monkeypatch):
    import telegram_bot._bot_instance as bot_instance

    monkeypatch.setattr(bot_instance, "_bot", None)
    assert reminders_mod._get_bot() is None

    stub = object()
    monkeypatch.setattr(bot_instance, "_bot", stub)
    assert reminders_mod._get_bot() is stub


# =========================================================================== #
# 4. api/analytics/_helpers.py
# =========================================================================== #
async def test_helpers_all_bonds_and_get_bond_or_404():
    from api.analytics import _helpers as helpers

    await _seed_bond("AUD-B1", currency="USD", ytm=10.0)
    await _seed_bond("AUD-B2", currency="BYN", ytm=8.0)

    bonds = await helpers._all_bonds()
    ids = {b.internal_id for b in bonds}
    assert {"AUD-B1", "AUD-B2"} <= ids
    b1 = next(b for b in bonds if b.internal_id == "AUD-B1")
    assert b1.currency == "USD"

    found = await helpers._get_bond_or_404("AUD-B1")
    assert found.internal_id == "AUD-B1"


async def test_helpers_get_bond_or_404_raises():
    from api.analytics import _helpers as helpers

    with pytest.raises(HTTPException) as exc:
        await helpers._get_bond_or_404("AUD-NOPE")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Bond AUD-NOPE not found"


async def test_score_for_bond_uses_stored_score():
    from api.analytics import _helpers as helpers

    await _seed_bond("AUD-SC", currency="USD", ytm=10.0)
    async with session_scope() as s:
        s.add(
            BondScoreORM(
                internal_id="AUD-SC",
                score=Decimal("77.50"),
                tier="A",
                breakdown={"yield_component": 70.0},
            )
        )
    bond = await helpers._get_bond_or_404("AUD-SC")
    score = await helpers._score_for_bond(bond)
    assert score.internal_id == "AUD-SC"
    assert score.score == 77.5
    assert score.breakdown.yield_component == 70.0


async def test_score_for_bond_fallback_computes():
    from api.analytics import _helpers as helpers

    await _seed_bond("AUD-SF", currency="USD", ytm=10.0, price=100.0, maturity=date(2032, 1, 1))
    bond = await helpers._get_bond_or_404("AUD-SF")
    score = await helpers._score_for_bond(bond)
    assert score.internal_id == "AUD-SF"
    assert isinstance(score.score, float)


# --------------------------------------------------------------------------- #
# Local helpers used above
# --------------------------------------------------------------------------- #
async def _async_none(*args, **kwargs):
    return None
