"""Security-focused tests for the YooKassa billing webhook.

YooKassa does not sign webhooks, so the endpoint must (1) restrict callers to
YooKassa IP ranges and (2) re-verify every event against the YooKassa API,
acting only on the server-confirmed object — never the raw request body.

These tests assert that a forged body cannot activate/refund a subscription,
that the amount is checked against the plan price, and that processing is
idempotent. The YooKassa API calls are stubbed so no network is used.
"""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from api.billing import service as billing_service
from api.main import app
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, UserORM

client = TestClient(app)

# A real YooKassa source IP (from the published ranges) for allowed requests.
_YK_IP = "185.71.76.1"
_BAD_IP = "203.0.113.7"


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


async def _make_user(uid: int = 501) -> int:
    async with session_scope() as s:
        u = UserORM(
            id=uid,
            email=f"u{uid}@t.co",
            name="T",
            role="user",
            subscription_tier="free",
            is_active=True,
            is_verified=False,
        )
        s.add(u)
    return uid


async def _tier_of(uid: int) -> str:
    from telegram_bot.subscriptions import effective_tier

    async with session_scope() as s:
        row = (
            await s.execute(
                UserORM.__table__.select().where(UserORM.id == uid)
            )
        ).mappings().first()
    return effective_tier(
        row["subscription_tier"], row["subscription_expires_at"], row.get("trial_end")
    )


def _pay_body(payment_id: str, plan: str, uid: int, status: str = "succeeded") -> dict:
    return {
        "event": f"payment.{status}" if status != "succeeded" else "payment.succeeded",
        "object": {
            "id": payment_id,
            "status": status,
            "amount": {"value": "29.00", "currency": "BYN"},
            "metadata": {"user_id": str(uid), "plan": plan},
        },
    }


# --- IP allowlist -----------------------------------------------------------
def test_webhook_rejects_non_yookassa_ip(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    monkeypatch.delenv("YOOKASSA_WEBHOOK_IPS", raising=False)
    resp = client.post(
        "/billing/webhook",
        json=_pay_body("pay-1", "pro", 1),
        headers={"X-Forwarded-For": _BAD_IP},
    )
    assert resp.status_code == 403


def test_webhook_accepts_yookassa_ip_but_verifies(monkeypatch):
    """From an allowed IP a forged body is still inert if the API says so."""
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    monkeypatch.delenv("YOOKASSA_WEBHOOK_IPS", raising=False)

    async def fake_fetch_payment(pid):
        return None  # API does not confirm this (forged) payment

    monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
    resp = client.post(
        "/billing/webhook",
        json=_pay_body("forged", "enterprise", 1),
        headers={"X-Forwarded-For": _YK_IP},
    )
    # Event type unknown/unverified -> handler returns None -> 400.
    assert resp.status_code == 400


# --- Verification against the API -------------------------------------------
def test_forged_body_cannot_grant_when_api_disagrees(monkeypatch):
    """Body claims succeeded+enterprise; API returns a different (pending) state."""

    def scenario():
        async def run():
            uid = await _make_user(510)

            async def fake_fetch_payment(pid):
                return {"id": pid, "status": "pending", "metadata": {}}

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            event = await billing_service.handle_webhook(
                _json(_pay_body("p-510", "enterprise", uid))
            )
            assert event is None
            assert await _tier_of(uid) == "free"

        return run

    _run(scenario())


def test_verified_payment_activates_pro(monkeypatch):
    def scenario():
        async def run():
            uid = await _make_user(511)

            async def fake_fetch_payment(pid):
                return {
                    "id": pid,
                    "status": "succeeded",
                    "amount": {"value": "29.00", "currency": "BYN"},
                    "metadata": {"user_id": str(uid), "plan": "pro"},
                }

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            event = await billing_service.handle_webhook(
                _json(_pay_body("p-511", "pro", uid))
            )
            assert event == "payment.succeeded"
            assert await _tier_of(uid) == "pro"

        return run

    _run(scenario())


def test_amount_mismatch_does_not_grant_enterprise(monkeypatch):
    """Attacker pays the Pro price but metadata claims Enterprise."""

    def scenario():
        async def run():
            uid = await _make_user(512)

            async def fake_fetch_payment(pid):
                return {
                    "id": pid,
                    "status": "succeeded",
                    # Enterprise costs more than this; underpaid.
                    "amount": {"value": "29.00", "currency": "BYN"},
                    "metadata": {"user_id": str(uid), "plan": "enterprise"},
                }

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            await billing_service.handle_webhook(_json(_pay_body("p-512", "enterprise", uid)))
            assert await _tier_of(uid) == "free"

        return run

    _run(scenario())


def test_unknown_plan_is_ignored(monkeypatch):
    def scenario():
        async def run():
            uid = await _make_user(513)

            async def fake_fetch_payment(pid):
                return {
                    "id": pid,
                    "status": "succeeded",
                    "amount": {"value": "999.00", "currency": "BYN"},
                    "metadata": {"user_id": str(uid), "plan": "ultra"},
                }

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            await billing_service.handle_webhook(_json(_pay_body("p-513", "ultra", uid)))
            assert await _tier_of(uid) == "free"

        return run

    _run(scenario())


def test_idempotent_succeeded_processing(monkeypatch):
    def scenario():
        async def run():
            uid = await _make_user(514)
            calls = {"n": 0}

            async def fake_fetch_payment(pid):
                calls["n"] += 1
                return {
                    "id": pid,
                    "status": "succeeded",
                    "amount": {"value": "29.00", "currency": "BYN"},
                    "metadata": {"user_id": str(uid), "plan": "pro"},
                }

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            body = _json(_pay_body("p-514", "pro", uid))
            await billing_service.handle_webhook(body)
            await billing_service.handle_webhook(body)  # redelivery
            assert await _tier_of(uid) == "pro"
            # Still Pro, not double-extended into an inconsistent state.
            async with session_scope() as s:
                from api.billing.service import get_subscription

                sub = await get_subscription(s, uid)
                assert sub is not None
                assert sub.status == "active"

        return run

    _run(scenario())


def test_refund_revokes_after_verification(monkeypatch):
    def scenario():
        async def run():
            uid = await _make_user(515)

            async def fake_fetch_payment(pid):
                return {
                    "id": pid,
                    "status": "succeeded",
                    "amount": {"value": "29.00", "currency": "BYN"},
                    "metadata": {"user_id": str(uid), "plan": "pro"},
                }

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            await billing_service.handle_webhook(_json(_pay_body("p-515", "pro", uid)))
            assert await _tier_of(uid) == "pro"

            async def fake_fetch_refund(rid):
                return {
                    "id": rid,
                    "status": "succeeded",
                    "payment_id": "p-515",
                    "metadata": {},
                }

            monkeypatch.setattr(billing_service, "fetch_refund", fake_fetch_refund)
            refund_body = _json(
                {
                    "event": "refund.succeeded",
                    "object": {"id": "r-515", "status": "succeeded", "payment_id": "p-515"},
                }
            )
            await billing_service.handle_webhook(refund_body)
            assert await _tier_of(uid) == "free"

        return run

    _run(scenario())


def _json(obj) -> bytes:
    import json

    return json.dumps(obj).encode()
