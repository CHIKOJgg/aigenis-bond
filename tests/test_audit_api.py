"""Comprehensive pytest suite for the money-critical FastAPI layer.

Coverage:
  * api/billing/service.py      — YooKassa webhooks, subscription lifecycle,
                                  payment creation, referral attribution
  * api/portfolio_api.py        — transactions CRUD, P&L dashboard, backtest
  * api/pricing/router.py       — pricing endpoint + client-IP geo resolution
  * api/services/desk.py        — RV / duration / carry / repo / stress /
                                  curve / spreads / status
  * api/reports.py              — portfolio HTML report
  * api/analytics/portfolio.py  — forecast / scenarios / positions / income /
                                  allocate / build_plan / rebalance / alerts

Run only this file:  python -m pytest tests/test_audit_api.py -q -p no:warnings --tb=short

Tests that expose genuine source bugs are prefixed with "# KNOWN-FAILING"
and are reported separately; they fail until the source is fixed.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from api.auth.service import create_access_token
from api.billing import service as billing_service
from api.main import app
from api.pricing import router as pricing_router
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import (
    AlertEventORM,
    AlertORM,
    Base,
    BillingPaymentEventORM,
    BondHistoryORM,
    BondORM,
    PartnerKeyORM,
    PartnerReferralORM,
    PnLSnapshotORM,
    StockORM,
    SubscriptionORM,
    UserORM,
)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
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


async def _seed_user(
    uid: int,
    tier: str = "pro",
    expires_days: int | None = 30,
    channel: str | None = None,
    referral_code: str | None = None,
) -> int:
    async with session_scope() as s:
        s.add(
            UserORM(
                id=uid,
                email=f"u{uid}@t.co",
                name=f"User {uid}",
                password_hash="x",
                role="user",
                subscription_tier=tier,
                subscription_expires_at=(
                    datetime.now(UTC) + timedelta(days=expires_days) if expires_days else None
                ),
                payment_channel=channel,
                is_active=True,
                is_verified=False,
                referral_code=referral_code,
            )
        )
    return uid


async def _seed_subscription(
    uid: int, *, payment_id: str | None = None, plan: str = "pro", status: str = "active"
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
            )
        )


async def _seed_bond(
    iid: str,
    *,
    name: str | None = None,
    currency: str = "USD",
    ytm: float | None = 10.0,
    price: float = 100.0,
    coupon: float | None = None,
    freq: int = 2,
    maturity: date = date(2030, 1, 1),
    issuer: str = "Treasury",
    is_government: bool = False,
    nominal: Decimal = Decimal("1000"),
) -> str:
    async with session_scope() as s:
        s.add(
            BondORM(
                internal_id=iid,
                name=name or f"Bond {iid}",
                currency=currency,
                yield_to_maturity=Decimal(str(ytm)) if ytm is not None else None,
                price=Decimal(str(price)),
                coupon_rate=Decimal(str(coupon)) if coupon is not None else None,
                coupon_frequency=freq,
                maturity_date=maturity,
                issuer=issuer,
                nominal=nominal,
                is_government=is_government,
                status="active",
            )
        )
    return iid


async def _seed_bond_history(iid: str, rows: list[tuple[str, float, float]]) -> None:
    """Seed BondHistoryORM rows as [(YYYY-MM-DD, price, yield), ...]."""
    async with session_scope() as s:
        for d, px, y in rows:
            s.add(
                BondHistoryORM(
                    internal_id=iid,
                    date=date.fromisoformat(d),
                    price=Decimal(str(px)),
                    yield_=Decimal(str(y)),
                )
            )


async def _seed_stock(iid: str, *, name: str = "Stock", currency: str = "RUB") -> None:
    async with session_scope() as s:
        s.add(
            StockORM(internal_id=iid, secid=iid, name=name, currency=currency, price=Decimal("100"))
        )


async def _count(model) -> int:
    from sqlalchemy import select

    async with session_scope() as s:
        result = await s.execute(select(model))
        return len(list(result.scalars().all()))


def _make_client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _payment(
    payment_id: str,
    *,
    status: str = "succeeded",
    amount: str = "29.00",
    currency: str = "BYN",
    user_id: int = 1,
    plan: str = "pro",
) -> dict:
    return {
        "id": payment_id,
        "status": status,
        "amount": {"value": amount, "currency": currency},
        "metadata": {"user_id": str(user_id), "plan": plan},
    }


def _json(obj: dict) -> bytes:
    return json.dumps(obj).encode()


# =========================================================================== #
# 1. Billing service — api/billing/service.py
# =========================================================================== #


# --- Metadata / webhook plumbing ------------------------------------------- #
def test_metadata_user_id_tolerant_parsing():
    assert billing_service._metadata_user_id({"user_id": 123}) == 123
    assert billing_service._metadata_user_id({"user_id": "123.0"}) == 123
    assert billing_service._metadata_user_id({"user_id": " 42 "}) == 42
    assert billing_service._metadata_user_id({"user_id": "garbage"}) == 0
    assert billing_service._metadata_user_id({}) == 0


def test_webhook_invalid_json_returns_none():
    def run():
        async def _go():
            assert await billing_service.handle_webhook(b"not json {{{") is None

        return _go

    _run(run())


def test_webhook_missing_fields_returns_none():
    def run():
        async def _go():
            assert await billing_service.handle_webhook(b'{"event": "payment.succeeded"}') is None
            assert await billing_service.handle_webhook(b'{"object": {"id": "p1"}}') is None

        return _go

    _run(run())


def test_webhook_unknown_event_returns_event_type(monkeypatch):
    def run():
        async def _go():
            body = _json({"event": "payment.something.new", "object": {"id": "p1"}})
            assert await billing_service.handle_webhook(body) == "payment.something.new"

        return _go

    _run(run())


def test_webhook_unverified_payment_returns_none(monkeypatch):
    def run():
        async def _go():
            async def fake_fetch_payment(pid):
                return None  # YooKassa API does not confirm this id

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            body = _json({"event": "payment.succeeded", "object": {"id": "forged"}})
            assert await billing_service.handle_webhook(body) is None

        return _go

    _run(run())


# --- payment.succeeded ----------------------------------------------------- #
def test_payment_succeeded_creates_subscription(monkeypatch):
    def run():
        async def _go():
            uid = await _seed_user(601, expires_days=None)

            async def fake_fetch_payment(pid):
                return _payment(pid, user_id=uid)

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            event = await billing_service.handle_webhook(
                _json({"event": "payment.succeeded", "object": _payment("pay-601", user_id=uid)})
            )
            assert event == "payment.succeeded"

            async with session_scope() as s:
                sub = (
                    (
                        await s.execute(
                            SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                        )
                    )
                    .mappings()
                    .first()
                )
                user = (
                    (await s.execute(UserORM.__table__.select().where(UserORM.id == uid)))
                    .mappings()
                    .first()
                )
            assert sub["plan"] == "pro"
            assert sub["status"] == "active"
            assert sub["yookassa_payment_id"] == "pay-601"
            assert user["subscription_tier"] == "pro"
            assert user["payment_channel"] == "yookassa"
            expected = (datetime.now(UTC) + timedelta(days=30)).replace(tzinfo=None)
            assert abs((sub["current_period_end"] - expected).total_seconds()) < 120
            assert await _count(BillingPaymentEventORM) == 1

        return _go

    _run(run())


def test_payment_succeeded_extends_existing_subscription(monkeypatch):
    def run():
        async def _go():
            uid = await _seed_user(602, expires_days=5, channel="yookassa")
            await _seed_subscription(602, payment_id=None)

            async def fake_fetch_payment(pid):
                return _payment(pid, user_id=uid)

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            await billing_service.handle_webhook(
                _json({"event": "payment.succeeded", "object": _payment("pay-602", user_id=uid)})
            )

            async with session_scope() as s:
                sub = (
                    (
                        await s.execute(
                            SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                        )
                    )
                    .mappings()
                    .first()
                )
            # Repeat purchase extends from the existing expiry (+5d), not from now.
            expected = (datetime.now(UTC) + timedelta(days=35)).replace(tzinfo=None)
            assert abs((sub["current_period_end"] - expected).total_seconds()) < 120

        return _go

    _run(run())


def test_payment_succeeded_overpay_accepted(monkeypatch):
    """Documented behavior: paying MORE than the plan price is accepted."""

    def run():
        async def _go():
            uid = await _seed_user(603)

            async def fake_fetch_payment(pid):
                return _payment(pid, amount="29.50", user_id=uid)

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            await billing_service.handle_webhook(
                _json(
                    {
                        "event": "payment.succeeded",
                        "object": _payment("pay-603", amount="29.50", user_id=uid),
                    }
                )
            )

            async with session_scope() as s:
                sub = (
                    (
                        await s.execute(
                            SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                        )
                    )
                    .mappings()
                    .first()
                )
            assert sub["status"] == "active"

        return _go

    _run(run())


def test_payment_succeeded_underpay_rejected(monkeypatch):
    def run():
        async def _go():
            uid = await _seed_user(604)

            async def fake_fetch_payment(pid):
                return _payment(pid, amount="20.00", user_id=uid)

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            await billing_service.handle_webhook(
                _json(
                    {
                        "event": "payment.succeeded",
                        "object": _payment("pay-604", amount="20.00", user_id=uid),
                    }
                )
            )

            async with session_scope() as s:
                sub = (
                    await s.execute(
                        SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                    )
                ).first()
            assert sub is None

        return _go

    _run(run())


def test_payment_succeeded_wrong_currency_rejected(monkeypatch):
    def run():
        async def _go():
            uid = await _seed_user(605)

            async def fake_fetch_payment(pid):
                return _payment(pid, currency="USD", user_id=uid)

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            await billing_service.handle_webhook(
                _json(
                    {
                        "event": "payment.succeeded",
                        "object": _payment("pay-605", currency="USD", user_id=uid),
                    }
                )
            )

            async with session_scope() as s:
                sub = (
                    await s.execute(
                        SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                    )
                ).first()
            assert sub is None

        return _go

    _run(run())


def test_payment_succeeded_redelivery_is_idempotent(monkeypatch):
    def run():
        async def _go():
            uid = await _seed_user(606, expires_days=None)

            async def fake_fetch_payment(pid):
                return _payment(pid, user_id=uid)

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            body = _json({"event": "payment.succeeded", "object": _payment("pay-606", user_id=uid)})
            await billing_service.handle_webhook(body)
            await billing_service.handle_webhook(body)  # YooKassa redelivery

            async with session_scope() as s:
                sub = (
                    (
                        await s.execute(
                            SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                        )
                    )
                    .mappings()
                    .first()
                )
            assert sub["status"] == "active"
            # One processed event, expiry NOT double-extended.
            assert await _count(BillingPaymentEventORM) == 1
            expected = (datetime.now(UTC) + timedelta(days=30)).replace(tzinfo=None)
            assert abs((sub["current_period_end"] - expected).total_seconds()) < 120

        return _go

    _run(run())


# --- payment.canceled ------------------------------------------------------ #
def test_payment_canceled_marks_subscription_canceled(monkeypatch):
    def run():
        async def _go():
            uid = await _seed_user(607, channel="yookassa")
            await _seed_subscription(607, payment_id="pay-607")

            async def fake_fetch_payment(pid):
                return _payment(pid, status="canceled", user_id=uid)

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            await billing_service.handle_webhook(
                _json(
                    {
                        "event": "payment.canceled",
                        "object": _payment("pay-607", status="canceled", user_id=uid),
                    }
                )
            )

            async with session_scope() as s:
                sub = (
                    (
                        await s.execute(
                            SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                        )
                    )
                    .mappings()
                    .first()
                )
                user = (
                    (await s.execute(UserORM.__table__.select().where(UserORM.id == uid)))
                    .mappings()
                    .first()
                )
            assert sub["status"] == "canceled"
            assert user["subscription_tier"] == "free"
            assert user["subscription_expires_at"] is None
            assert user["payment_channel"] is None

        return _go

    _run(run())


def test_payment_canceled_stale_payment_ignored(monkeypatch):
    def run():
        async def _go():
            uid = await _seed_user(608, channel="yookassa")
            await _seed_subscription(608, payment_id="pay-OLD")

            async def fake_fetch_payment(pid):
                return _payment(pid, status="canceled", user_id=uid)

            monkeypatch.setattr(billing_service, "fetch_payment", fake_fetch_payment)
            await billing_service.handle_webhook(
                _json(
                    {
                        "event": "payment.canceled",
                        "object": _payment("pay-608", status="canceled", user_id=uid),
                    }
                )
            )

            async with session_scope() as s:
                sub = (
                    (
                        await s.execute(
                            SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                        )
                    )
                    .mappings()
                    .first()
                )
            # Stale cancellation for a superseded payment must not corrupt the record.
            assert sub["status"] == "active"
            assert sub["yookassa_payment_id"] == "pay-OLD"

        return _go

    _run(run())


# --- refund.succeeded ------------------------------------------------------ #
def test_refund_succeeded_full_refund_revokes(monkeypatch):
    def run():
        async def _go():
            uid = await _seed_user(609, channel="yookassa")
            await _seed_subscription(609, payment_id="pay-609")

            async def fake_fetch_refund(rid):
                return {
                    "id": rid,
                    "status": "succeeded",
                    "payment_id": "pay-609",
                    "amount": {"value": "29.00", "currency": "BYN"},
                    "metadata": {},
                }

            monkeypatch.setattr(billing_service, "fetch_refund", fake_fetch_refund)
            await billing_service.handle_webhook(
                _json(
                    {
                        "event": "refund.succeeded",
                        "object": {"id": "ref-609", "status": "succeeded", "payment_id": "pay-609"},
                    }
                )
            )

            async with session_scope() as s:
                sub = (
                    (
                        await s.execute(
                            SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                        )
                    )
                    .mappings()
                    .first()
                )
                user = (
                    (await s.execute(UserORM.__table__.select().where(UserORM.id == uid)))
                    .mappings()
                    .first()
                )
            assert sub["status"] == "refunded"
            assert user["subscription_tier"] == "free"
            assert user["payment_channel"] is None

        return _go

    _run(run())


def test_refund_partial_ignored(monkeypatch):
    def run():
        async def _go():
            uid = await _seed_user(610, channel="yookassa")
            await _seed_subscription(610, payment_id="pay-610")

            async def fake_fetch_refund(rid):
                return {
                    "id": rid,
                    "status": "succeeded",
                    "payment_id": "pay-610",
                    "amount": {"value": "10.00", "currency": "BYN"},  # partial refund
                    "metadata": {},
                }

            monkeypatch.setattr(billing_service, "fetch_refund", fake_fetch_refund)
            await billing_service.handle_webhook(
                _json(
                    {
                        "event": "refund.succeeded",
                        "object": {"id": "ref-610", "status": "succeeded", "payment_id": "pay-610"},
                    }
                )
            )

            async with session_scope() as s:
                sub = (
                    (
                        await s.execute(
                            SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                        )
                    )
                    .mappings()
                    .first()
                )
            # Partial refunds (e.g. discounts) must not cut an active subscription.
            assert sub["status"] == "active"

        return _go

    _run(run())


def test_refund_stars_channel_not_revoked(monkeypatch):
    """A YooKassa refund must not revoke access paid for via Telegram Stars."""

    def run():
        async def _go():
            uid = await _seed_user(611, channel="stars")
            await _seed_subscription(611, payment_id="pay-611")

            async def fake_fetch_refund(rid):
                return {
                    "id": rid,
                    "status": "succeeded",
                    "payment_id": "pay-611",
                    "amount": {"value": "29.00", "currency": "BYN"},
                    "metadata": {},
                }

            monkeypatch.setattr(billing_service, "fetch_refund", fake_fetch_refund)
            await billing_service.handle_webhook(
                _json(
                    {
                        "event": "refund.succeeded",
                        "object": {"id": "ref-611", "status": "succeeded", "payment_id": "pay-611"},
                    }
                )
            )

            async with session_scope() as s:
                sub = (
                    (
                        await s.execute(
                            SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                        )
                    )
                    .mappings()
                    .first()
                )
                user = (
                    (await s.execute(UserORM.__table__.select().where(UserORM.id == uid)))
                    .mappings()
                    .first()
                )
            assert sub["status"] == "refunded"
            assert user["subscription_tier"] == "pro"
            assert user["payment_channel"] == "stars"

        return _go

    _run(run())


def test_refund_empty_id_rejected():
    """A refund object without an id must be ignored (nothing to dedupe against).

    # KNOWN-FAILING: ``_handle_refund_succeeded`` processes refunds with an
    # empty ``id``: the replay guard is skipped (``refund_id`` is falsy) and
    # the subscription is marked refunded / access revoked. The handler should
    # reject objects whose ``id`` is missing, as it does for missing payment ids.
    """

    def run():
        async def _go():
            uid = await _seed_user(612, channel="yookassa")
            await _seed_subscription(612, payment_id="pay-612")

            await billing_service._handle_refund_succeeded(
                {
                    "id": "",  # empty refund id — must be rejected
                    "status": "succeeded",
                    "payment_id": "pay-612",
                    "amount": {"value": "29.00", "currency": "BYN"},
                    "metadata": {},
                },
                {},
            )

            async with session_scope() as s:
                sub = (
                    (
                        await s.execute(
                            SubscriptionORM.__table__.select().where(SubscriptionORM.user_id == uid)
                        )
                    )
                    .mappings()
                    .first()
                )
                user = (
                    (await s.execute(UserORM.__table__.select().where(UserORM.id == uid)))
                    .mappings()
                    .first()
                )
            assert sub["status"] == "active"
            assert user["subscription_tier"] == "pro"

        return _go

    _run(run())


# --- create_payment -------------------------------------------------------- #
class _FakeResp:
    def __init__(self, status: int = 200, payload: dict | None = None):
        self.status_code = status
        self.text = "{}"
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    instances: list[_FakeAsyncClient] = []

    def __init__(self, *args, **kwargs):
        self.auth = kwargs.get("auth")
        self.calls: list[tuple[str, dict]] = []
        _FakeAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url: str, **kwargs) -> _FakeResp:
        self.calls.append((url, kwargs))
        return _FakeResp(
            payload={
                "id": "pay-created-1",
                "status": "pending",
                "confirmation": {"confirmation_url": "https://pay.example/confirm/1"},
            }
        )


def _patch_yookassa_client(monkeypatch):
    monkeypatch.setattr(billing_service, "YOOKASSA_SHOP_ID", "shop-id")
    monkeypatch.setattr(billing_service, "YOOKASSA_SECRET_KEY", "secret-key")
    _FakeAsyncClient.instances = []
    monkeypatch.setattr(billing_service.httpx, "AsyncClient", _FakeAsyncClient)
    assert billing_service.is_yookassa_configured() is True
    return _FakeAsyncClient


def test_create_payment_pro_plan_payload(monkeypatch):
    def run():
        async def _go():
            fake_cls = _patch_yookassa_client(monkeypatch)
            user = SimpleNamespace(id=601)
            result = await billing_service.create_payment(user, "pro", "https://app.example/ok")

            assert result == {
                "payment_id": "pay-created-1",
                "status": "pending",
                "confirmation_url": "https://pay.example/confirm/1",
            }
            client = fake_cls.instances[0]
            assert client.auth == ("shop-id", "secret-key")
            url, kwargs = client.calls[0]
            assert url == "https://api.yookassa.ru/v3/payments"
            payload = kwargs["json"]
            assert payload["amount"] == {"value": "29.00", "currency": "BYN"}
            assert payload["metadata"] == {
                "user_id": "601",
                "plan": "pro",
                "referral_code": "",
            }
            assert payload["confirmation"]["return_url"] == "https://app.example/ok"
            assert "Idempotence-Key" in kwargs["headers"]
            assert "Aigenis" in payload["description"]

        return _go

    _run(run())


def test_create_payment_referral_code_in_metadata(monkeypatch):
    def run():
        async def _go():
            fake_cls = _patch_yookassa_client(monkeypatch)
            user = SimpleNamespace(id=602)
            await billing_service.create_payment(
                user, "enterprise", "https://app.example/ok", referral_code="PARTNER1"
            )
            payload = fake_cls.instances[0].calls[0][1]["json"]
            assert payload["amount"] == {"value": "99.00", "currency": "BYN"}
            assert payload["metadata"]["referral_code"] == "PARTNER1"
            assert payload["metadata"]["plan"] == "enterprise"

        return _go

    _run(run())


def test_create_payment_unknown_plan_returns_none(monkeypatch):
    def run():
        async def _go():
            fake_cls = _patch_yookassa_client(monkeypatch)
            user = SimpleNamespace(id=603)
            result = await billing_service.create_payment(user, "gold", "https://app.example/ok")
            assert result is None
            assert fake_cls.instances == []

        return _go

    _run(run())


def test_create_payment_yookassa_error_returns_none(monkeypatch):
    def run():
        async def _go():
            _patch_yookassa_client(monkeypatch)

            async def failing_post(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return _FakeResp(status=500, payload={"code": "internal_error"})

            monkeypatch.setattr(_FakeAsyncClient, "post", failing_post)
            user = SimpleNamespace(id=604)
            result = await billing_service.create_payment(user, "pro", "https://app.example/ok")
            assert result is None

        return _go

    _run(run())


def test_create_payment_when_not_configured_returns_none(monkeypatch):
    """When YooKassa credentials are absent the API must refuse to create a payment.

    (Regression: ``create_payment`` used to call the YooKassa API with empty
    auth instead of returning None immediately.)
    """

    def run():
        async def _go():
            assert billing_service.is_yookassa_configured() is False  # .env is empty in tests

            class _MustNotBeUsed:
                def __init__(self, *args, **kwargs):
                    raise AssertionError("create_payment must not call YooKassa when unconfigured")

            monkeypatch.setattr(billing_service.httpx, "AsyncClient", _MustNotBeUsed)
            user = SimpleNamespace(id=605)
            result = await billing_service.create_payment(user, "pro", "https://app.example/ok")
            assert result is None

        return _go

    _run(run())


# --- referral attribution -------------------------------------------------- #
async def _attribution(code: str, referred_uid: int, referrer_uid: int) -> list[PartnerReferralORM]:
    from sqlalchemy import select

    await _seed_user(referrer_uid, referral_code=f"CODE{referrer_uid}")
    async with session_scope() as s:
        await billing_service._attribute_referral(s, code, referred_uid, "pro", 29.0, "BYN")
    async with session_scope() as s:
        result = await s.execute(select(PartnerReferralORM))
        return list(result.scalars().all())


def test_attribute_referral_partner_key():
    def run():
        async def _go():
            await _seed_user(777, referral_code="OWNER1")
            async with session_scope() as s:
                pk = PartnerKeyORM(
                    name="Partner A",
                    key_hash="h",
                    key_fp="fp",
                    referral_code="PARTNER1",
                    active=True,
                    owner_user_id=777,
                )
                s.add(pk)
                await s.flush()
                pk_id = pk.id
                await billing_service._attribute_referral(s, "PARTNER1", 700, "pro", 29.0, "BYN")
            async with session_scope() as s:
                from sqlalchemy import select

                rows = list((await s.execute(select(PartnerReferralORM))).scalars().all())
            assert len(rows) == 1
            assert rows[0].partner_key_id == pk_id
            assert rows[0].referrer_user_id == 777
            assert rows[0].referred_user_id == 700
            assert rows[0].plan == "pro"
            assert rows[0].amount == 29.0
            assert rows[0].currency == "BYN"
            assert rows[0].payout_status == "pending"

        return _go

    _run(run())


def test_attribute_referral_user_referral_code():
    def run():
        async def _go():
            await _seed_user(801, referral_code="JOE1")
            await _seed_user(802)
            async with session_scope() as s:
                await billing_service._attribute_referral(s, "JOE1", 802, "pro", 29.0, "BYN")
            async with session_scope() as s:
                from sqlalchemy import select

                rows = list((await s.execute(select(PartnerReferralORM))).scalars().all())
            assert len(rows) == 1
            assert rows[0].partner_key_id is None
            assert rows[0].referrer_user_id == 801

        return _go

    _run(run())


def test_attribute_referral_self_referral_skipped():
    def run():
        async def _go():
            await _seed_user(803, referral_code="SELF1")
            async with session_scope() as s:
                await billing_service._attribute_referral(s, "SELF1", 803, "pro", 29.0, "BYN")
            async with session_scope() as s:
                from sqlalchemy import select

                rows = list((await s.execute(select(PartnerReferralORM))).scalars().all())
            assert rows == []

        return _go

    _run(run())


def test_attribute_referral_unknown_code_skipped():
    def run():
        async def _go():
            await _seed_user(804)
            async with session_scope() as s:
                await billing_service._attribute_referral(s, "NOPE", 804, "pro", 29.0, "BYN")
            async with session_scope() as s:
                from sqlalchemy import select

                rows = list((await s.execute(select(PartnerReferralORM))).scalars().all())
            assert rows == []

        return _go

    _run(run())


# =========================================================================== #
# 2. Portfolio advanced API — api/portfolio_api.py
# =========================================================================== #
def test_transactions_crud_flow():
    def run():
        async def _go():
            await _seed_user(701)
            await _seed_bond("B-TX", currency="BYN", price=100.0)
            async with _make_client() as client:
                r = await client.post(
                    "/api/v1/transactions",
                    json={"internal_id": "B-TX", "side": "buy", "amount": 1000, "price": 98.0},
                    headers=_auth(701),
                )
                assert r.status_code == 200
                body = r.json()
                assert body["status"] == "ok"
                assert body["internal_id"] == "B-TX"
                assert body["side"] == "buy"
                assert body["amount"] == 1000.0
                assert body["price"] == 98.0
                tx_id = body["id"]

                listed = await client.get("/api/v1/transactions", headers=_auth(701))
                assert listed.status_code == 200
                assert len(listed.json()) == 1
                assert listed.json()[0]["currency"] == "BYN"

                per_bond = await client.get("/api/v1/transactions/bond/B-TX", headers=_auth(701))
                assert per_bond.status_code == 200
                agg = per_bond.json()
                assert agg["total_bought"] == 1000.0
                assert agg["total_sold"] == 0.0
                assert agg["buy_count"] == 1
                assert agg["sell_count"] == 0

                deleted = await client.delete(f"/api/v1/transactions/{tx_id}", headers=_auth(701))
                assert deleted.status_code == 200
                assert deleted.json() == {"status": "deleted", "id": tx_id}

                again = await client.delete(f"/api/v1/transactions/{tx_id}", headers=_auth(701))
                assert again.status_code == 404

        return _go

    _run(run())


def test_transactions_validation_errors():
    def run():
        async def _go():
            await _seed_user(702)
            await _seed_bond("B-TXV", price=100.0)
            async with _make_client() as client:
                r = await client.post(
                    "/api/v1/transactions",
                    json={"internal_id": "B-TXV", "side": "hold", "amount": 1000, "price": 98.0},
                    headers=_auth(702),
                )
                assert r.status_code == 422
                r = await client.post(
                    "/api/v1/transactions",
                    json={"internal_id": "B-TXV", "side": "buy", "amount": -1, "price": 98.0},
                    headers=_auth(702),
                )
                assert r.status_code == 422
                r = await client.post(
                    "/api/v1/transactions",
                    json={"internal_id": "B-TXV", "side": "buy", "amount": 1000, "price": 0},
                    headers=_auth(702),
                )
                assert r.status_code == 422
                r = await client.post(
                    "/api/v1/transactions",
                    json={"internal_id": "NOPE", "side": "buy", "amount": 1000, "price": 98.0},
                    headers=_auth(702),
                )
                assert r.status_code == 404

        return _go

    _run(run())


def test_transactions_user_isolation():
    def run():
        async def _go():
            await _seed_user(703)
            await _seed_user(704)
            await _seed_bond("B-ISO", price=100.0)
            async with _make_client() as client:
                r1 = await client.post(
                    "/api/v1/transactions",
                    json={"internal_id": "B-ISO", "side": "buy", "amount": 500, "price": 100.0},
                    headers=_auth(703),
                )
                tx1 = r1.json()["id"]
                r2 = await client.post(
                    "/api/v1/transactions",
                    json={"internal_id": "B-ISO", "side": "buy", "amount": 900, "price": 100.0},
                    headers=_auth(704),
                )
                tx2 = r2.json()["id"]

                listed = await client.get("/api/v1/transactions", headers=_auth(703))
                assert len(listed.json()) == 1
                assert listed.json()[0]["id"] == tx1

                resp = await client.delete(f"/api/v1/transactions/{tx2}", headers=_auth(703))
                assert resp.status_code == 404

        return _go

    _run(run())


def test_transactions_pagination_and_limit_validation():
    def run():
        async def _go():
            await _seed_user(705)
            await _seed_bond("B-PG", price=100.0)
            async with _make_client() as client:
                for _ in range(3):
                    await client.post(
                        "/api/v1/transactions",
                        json={"internal_id": "B-PG", "side": "buy", "amount": 100, "price": 100.0},
                        headers=_auth(705),
                    )
                page1 = await client.get(
                    "/api/v1/transactions", params={"limit": 2}, headers=_auth(705)
                )
                assert len(page1.json()) == 2
                page2 = await client.get(
                    "/api/v1/transactions", params={"limit": 2, "offset": 1}, headers=_auth(705)
                )
                assert len(page2.json()) == 2
                off = await client.get(
                    "/api/v1/transactions", params={"offset": 5}, headers=_auth(705)
                )
                assert off.json() == []
                assert (
                    await client.get(
                        "/api/v1/transactions", params={"limit": 0}, headers=_auth(705)
                    )
                ).status_code == 422
                assert (
                    await client.get(
                        "/api/v1/transactions", params={"limit": 500}, headers=_auth(705)
                    )
                ).status_code == 422

        return _go

    _run(run())


def test_pnl_spot_check_and_snapshot_persistence():
    def run():
        async def _go():
            await _seed_user(706)
            await _seed_bond("B-PNL", currency="BYN", price=100.0)
            async with _make_client() as client:
                await client.post(
                    "/api/v1/transactions",
                    json={"internal_id": "B-PNL", "side": "buy", "amount": 1000, "price": 98.0},
                    headers=_auth(706),
                )
                await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "B-PNL", "amount": 1000},
                    headers=_auth(706),
                )
                r = await client.get("/api/v1/pnl", headers=_auth(706))
                assert r.status_code == 200
                body = r.json()
                # face = 1000 * 100 / 98 = 1020.408; value at price 100 = 1020.41
                assert body["total_invested"] == pytest.approx(1000.0, abs=0.01)
                assert body["total_value"] == pytest.approx(1020.41, abs=0.01)
                assert body["total_unrealized_pnl"] == pytest.approx(20.41, abs=0.01)
                assert body["total_pnl"] == pytest.approx(20.41, abs=0.01)
                assert body["total_return_pct"] == pytest.approx(2.04, abs=0.01)
                assert len(body["per_bond"]) == 1
                assert body["per_bond"][0]["internal_id"] == "B-PNL"
                assert len(body["daily_returns"]) == 0  # single-point equity curve
                assert body["per_bond"][0]["current_value"] == pytest.approx(1020.41, abs=0.01)

                # Snapshot persisted; a second /pnl call updates, not duplicates.
                assert await _count(PnLSnapshotORM) == 1
                await client.get("/api/v1/pnl", headers=_auth(706))
                assert await _count(PnLSnapshotORM) == 1

                history = await client.get("/api/v1/pnl/history", headers=_auth(706))
                assert history.status_code == 200
                rows = history.json()
                assert len(rows) == 1
                assert rows[0]["total_value"] == pytest.approx(1020.41, abs=0.01)

                bad_days = await client.get(
                    "/api/v1/pnl/history", params={"days": 6}, headers=_auth(706)
                )
                assert bad_days.status_code == 422

        return _go

    _run(run())


def test_pnl_empty_state():
    def run():
        async def _go():
            await _seed_user(707)
            async with _make_client() as client:
                r = await client.get("/api/v1/pnl", headers=_auth(707))
                assert r.status_code == 200
                body = r.json()
                assert body["total_value"] == 0
                assert body["per_bond"] == []
                assert body["daily_returns"] == []

        return _go

    _run(run())


def test_backtest_deterministic_spot_check():
    def run():
        async def _go():
            await _seed_user(708)
            await _seed_bond(
                "B-BT", currency="USD", ytm=10.0, price=105.0, maturity=date(2040, 1, 1)
            )
            await _seed_bond_history(
                "B-BT",
                [
                    ("2026-01-01", 100.0, 10.0),
                    ("2026-02-01", 102.0, 10.0),
                    ("2026-03-01", 105.0, 10.0),
                ],
            )
            async with _make_client() as client:
                r = await client.post(
                    "/api/v1/backtest",
                    json={
                        "strategy": "Balanced",
                        "initial_capital": 10000,
                        "start_date": "2026-01-01",
                        "end_date": "2026-03-01",
                        "top_n": 5,
                    },
                    headers=_auth(708),
                )
                assert r.status_code == 200
                body = r.json()
                assert body["strategy"] == "Balanced"
                assert body["initial_capital"] == 10000.0
                assert body["final_value"] == 10500.0
                assert body["total_return_pct"] == 5.0
                assert body["annual_return_pct"] is not None
                assert [p["value"] for p in body["equity_curve"]] == [10000.0, 10200.0, 10500.0]
                # Rebalances on 01-01 and 02-01 (31 days), not on 03-01 (28 days).
                assert len(body["positions_history"]) == 2
                assert body["positions_history"][0]["holdings"] == {"B-BT": 100.0}

        return _go

    _run(run())


def test_backtest_empty_history_returns_initial_capital():
    def run():
        async def _go():
            await _seed_user(709)
            async with _make_client() as client:
                r = await client.post(
                    "/api/v1/backtest",
                    json={"strategy": "Balanced", "initial_capital": 10000},
                    headers=_auth(709),
                )
                assert r.status_code == 200
                body = r.json()
                assert body["final_value"] == 10000.0
                assert len(body["equity_curve"]) == 1

        return _go

    _run(run())


def test_backtest_validation_errors():
    def run():
        async def _go():
            await _seed_user(710)
            async with _make_client() as client:
                r = await client.post(
                    "/api/v1/backtest",
                    json={"strategy": "Momentum"},  # not in KNOWN_STRATEGIES
                    headers=_auth(710),
                )
                assert r.status_code == 422
                r = await client.post(
                    "/api/v1/backtest",
                    json={"strategy": "Balanced", "start_date": "2026-13-99"},
                    headers=_auth(710),
                )
                assert r.status_code == 422
                r = await client.post(
                    "/api/v1/backtest",
                    json={
                        "strategy": "Balanced",
                        "start_date": "2026-03-01",
                        "end_date": "2026-01-01",  # start after end
                    },
                    headers=_auth(710),
                )
                assert r.status_code == 422
                r = await client.post(
                    "/api/v1/backtest",
                    json={"strategy": "Balanced", "initial_capital": 0},
                    headers=_auth(710),
                )
                assert r.status_code == 422

        return _go

    _run(run())


# =========================================================================== #
# 3. Pricing — api/pricing/router.py
# =========================================================================== #
def _pricing_client():
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def test_pricing_default_shape(monkeypatch):
    """Private client IP (127.0.0.1) -> country US, no geo lookup, billing source."""

    def run():
        async def _go():
            calls: list[str] = []

            async def fake_geo(ip):
                calls.append(ip)
                return "DE"

            monkeypatch.setattr(pricing_router, "_geo_lookup", fake_geo)
            async with _pricing_client() as client:
                r = await client.get("/pricing/")
                assert r.status_code == 200
                body = r.json()
                assert body == {
                    "pro": 29.0,
                    "enterprise": 99.0,
                    "currency": "BYN",
                    "country": "US",
                    "source": "billing",
                }
                assert calls == []  # 127.0.0.1 is private -> no lookup

        return _go

    _run(run())


def test_pricing_geo_lookup_for_public_ip(monkeypatch):
    def run():
        async def _go():
            calls: list[str] = []

            async def fake_geo(ip):
                calls.append(ip)
                return "DE"

            monkeypatch.setattr(pricing_router, "_geo_lookup", fake_geo)
            async with _pricing_client() as client:
                r = await client.get("/pricing/", headers={"cf-connecting-ip": "198.51.100.7"})
                assert r.status_code == 200
                assert r.json()["country"] == "DE"
                assert calls == ["198.51.100.7"]

        return _go

    _run(run())


def test_pricing_cf_connecting_ip_always_trusted(monkeypatch):
    """cf-connecting-ip is honored even without TRUSTED_PROXY=1."""

    def run():
        async def _go():
            calls: list[str] = []

            async def fake_geo(ip):
                calls.append(ip)
                return "BY"

            monkeypatch.setattr(pricing_router, "_geo_lookup", fake_geo)
            async with _pricing_client() as client:
                r = await client.get(
                    "/pricing/",
                    headers={
                        "cf-connecting-ip": "198.51.100.9",
                        "x-forwarded-for": "10.0.0.5",
                    },
                )
                assert r.json()["country"] == "BY"
                assert calls == ["198.51.100.9"]

        return _go

    _run(run())


def test_pricing_xff_ignored_without_trusted_proxy(monkeypatch):
    def run():
        async def _go():
            calls: list[str] = []

            async def fake_geo(ip):
                calls.append(ip)
                return "RU"

            monkeypatch.setattr(pricing_router, "_geo_lookup", fake_geo)
            async with _pricing_client() as client:
                r = await client.get("/pricing/", headers={"x-forwarded-for": "198.51.100.8"})
                # Header spoofed; falls back to 127.0.0.1 (private) -> US, no lookup.
                assert r.json()["country"] == "US"
                assert calls == []

        return _go

    _run(run())


def test_pricing_xff_honored_with_trusted_proxy(monkeypatch):
    def run():
        async def _go():
            monkeypatch.setenv("TRUSTED_PROXY", "1")
            calls: list[str] = []

            async def fake_geo(ip):
                calls.append(ip)
                return "BY"

            monkeypatch.setattr(pricing_router, "_geo_lookup", fake_geo)
            async with _pricing_client() as client:
                r = await client.get("/pricing/", headers={"x-forwarded-for": "203.0.113.9"})
                assert r.json()["country"] == "BY"
                assert calls == ["203.0.113.9"]

        return _go

    _run(run())


def test_pricing_private_proxy_ip_skips_geo(monkeypatch):
    def run():
        async def _go():
            monkeypatch.setenv("TRUSTED_PROXY", "1")
            calls: list[str] = []

            async def fake_geo(ip):
                calls.append(ip)
                return "DE"

            monkeypatch.setattr(pricing_router, "_geo_lookup", fake_geo)
            async with _pricing_client() as client:
                r = await client.get("/pricing/", headers={"x-forwarded-for": "10.0.0.5"})
                assert r.json()["country"] == "US"
                assert calls == []

        return _go

    _run(run())


# =========================================================================== #
# 4. Desk analytics — api/services/desk.py + api/analytics/desk.py
# =========================================================================== #
def test_desk_rv_signals_spot_check():
    def run():
        async def _go():
            await _seed_user(711)
            # Three mid-bucket (1y < T <= 5y) USD bonds: ytms 12 / 4 / 8.
            await _seed_bond("B-RV1", currency="USD", ytm=12.0, maturity=date(2028, 1, 1))
            await _seed_bond("B-RV2", currency="USD", ytm=4.0, maturity=date(2029, 1, 1))
            await _seed_bond("B-RV3", currency="USD", ytm=8.0, maturity=date(2030, 1, 1))
            # Alone in the short bucket (< 1y) -> group skipped.
            await _seed_bond("B-RV4", currency="USD", ytm=6.0, maturity=date(2027, 1, 1))
            async with _make_client() as client:
                r = await client.get("/api/v1/desk/rv", headers=_auth(711))
                assert r.status_code == 200
                signals = r.json()
                assert len(signals) == 3
                assert [s["side"] for s in signals] == ["buy", "sell", "hold"]  # sorted by |z|
                by_id = {s["internal_id"]: s for s in signals}
                assert by_id["B-RV1"]["side"] == "buy"
                assert by_id["B-RV2"]["side"] == "sell"
                assert by_id["B-RV3"]["side"] == "hold"
                assert by_id["B-RV1"]["z_score"] == pytest.approx(1.225, abs=0.001)
                assert by_id["B-RV2"]["z_score"] == pytest.approx(-1.225, abs=0.001)

        return _go

    _run(run())


def test_desk_duration_report_and_404():
    def run():
        async def _go():
            await _seed_user(712)
            await _seed_bond(
                "B-DUR",
                currency="BYN",
                ytm=10.0,
                price=100.0,
                coupon=12.0,
                freq=2,
                maturity=date(2030, 1, 1),
                nominal=Decimal("1000"),
            )
            async with _make_client() as client:
                r = await client.get(
                    "/api/v1/desk/duration", params={"bond_id": "B-DUR"}, headers=_auth(712)
                )
                assert r.status_code == 200
                body = r.json()
                assert body["title"] == "duration:B-DUR"
                assert body["macaulay_duration"] > 0
                assert body["modified_duration"] > 0
                assert body["convexity"] > 0
                assert body["dv01"] > 0
                assert isinstance(body["key_rate_durations"], dict)
                assert len(body["key_rate_durations"]) > 0

                rp = await client.get("/api/v1/desk/duration", headers=_auth(712))
                assert rp.status_code == 200
                assert rp.json()["title"] == "duration:portfolio"

                r404 = await client.get(
                    "/api/v1/desk/duration", params={"bond_id": "NOPE"}, headers=_auth(712)
                )
                assert r404.status_code == 404

        return _go

    _run(run())


def test_desk_carry_and_funding_validation():
    def run():
        async def _go():
            await _seed_user(713)
            await _seed_bond("B-CRY", currency="USD", ytm=10.0, price=100.0, coupon=12.0, freq=2)
            async with _make_client() as client:
                r = await client.get("/api/v1/desk/carry", headers=_auth(713))
                assert r.status_code == 200
                trades = r.json()
                assert len(trades) == 1
                assert trades[0]["internal_id"] == "B-CRY"
                assert isinstance(trades[0]["expected_pnl_pct"], float)
                assert isinstance(trades[0]["coupon_pct"], float)

                bad = await client.get(
                    "/api/v1/desk/carry", params={"funding": -1}, headers=_auth(713)
                )
                assert bad.status_code == 422

        return _go

    _run(run())


def test_desk_repo_treasury_spot_check():
    def run():
        async def _go():
            await _seed_user(714)
            await _seed_bond(
                "B-REPO",
                currency="BYN",
                ytm=10.0,
                price=100.0,
                coupon=8.0,
                issuer="Treasury of the Republic of Belarus",
                nominal=Decimal("1000"),
            )
            await _seed_bond(
                "B-BANK",
                currency="BYN",
                ytm=10.0,
                price=100.0,
                issuer="Belarusbank",
                nominal=Decimal("1000"),
            )
            async with _make_client() as client:
                r = await client.post(
                    "/api/v1/desk/repo",
                    json={
                        "bond_id": "B-REPO",
                        "notional": 1000,
                        "tenor_days": 30,
                        "repo_rate_pct": 5.0,
                    },
                    headers=_auth(714),
                )
                assert r.status_code == 200
                deal = r.json()
                assert deal["internal_id"] == "B-REPO"
                assert deal["haircut_pct"] == 1.0  # government -> 1%
                assert deal["collateral_value"] == 1000.0
                assert deal["cash_lent"] == 990.0  # 1000 * (1 - 1%)
                assert deal["accrued_interest"] == pytest.approx(4.07, abs=0.005)  # 990*5%*30/365
                assert deal["tenor_days"] == 30
                assert deal["repo_rate_pct"] == 5.0

                bank = await client.post(
                    "/api/v1/desk/repo",
                    json={
                        "bond_id": "B-BANK",
                        "notional": 1000,
                        "tenor_days": 30,
                        "repo_rate_pct": 5.0,
                    },
                    headers=_auth(714),
                )
                assert bank.json()["haircut_pct"] == 3.0  # bank -> 3%
                assert bank.json()["cash_lent"] == 970.0

                r404 = await client.post(
                    "/api/v1/desk/repo",
                    json={"bond_id": "NOPE", "notional": 1000},
                    headers=_auth(714),
                )
                assert r404.status_code == 404

        return _go

    _run(run())


def test_desk_stress_presets_and_fx_shock_spot_check():
    def run():
        async def _go():
            await _seed_user(715)
            await _seed_bond(
                "B-STR",
                currency="BYN",
                ytm=10.0,
                price=100.0,
                coupon=8.0,
                freq=2,
                maturity=date(2030, 1, 1),
                nominal=Decimal("1000"),
            )
            async with _make_client() as client:
                r = await client.get("/api/v1/desk/stress", headers=_auth(715))
                assert r.status_code == 200
                scenarios = r.json()
                assert len(scenarios) == 8  # PRESET_SCENARIOS
                from desk.stress import PRESET_SCENARIOS

                assert {s["scenario"] for s in scenarios} == set(PRESET_SCENARIOS)
                for s in scenarios:
                    assert s["kind"] in {
                        "parallel",
                        "steepener",
                        "flattener",
                        "inversion",
                        "credit_shock",
                        "fx_shock",
                    }

                # FX shock -20%: the local (BYN) currency is the base for a
                # BCSE portfolio, so a BYN-denominated bond is unaffected (the
                # shock only reprices foreign-currency bonds vs USD).
                fx = next(s for s in scenarios if s["scenario"] == "fx_shock_-20%")
                assert fx["pnl"] == 0.0
                assert fx["pnl_pct"] == 0.0

                # Invariant: pnl_pct == pnl / 1000 * 100 for this 1000 portfolio.
                for s in scenarios:
                    assert abs(s["pnl_pct"] * 10.0 - s["pnl"]) <= 0.011

        return _go

    _run(run())


def test_desk_curve_slope_spot_check():
    def run():
        async def _go():
            await _seed_user(716)
            await _seed_bond("B-CV1", currency="USD", ytm=5.0, maturity=date(2027, 1, 1))
            await _seed_bond("B-CV2", currency="USD", ytm=6.0, maturity=date(2030, 1, 1))
            await _seed_bond("B-CV3", currency="USD", ytm=7.0, maturity=date(2033, 1, 1))
            await _seed_bond("B-CV4", currency="USD", ytm=9.0, maturity=date(2036, 1, 1))
            async with _make_client() as client:
                r = await client.get("/api/v1/desk/curve", headers=_auth(716))
                assert r.status_code == 200
                curves = r.json()
                assert len(curves) == 1
                curve = curves[0]
                assert curve["currency"] == "USD"
                assert len(curve["points"]) == 4  # 6M / 3Y / 7Y / 10Y buckets
                rates = [p["rate_pct"] for p in curve["points"]]
                assert all(rr > 0 for rr in rates)
                assert curve["slope"] == round(max(rates) - min(rates), 4) == 4.0
                assert isinstance(curve["beta0"], float)
                assert isinstance(curve["beta1"], float)
                assert isinstance(curve["beta2"], float)

        return _go

    _run(run())


def test_desk_spreads_reports():
    def run():
        async def _go():
            await _seed_user(717)
            for _i, (iid, ytm, mat) in enumerate(
                [
                    ("B-SP1", 5.0, date(2027, 1, 1)),
                    ("B-SP2", 6.0, date(2030, 1, 1)),
                    ("B-SP3", 7.0, date(2033, 1, 1)),
                    ("B-SP4", 9.0, date(2036, 1, 1)),
                ]
            ):
                await _seed_bond(
                    iid, currency="USD", ytm=ytm, price=100.0, coupon=ytm, maturity=mat
                )
            async with _make_client() as client:
                r = await client.get("/api/v1/desk/spreads", headers=_auth(717))
                assert r.status_code == 200
                reports = r.json()
                assert len(reports) == 4
                for rep in reports:
                    assert rep["internal_id"].startswith("B-SP")
                    assert rep["g_spread_pct"] is not None
                    assert rep["model_price"] is not None
                    assert rep["market_price"] == 100.0
                    assert rep["side"] in {"rich", "cheap", "fair"}

        return _go

    _run(run())


def test_desk_status_ok():
    def run():
        async def _go():
            await _seed_user(718)
            async with _make_client() as client:
                r = await client.get("/api/v1/desk/status", headers=_auth(718))
                assert r.status_code == 200
                body = r.json()
                assert set(body) == {"rv", "stress", "spreads"}
                assert isinstance(body["rv"], list)
                assert isinstance(body["stress"], list)
                assert isinstance(body["spreads"], list)

        return _go

    _run(run())


def test_desk_free_tier_402():
    def run():
        async def _go():
            await _seed_user(719, tier="free", expires_days=None)
            async with _make_client() as client:
                r = await client.get("/api/v1/desk/rv", headers=_auth(719))
                assert r.status_code == 402
                r = await client.get("/api/v1/desk/status", headers=_auth(719))
                assert r.status_code == 402

        return _go

    _run(run())


# =========================================================================== #
# 5. Reports — api/reports.py
# =========================================================================== #
def test_reports_portfolio_html_contains_pnl():
    def run():
        async def _go():
            await _seed_user(720)
            await _seed_bond("B-REP", currency="BYN", price=100.0)
            async with _make_client() as client:
                await client.post(
                    "/api/v1/transactions",
                    json={"internal_id": "B-REP", "side": "buy", "amount": 1000, "price": 98.0},
                    headers=_auth(720),
                )
                await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "B-REP", "amount": 1000},
                    headers=_auth(720),
                )
                r = await client.get("/api/v1/reports/portfolio", headers=_auth(720))
                assert r.status_code == 200
                assert r.headers["content-type"].startswith("text/html")
                text = r.text
                assert "B-REP" in text
                assert "+20.41" in text  # {total_pnl:+,.2f} == +20.41
                assert "+2.04%" in text  # {total_return_pct:+.2f}%

        return _go

    _run(run())


def test_reports_empty_portfolio_still_html():
    def run():
        async def _go():
            await _seed_user(721)
            async with _make_client() as client:
                r = await client.get("/api/v1/reports/portfolio", headers=_auth(721))
                assert r.status_code == 200
                assert r.headers["content-type"].startswith("text/html")
                assert "0.00" in r.text

        return _go

    _run(run())


# =========================================================================== #
# 6. Analytics portfolio — api/analytics/portfolio.py
# =========================================================================== #
def _annuity_value(initial: float, monthly: float, annual_pct: float, months: int) -> float:
    rate = (1.0 + annual_pct / 100.0) ** (1.0 / 12.0) - 1.0
    value = initial
    for _ in range(months):
        value = value * (1.0 + rate) + monthly
    return value


def test_forecast_three_horizons_spot_check():
    def run():
        async def _go():
            await _seed_user(722)
            async with _make_client() as client:
                r = await client.get("/api/v1/forecast", headers=_auth(722))
                assert r.status_code == 200
                forecasts = r.json()
                assert [f["horizon_years"] for f in forecasts] == [1, 3, 5]
                for f in forecasts:
                    assert f["method"] == "monte_carlo"
                    assert set(f["mc_percentiles"]) == {"p5", "p25", "p50", "p75", "p95"}
                    assert f["cvar_95"] < f["mc_percentiles"]["p50"]
                    assert (
                        f["pessimistic_capital"] < f["expected_capital"] < f["optimistic_capital"]
                    )
                    # Deterministic annuity spot-check (7.0% p.a., +500/month).
                    expected = _annuity_value(10000.0, 500.0, 7.0, f["horizon_years"] * 12)
                    assert f["expected_capital"] == pytest.approx(expected, abs=0.01)

        return _go

    _run(run())


def test_scenarios_spot_check():
    def run():
        async def _go():
            await _seed_user(723)
            async with _make_client() as client:
                r = await client.get("/api/v1/scenarios", headers=_auth(723))
                assert r.status_code == 200
                scenarios = r.json()
                assert [s["scenario"] for s in scenarios] == [
                    "Bull USD",
                    "Neutral",
                    "Bull BYN",
                    "Stress",
                ]
                bull = next(s for s in scenarios if s["scenario"] == "Bull USD")
                assert bull["usd_byn_end"] == pytest.approx(3.795, abs=1e-9)  # 3.30 * 1.15
                assert bull["fx_change_pct"] == 15.0
                # Default shares: usd .5, byn .3, metals .2, eur 0 -> 7.5-4.5+0.9 = 3.9%
                assert bull["portfolio_value_change_pct"] == 3.9
                neutral = next(s for s in scenarios if s["scenario"] == "Neutral")
                assert neutral["usd_byn_end"] == 3.3
                assert neutral["fx_change_pct"] == 0.0
                stress = next(s for s in scenarios if s["scenario"] == "Stress")
                assert stress["usd_byn_end"] == pytest.approx(2.31, abs=1e-9)
                assert stress["fx_change_pct"] == -30.0

        return _go

    _run(run())


def test_positions_crud_and_validation():
    def run():
        async def _go():
            await _seed_user(724)
            await _seed_bond("B-POS", currency="BYN", price=100.0)
            async with _make_client() as client:
                r = await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "B-POS", "amount": 1000},
                    headers=_auth(724),
                )
                assert r.status_code == 200
                assert r.json() == {"status": "ok", "internal_id": "B-POS", "amount": 1000.0}

                listed = await client.get("/api/v1/positions", headers=_auth(724))
                assert listed.status_code == 200
                body = listed.json()
                assert body["total_invested"] == 1000.0
                assert body["positions"][0]["internal_id"] == "B-POS"

                zero = await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "B-POS", "amount": 0},
                    headers=_auth(724),
                )
                assert zero.status_code == 400
                neg = await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "B-POS", "amount": -5},
                    headers=_auth(724),
                )
                assert neg.status_code == 400
                nf = await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "NOPE", "amount": 100},
                    headers=_auth(724),
                )
                assert nf.status_code == 404

                deleted = await client.delete("/api/v1/positions/B-POS", headers=_auth(724))
                assert deleted.status_code == 200
                assert (await client.get("/api/v1/positions", headers=_auth(724))).json()[
                    "positions"
                ] == []

        return _go

    _run(run())


def test_portfolio_income_spot_check():
    def run():
        async def _go():
            await _seed_user(725)
            await _seed_bond(
                "B-INC",
                currency="BYN",
                ytm=10.0,
                price=100.0,
                coupon=8.0,
                freq=2,
                maturity=date(2030, 1, 1),
                nominal=Decimal("1000"),
            )
            async with _make_client() as client:
                await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "B-INC", "amount": 1000},
                    headers=_auth(725),
                )
                r = await client.get("/api/v1/portfolio/income", headers=_auth(725))
                assert r.status_code == 200
                body = r.json()
                assert body["mode"] == "portfolio"
                assert body["total_invested"] == 1000.0
                assert body["annual_income"] == 80.0  # 8% coupon on 1000 face
                assert body["yield_on_cost"] == 8.0
                assert body["next_payment"] == {
                    "date": "2027-01-01",
                    "amount": 40.0,
                    "kind": "coupon",
                    "internal_id": "B-INC",
                }
                assert body["monthly_calendar"][0] == {"month": "2027-01", "amount": 40.0}
                assert body["per_bond"][0]["annual_income"] == 80.0

        return _go

    _run(run())


def test_portfolio_income_empty_mode():
    def run():
        async def _go():
            await _seed_user(726)
            async with _make_client() as client:
                r = await client.get("/api/v1/portfolio/income", headers=_auth(726))
                assert r.status_code == 200
                body = r.json()
                assert body["mode"] == "empty"
                assert body["annual_income"] == 0.0
                assert body["next_payment"] is None

        return _go

    _run(run())


def test_portfolio_recommendation_and_holdings_modes():
    def run():
        async def _go():
            await _seed_user(727)
            await _seed_bond("B-PF", currency="BYN", ytm=10.0, price=100.0, coupon=8.0)
            async with _make_client() as client:
                # No positions -> recommendation mode with a forecast.
                rec = await client.get("/api/v1/portfolio", headers=_auth(727))
                assert rec.status_code == 200
                assert rec.json()["mode"] == "recommendation"
                assert len(rec.json()["forecast"]) == 3

                await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "B-PF", "amount": 1000},
                    headers=_auth(727),
                )
                held = await client.get("/api/v1/portfolio", headers=_auth(727))
                assert held.status_code == 200
                body = held.json()
                assert body["mode"] == "portfolio"
                assert body["positions_count"] == 1
                assert body["total_invested"] == 1000.0
                assert body["holdings"][0]["internal_id"] == "B-PF"
                assert body["holdings"][0]["weight"] == 1.0

        return _go

    _run(run())


def test_allocate_basket_and_validation():
    def run():
        async def _go():
            await _seed_user(728)
            await _seed_bond("B-AL", currency="BYN", ytm=10.0, price=100.0, coupon=8.0)
            async with _make_client() as client:
                r = await client.post(
                    "/api/v1/allocate",
                    json={"amount": 10000, "horizon_years": 3, "risk": "Balanced", "top_n": 5},
                    headers=_auth(728),
                )
                assert r.status_code == 200
                body = r.json()
                assert body["strategy"] == "Balanced"
                assert body["total_allocated"] == 10000.0
                assert len(body["basket"]) == 1
                assert body["basket"][0]["internal_id"] == "B-AL"
                assert body["basket"][0]["amount"] == 10000.0
                assert body["basket"][0]["weight"] == 1.0
                assert sum(b["amount"] for b in body["basket"]) == body["total_allocated"]
                assert "projection" in body
                assert body["projection"]["horizon_years"] == 3

                unknown = await client.post(
                    "/api/v1/allocate",
                    json={"amount": 10000, "risk": "Yolo", "top_n": 5},
                    headers=_auth(728),
                )
                assert unknown.status_code == 400
                zero = await client.post(
                    "/api/v1/allocate",
                    json={"amount": 0, "risk": "Balanced", "top_n": 5},
                    headers=_auth(728),
                )
                assert zero.status_code == 422
                bad_top = await client.post(
                    "/api/v1/allocate",
                    json={"amount": 10000, "risk": "Balanced", "top_n": 0},
                    headers=_auth(728),
                )
                assert bad_top.status_code == 422

        return _go

    _run(run())


def test_build_plan_modes():
    def run():
        async def _go():
            await _seed_user(729)
            await _seed_bond("B-PL", currency="BYN", ytm=10.0, price=100.0, coupon=8.0)
            async with _make_client() as client:
                empty = await client.post(
                    "/api/v1/build_plan", json={"positions": []}, headers=_auth(729)
                )
                assert empty.status_code == 200
                assert empty.json()["mode"] == "empty"

                ok_plan = await client.post(
                    "/api/v1/build_plan",
                    json={"positions": [{"internal_id": "B-PL", "amount": 5000}]},
                    headers=_auth(729),
                )
                assert ok_plan.status_code == 200
                # Single bond -> no drift -> no actions.
                assert ok_plan.json()["mode"] == "ok"
                assert ok_plan.json()["actions"] == []

        return _go

    _run(run())


def test_rebalance_below_threshold():
    def run():
        async def _go():
            await _seed_user(730)
            await _seed_bond("B-RB", currency="BYN", ytm=10.0, price=100.0, coupon=8.0)
            async with _make_client() as client:
                await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "B-RB", "amount": 10000},
                    headers=_auth(730),
                )
                r = await client.post("/api/v1/rebalance", headers=_auth(730))
                assert r.status_code == 200
                body = r.json()
                assert body["rebalanced"] is False
                assert "drift" in body["reason"]

        return _go

    _run(run())


def test_rebalance_above_threshold():
    def run():
        async def _go():
            await _seed_user(731)
            # B1 (high-yield USD) dominates B2 (low-yield BYN) in scoring.
            await _seed_bond(
                "B-RB1",
                currency="USD",
                ytm=20.0,
                price=100.0,
                coupon=15.0,
                maturity=date(2030, 1, 1),
            )
            await _seed_bond(
                "B-RB2", currency="BYN", ytm=4.0, price=100.0, coupon=1.0, maturity=date(2028, 1, 1)
            )
            async with _make_client() as client:
                await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "B-RB1", "amount": 5000},
                    headers=_auth(731),
                )
                await client.post(
                    "/api/v1/positions",
                    json={"internal_id": "B-RB2", "amount": 100},
                    headers=_auth(731),
                )
                r = await client.post("/api/v1/rebalance", headers=_auth(731))
                assert r.status_code == 200
                body = r.json()
                # 98% in B-RB1 vs ~63% target -> drift well above the 5% threshold.
                assert body["rebalanced"] is True
                assert body["max_drift_observed"] >= 0.05
                assert len(body["actions"]) >= 1
                for action in body["actions"]:
                    assert action["internal_id"] in {"B-RB1", "B-RB2"}
                    assert action["side"] in {"buy", "sell"}
                    assert action["amount"] > 0

        return _go

    _run(run())


def test_alert_rules_crud_and_metric_validation():
    def run():
        async def _go():
            await _seed_user(732)
            await _seed_user(733)
            await _seed_bond("B-ALR", currency="BYN", ytm=10.0, price=100.0, coupon=8.0)
            await _seed_stock("SBER")
            async with _make_client() as client:
                bond_rule = await client.post(
                    "/api/v1/alerts/rules",
                    json={
                        "internal_id": "B-ALR",
                        "metric": "ytm",
                        "direction": "above",
                        "threshold": 10.0,
                    },
                    headers=_auth(732),
                )
                assert bond_rule.status_code == 200
                rule = bond_rule.json()
                assert rule["internal_id"] == "B-ALR"
                assert rule["metric"] == "ytm"
                assert rule["active"] is True
                rule_id = rule["id"]

                # Bond rules may not use stock-only metrics.
                bad_metric = await client.post(
                    "/api/v1/alerts/rules",
                    json={
                        "internal_id": "B-ALR",
                        "metric": "pbr",
                        "direction": "above",
                        "threshold": 1.0,
                    },
                    headers=_auth(732),
                )
                assert bad_metric.status_code == 400

                stock_rule = await client.post(
                    "/api/v1/alerts/rules",
                    json={
                        "internal_id": "SBER",
                        "metric": "pbr",
                        "direction": "below",
                        "threshold": 1.0,
                    },
                    headers=_auth(732),
                )
                assert stock_rule.status_code == 200

                nf = await client.post(
                    "/api/v1/alerts/rules",
                    json={
                        "internal_id": "NOPE",
                        "metric": "price",
                        "direction": "above",
                        "threshold": 1.0,
                    },
                    headers=_auth(732),
                )
                assert nf.status_code == 404

                listed = await client.get("/api/v1/alerts/rules", headers=_auth(732))
                assert len(listed.json()) == 2

                deleted = await client.delete(f"/api/v1/alerts/rules/{rule_id}", headers=_auth(732))
                assert deleted.status_code == 200
                again = await client.delete(f"/api/v1/alerts/rules/{rule_id}", headers=_auth(732))
                assert again.status_code == 404

                # User isolation: user 733's rules are invisible to user 732's delete.
                other_rule = await client.post(
                    "/api/v1/alerts/rules",
                    json={
                        "internal_id": "B-ALR",
                        "metric": "price",
                        "direction": "below",
                        "threshold": 90.0,
                    },
                    headers=_auth(733),
                )
                other_id = other_rule.json()["id"]
                cross = await client.delete(f"/api/v1/alerts/rules/{other_id}", headers=_auth(732))
                assert cross.status_code == 404

        return _go

    _run(run())


def test_alert_feed_shows_triggered_events():
    def run():
        async def _go():
            uid = await _seed_user(734)
            async with session_scope() as s:
                s.add(
                    AlertEventORM(
                        user_id=uid,
                        internal_id="B-ALR",
                        metric="price",
                        message="B-ALR dropped below 95",
                        value=Decimal("94.50"),
                        delivered=False,
                    )
                )
            async with _make_client() as client:
                r = await client.get("/api/v1/alerts/feed", headers=_auth(uid))
                assert r.status_code == 200
                feed = r.json()
                assert len(feed) == 1
                assert feed[0]["internal_id"] == "B-ALR"
                assert feed[0]["metric"] == "price"
                assert feed[0]["value"] == 94.5
                assert feed[0]["delivered"] is False

        return _go

    _run(run())


def test_system_alerts_feed():
    def run():
        async def _go():
            uid = await _seed_user(735)
            async with session_scope() as s:
                s.add(
                    AlertORM(
                        kind="data_quality",
                        title="New bond listed",
                        message="B1 was added to the catalog",
                    )
                )
            async with _make_client() as client:
                r = await client.get("/api/v1/alerts", headers=_auth(uid))
                assert r.status_code == 200
                alerts = r.json()
                assert len(alerts) == 1
                assert alerts[0] == {
                    "title": "New bond listed",
                    "message": "B1 was added to the catalog",
                }

                bad_limit = await client.get(
                    "/api/v1/alerts", params={"limit": 0}, headers=_auth(uid)
                )
                assert bad_limit.status_code == 422

        return _go

    _run(run())
