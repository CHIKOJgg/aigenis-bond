"""YooKassa payment processing for subscriptions.

API docs: https://yookassa.ru/developers/api
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.logging import get_logger
from scraper.orm import (
    BillingPaymentEventORM,
    PartnerKeyORM,
    PartnerReferralORM,
    SubscriptionORM,
    UserORM,
)

# Per-payment lock to prevent TOCTOU race on concurrent webhook deliveries.
_webhook_locks: dict[str, asyncio.Lock] = {}
_WEBHOOK_LOCK_MAX_KEYS = 10_000  # bound memory: evict locks for stale payments

logger = get_logger("api.billing")

# YooKassa credentials
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
YOOKASSA_BASE_URL = "https://api.yookassa.ru/v3"

# Plan prices in BYN / RUB
# Pro: 29 BYN (~900 RUB), Enterprise: 99 BYN (~3000 RUB)
# Configurable via env
PRO_PRICE = os.getenv("YOOKASSA_PRO_PRICE", "29.00")
ENTERPRISE_PRICE = os.getenv("YOOKASSA_ENTERPRISE_PRICE", "99.00")
CURRENCY = os.getenv("YOOKASSA_CURRENCY", "BYN")

PLANS: dict[str, dict] = {
    "pro": {"price": PRO_PRICE, "name": "Pro", "duration_days": 30},
    "enterprise": {"price": ENTERPRISE_PRICE, "name": "Enterprise", "duration_days": 30},
}


def is_yookassa_configured() -> bool:
    return bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY)


def _metadata_user_id(metadata: dict) -> int:
    """Parse ``user_id`` from webhook metadata, tolerating dirty input.

    Webhook metadata arrives from third parties: the value can be an int,
    a string with surrounding whitespace, a float-formatted string
    (``"123.0"``), or missing entirely — none of which may 500 the handler.
    """
    raw = metadata.get("user_id", 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        try:
            return int(float(str(raw).strip()))
        except (TypeError, ValueError, ArithmeticError):
            return 0


def _auth() -> tuple[str, str]:
    return YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY


async def fetch_payment(payment_id: str) -> dict | None:
    """Fetch the authoritative payment object from YooKassa by id.

    YooKassa does NOT sign webhooks with an HMAC secret. The documented way to
    trust a notification is to (a) restrict the caller to YooKassa IPs and
    (b) re-fetch the object from the API and act only on that server-confirmed
    state — never on the raw webhook body, which an attacker could forge.
    """
    if not is_yookassa_configured() or not payment_id:
        return None
    try:
        async with httpx.AsyncClient(auth=_auth()) as client:
            resp = await client.get(
                f"{YOOKASSA_BASE_URL}/payments/{payment_id}",
                timeout=30,
            )
            if resp.status_code != 200:
                logger.error(
                    "yookassa_fetch_payment_error",
                    payment_id=payment_id,
                    status=resp.status_code,
                )
                return None
            return resp.json()
    except Exception as exc:
        logger.error("yookassa_fetch_payment_failed", payment_id=payment_id, error=str(exc))
        return None


async def fetch_refund(refund_id: str) -> dict | None:
    """Fetch the authoritative refund object from YooKassa by id."""
    if not is_yookassa_configured() or not refund_id:
        return None
    try:
        async with httpx.AsyncClient(auth=_auth()) as client:
            resp = await client.get(
                f"{YOOKASSA_BASE_URL}/refunds/{refund_id}",
                timeout=30,
            )
            if resp.status_code != 200:
                logger.error(
                    "yookassa_fetch_refund_error",
                    refund_id=refund_id,
                    status=resp.status_code,
                )
                return None
            return resp.json()
    except Exception as exc:
        logger.error("yookassa_fetch_refund_failed", refund_id=refund_id, error=str(exc))
        return None


def _idempotency_key() -> str:
    return str(uuid.uuid4())


async def create_payment(
    user: UserORM, plan: str, success_url: str, referral_code: str | None = None
) -> dict | None:
    """Create a YooKassa payment for subscription and return payment info."""
    if not is_yookassa_configured():
        logger.error("yookassa_not_configured")
        return None
    plan_config = PLANS.get(plan)
    if not plan_config:
        logger.error("unknown_plan", plan=plan)
        return None

    amount = plan_config["price"]
    description = f"Подписка {plan_config['name']} — Aigenis Bonds"

    payload = {
        "amount": {
            "value": amount,
            "currency": CURRENCY,
        },
        "payment_method_data": {
            "type": "bank_card",
        },
        "confirmation": {
            "type": "redirect",
            "return_url": success_url,
        },
        "capture": True,
        "description": description,
        "metadata": {
            "user_id": str(user.id),
            "plan": plan,
            "referral_code": referral_code or "",
        },
    }

    headers = {
        "Content-Type": "application/json",
        "Idempotence-Key": _idempotency_key(),
    }

    try:
        async with httpx.AsyncClient(auth=_auth()) as client:
            resp = await client.post(
                f"{YOOKASSA_BASE_URL}/payments",
                json=payload,
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                logger.error("yookassa_payment_error", status=resp.status_code, body=resp.text)
                return None
            data = resp.json()
            return {
                "payment_id": data["id"],
                "status": data["status"],
                "confirmation_url": data.get("confirmation", {}).get("confirmation_url"),
            }
    except Exception as exc:
        logger.error("yookassa_request_failed", error=str(exc))
        return None


async def handle_webhook(body: bytes) -> str | None:
    """Process an incoming YooKassa webhook notification.

    Security model: the webhook body is treated as an *untrusted* trigger. We
    only read the object id and event type from it, then re-fetch the object
    from the YooKassa API and act exclusively on the server-confirmed state.
    A forged body cannot activate a subscription because the object id either
    does not exist or its real ``status``/``metadata`` won't match.
    """
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        logger.error("invalid_webhook_json")
        return None

    event_type = event.get("event")
    obj = event.get("object", {})
    object_id = obj.get("id")

    if not event_type or not object_id:
        logger.warning("webhook_missing_fields")
        return None

    if event_type == "payment.succeeded":
        verified = await fetch_payment(object_id)
        # Trust only what YooKassa reports for this payment.
        if not verified or verified.get("status") != "succeeded":
            logger.warning("webhook_payment_not_verified", payment_id=object_id)
            return None
        await _handle_payment_succeeded(verified, verified.get("metadata", {}))
    elif event_type == "payment.canceled":
        verified = await fetch_payment(object_id)
        if not verified or verified.get("status") != "canceled":
            logger.warning("webhook_cancel_not_verified", payment_id=object_id)
            return None
        await _handle_payment_canceled(verified, verified.get("metadata", {}))
    elif event_type == "refund.succeeded":
        verified = await fetch_refund(object_id)
        if not verified or verified.get("status") != "succeeded":
            logger.warning("webhook_refund_not_verified", refund_id=object_id)
            return None
        await _handle_refund_succeeded(verified, verified.get("metadata", {}))
    else:
        logger.info("unhandled_webhook_event", event=event_type)
        return event_type

    return event_type


async def _is_payment_processed(session: AsyncSession, payment_id: str) -> bool:
    """True if this payment notification was already acted on.

    Guards against YooKassa webhook re-deliveries: the same payment event can
    arrive multiple times, including long after a newer payment superseded the
    subscription's current id (the old per-subscription ``yookassa_payment_id``
    check missed those and would extend access again for free).
    """
    result = await session.execute(
        select(BillingPaymentEventORM).where(BillingPaymentEventORM.payment_id == payment_id)
    )
    return result.scalar_one_or_none() is not None


async def _mark_payment_processed(
    session: AsyncSession, payment_id: str, event_type: str, user_id: int | None
) -> None:
    session.add(
        BillingPaymentEventORM(
            payment_id=payment_id,
            event_type=event_type,
            user_id=user_id,
        )
    )


async def _handle_payment_succeeded(obj: dict, metadata: dict) -> None:
    from scraper.db import session_scope

    user_id = _metadata_user_id(metadata)
    plan = metadata.get("plan", "pro")
    payment_id = obj.get("id")
    if not user_id or not payment_id:
        return

    # TOCTOU guard: serialize concurrent webhook deliveries for the same payment
    # to prevent double-granting subscription days under concurrent webhook calls.
    lock = _webhook_locks.setdefault(payment_id, asyncio.Lock())
    if len(_webhook_locks) > _WEBHOOK_LOCK_MAX_KEYS:
        for k in [
            k
            for k, item_lock in _webhook_locks.items()
            if not item_lock.locked() and k != payment_id
        ]:
            _webhook_locks.pop(k, None)
    async with lock:
        if plan not in PLANS:
            logger.warning("payment_unknown_plan", plan=plan, payment_id=payment_id)
            return
        plan_config = PLANS[plan]
        duration = plan_config["duration_days"]

        # Verify the amount actually paid matches the plan price. This closes the
        # gap where a crafted payment carries metadata for a more expensive plan
        # than was actually paid for.
        try:
            paid = float(obj.get("amount", {}).get("value", 0))
            expected = float(plan_config["price"])
            paid_currency = obj.get("amount", {}).get("currency", CURRENCY)
        except (TypeError, ValueError):
            logger.warning("payment_amount_unparseable", payment_id=payment_id)
            return
        if paid + 1e-9 < expected or paid_currency != CURRENCY:
            logger.warning(
                "payment_amount_mismatch",
                payment_id=payment_id,
                plan=plan,
                paid=paid,
                expected=expected,
                currency=paid_currency,
            )
            return

        async with session_scope() as session:
            # Replay guard: skip notifications already acted on (YooKassa
            # retries deliveries, and an old payment may be re-delivered after
            # a newer purchase superseded the subscription's current id).
            if await _is_payment_processed(session, payment_id):
                logger.info(
                    "webhook_payment_already_processed",
                    payment_id=payment_id,
                    event="payment.succeeded",
                )
                return

            # Find or create subscription record
            sub_result = await session.execute(
                select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
            )
            sub = sub_result.scalar_one_or_none()
            if not sub:
                sub = SubscriptionORM(user_id=user_id)
                session.add(sub)

            # Idempotency: skip if this payment was already processed. A
            # refunded/canceled payment must NOT be re-activated by a redelivered
            # ``payment.succeeded`` webhook (YooKassa retries webhooks).
            if sub.yookassa_payment_id == payment_id and sub.status in {
                "active",
                "refunded",
                "canceled",
            }:
                await session.commit()
                return

            # Sync to user (single source of truth for gating)
            user_result = await session.execute(select(UserORM).where(UserORM.id == user_id))
            user = user_result.scalar_one_or_none()

            # Update subscription. A repeat purchase extends from the later of the
            # current expiry or now, so paying again never shortens access.
            sub.yookassa_payment_id = payment_id
            sub.plan = plan
            sub.status = "active"
            now = datetime.now(UTC)
            # Extend from the later of the user's current effective expiry (which
            # may come from a Stars purchase) or now.
            base = user.subscription_expires_at if user else None
            if base is not None and base.tzinfo is None:
                base = base.replace(tzinfo=UTC)
            start = max(base, now) if base and base > now else now
            sub.current_period_start = now
            sub.current_period_end = start + timedelta(days=duration)

            if user:
                user.subscription_tier = plan
                user.subscription_expires_at = sub.current_period_end
                user.payment_channel = "yookassa"

            await _mark_payment_processed(session, payment_id, "payment.succeeded", user_id)
            await session.commit()
            logger.info("subscription_activated", user_id=user_id, plan=plan, payment_id=payment_id)

            # Attribute the conversion to a partner/referrer, if any.
            ref_code = (metadata.get("referral_code") or "").strip()
            if ref_code:
                await _attribute_referral(
                    session,
                    ref_code,
                    user_id,
                    plan,
                    paid,
                    paid_currency,
                )


async def _attribute_referral(
    session: AsyncSession,
    referral_code: str,
    referred_user_id: int,
    plan: str,
    amount: float,
    currency: str,
) -> None:
    """Record a partner/user referral conversion for later payout."""
    from api.auth.service import _resolve_referrer as _resolve_user_referrer

    partner_key_id: int | None = None
    referrer_user_id: int | None = None

    # Try partner referral code first.
    pk = (
        await session.execute(
            select(PartnerKeyORM).where(
                PartnerKeyORM.referral_code == referral_code,
                PartnerKeyORM.active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if pk is not None:
        partner_key_id = pk.id
        referrer_user_id = pk.owner_user_id
    else:
        # Fall back to a user referral code (numeric id or telegram id).
        referrer = await _resolve_user_referrer(session, referral_code)
        if referrer is not None and referrer.id != referred_user_id:
            referrer_user_id = referrer.id

    if referrer_user_id is None and partner_key_id is None:
        return

    commission_pct = float(os.getenv("REFERRAL_COMMISSION_PCT", "0"))
    session.add(
        PartnerReferralORM(
            partner_key_id=partner_key_id,
            referrer_user_id=referrer_user_id,
            referred_user_id=referred_user_id,
            plan=plan,
            amount=amount,
            currency=currency,
            commission_pct=commission_pct,
            payout_status="pending",
        )
    )
    logger.info(
        "referral_attributed",
        partner_key_id=partner_key_id,
        referrer_user_id=referrer_user_id,
        referred_user_id=referred_user_id,
        plan=plan,
    )


async def _handle_payment_canceled(obj: dict, metadata: dict) -> None:
    """Handle a canceled YooKassa payment.

    Only the currently-active YooKassa payment can cancel the subscription;
    a stale cancellation for an older payment must not corrupt the record.
    """
    from scraper.db import session_scope

    user_id = _metadata_user_id(metadata)
    payment_id = obj.get("id")
    if not user_id or not payment_id:
        return

    async with session_scope() as session:
        # Replay guard: skip notifications already acted on.
        if await _is_payment_processed(session, payment_id):
            logger.info(
                "webhook_payment_already_processed",
                payment_id=payment_id,
                event="payment.canceled",
            )
            return
        sub_result = await session.execute(
            select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
        )
        sub = sub_result.scalar_one_or_none()
        if not sub or sub.yookassa_payment_id != payment_id:
            return
        sub.status = "canceled"

        user_result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        user = user_result.scalar_one_or_none()
        # Only revoke when YooKassa is the channel that established access.
        if user and user.subscription_tier != "free" and user.payment_channel == "yookassa":
            user.subscription_tier = "free"
            user.subscription_expires_at = None
            user.payment_channel = None

        await _mark_payment_processed(session, payment_id, "payment.canceled", user_id)
        await session.commit()
        logger.info("payment_canceled", user_id=user_id, payment_id=payment_id)


async def _handle_refund_succeeded(obj: dict, _metadata: dict) -> None:
    from scraper.db import session_scope

    payment_id = obj.get("payment_id", "")
    if not payment_id:
        return

    # Replay key: the refund object's own id (refund ids are unique and never
    # collide with payment ids; a redelivered refund.succeeded must be skipped,
    # while a *different* refund for the same payment is a new event).
    refund_id = str(obj.get("id") or "").strip()

    # A refund without an id cannot be deduplicated against redeliveries, so it
    # is rejected outright — same posture as missing payment ids.
    if not refund_id:
        logger.warning("refund_missing_id", payment_id=payment_id)
        return

    # Only a FULL refund revokes access; partial refunds (e.g. a discount
    # adjustment) must not cut an active subscription.
    try:
        refund_amount = float(obj.get("amount", {}).get("value", 0))
    except (TypeError, ValueError):
        refund_amount = 0.0

    async with session_scope() as session:
        # Replay guard: skip refund notifications already acted on.
        if refund_id and await _is_payment_processed(session, refund_id):
            logger.info(
                "webhook_payment_already_processed",
                payment_id=refund_id,
                event="refund.succeeded",
            )
            return
        sub_result = await session.execute(
            select(SubscriptionORM).where(SubscriptionORM.yookassa_payment_id == payment_id)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            plan_config = PLANS.get(sub.plan or "") or {"price": 0.0}
            expected = float(plan_config.get("price", 0.0))
            if refund_amount + 1e-9 < expected:
                logger.warning(
                    "refund_partial_ignored",
                    payment_id=payment_id,
                    refunded=refund_amount,
                    expected=expected,
                )
                return
            sub.status = "refunded"
            user_result = await session.execute(select(UserORM).where(UserORM.id == sub.user_id))
            user = user_result.scalar_one_or_none()
            # Cross-channel protection: a YooKassa refund must not revoke access
            # that was paid for via Telegram Stars.
            if user and user.payment_channel == "yookassa":
                user.subscription_tier = "free"
                user.subscription_expires_at = None
                user.payment_channel = None
            if refund_id:
                await _mark_payment_processed(session, refund_id, "refund.succeeded", sub.user_id)
            await session.commit()
            logger.info("subscription_refunded", user_id=sub.user_id, payment_id=payment_id)


async def get_subscription(session: AsyncSession, user_id: int) -> SubscriptionORM | None:
    result = await session.execute(
        select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
    )
    return result.scalar_one_or_none()
