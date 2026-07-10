"""YooKassa payment processing for subscriptions.

API docs: https://yookassa.ru/developers/api
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.logging import get_logger
from scraper.orm import SubscriptionORM, UserORM

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


def _auth() -> tuple[str, str]:
    return YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY


def _idempotency_key() -> str:
    return str(uuid.uuid4())


async def create_payment(user: UserORM, plan: str, success_url: str, cancel_url: str) -> dict | None:
    """Create a YooKassa payment for subscription and return payment info."""
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
    """Process incoming YooKassa webhook notification."""
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        logger.error("invalid_webhook_json")
        return None

    event_type = event.get("event")
    obj = event.get("object", {})
    metadata = obj.get("metadata", {})

    if event_type == "payment.succeeded":
        await _handle_payment_succeeded(obj, metadata)
    elif event_type == "payment.canceled":
        await _handle_payment_canceled(obj, metadata)
    elif event_type == "refund.succeeded":
        await _handle_refund_succeeded(obj, metadata)
    else:
        logger.info("unhandled_webhook_event", event=event_type)

    return event_type


async def _handle_payment_succeeded(obj: dict, metadata: dict) -> None:
    from scraper.db import session_scope

    user_id = int(metadata.get("user_id", 0))
    plan = metadata.get("plan", "pro")
    payment_id = obj.get("id")
    if not user_id or not payment_id:
        return

    plan_config = PLANS.get(plan, PLANS["pro"])
    duration = plan_config["duration_days"]

    async with session_scope() as session:
        # Find or create subscription record
        sub_result = await session.execute(
            select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
        )
        sub = sub_result.scalar_one_or_none()
        if not sub:
            sub = SubscriptionORM(user_id=user_id)
            session.add(sub)

        # Update subscription
        sub.yookassa_payment_id = payment_id
        sub.plan = plan
        sub.status = "active"
        now = datetime.now(UTC)
        sub.current_period_start = now
        sub.current_period_end = now + timedelta(days=duration)

        # Sync to user
        user_result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.subscription_tier = plan
            user.subscription_expires_at = sub.current_period_end

        await session.commit()
        logger.info("subscription_activated", user_id=user_id, plan=plan, payment_id=payment_id)


async def _handle_payment_canceled(obj: dict, metadata: dict) -> None:
    from scraper.db import session_scope

    user_id = int(metadata.get("user_id", 0))
    payment_id = obj.get("id")
    if not user_id:
        return

    async with session_scope() as session:
        sub_result = await session.execute(
            select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            sub.status = "canceled"

        user_result = await session.execute(select(UserORM).where(UserORM.id == user_id))
        user = user_result.scalar_one_or_none()
        if user and user.subscription_tier != "free":
            # Only downgrade if this was their active payment
            if sub and sub.yookassa_payment_id == payment_id:
                user.subscription_tier = "free"
                user.subscription_expires_at = None

        await session.commit()
        logger.info("payment_canceled", user_id=user_id, payment_id=payment_id)


async def _handle_refund_succeeded(obj: dict, metadata: dict) -> None:
    from scraper.db import session_scope

    payment_id = obj.get("payment_id", "")
    if not payment_id:
        return

    async with session_scope() as session:
        sub_result = await session.execute(
            select(SubscriptionORM).where(SubscriptionORM.yookassa_payment_id == payment_id)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            sub.status = "refunded"
            user_result = await session.execute(select(UserORM).where(UserORM.id == sub.user_id))
            user = user_result.scalar_one_or_none()
            if user:
                user.subscription_tier = "free"
                user.subscription_expires_at = None
            await session.commit()
            logger.info("subscription_refunded", user_id=sub.user_id, payment_id=payment_id)


async def get_subscription(session: AsyncSession, user_id: int) -> SubscriptionORM | None:
    result = await session.execute(
        select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
    )
    return result.scalar_one_or_none()
