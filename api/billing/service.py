from __future__ import annotations

import os
from datetime import datetime

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.logging import get_logger
from scraper.orm import SubscriptionORM, UserORM

logger = get_logger("api.billing")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

stripe.api_key = STRIPE_SECRET_KEY

PLANS = {
    "free": {"price_id": os.getenv("STRIPE_PRICE_FREE", ""), "name": "Free"},
    "pro": {"price_id": os.getenv("STRIPE_PRICE_PRO", ""), "name": "Pro"},
    "enterprise": {"price_id": os.getenv("STRIPE_PRICE_ENTERPRISE", ""), "name": "Enterprise"},
}


def _get_price_id(plan: str) -> str | None:
    p = PLANS.get(plan)
    return p["price_id"] if p else None


async def get_or_create_customer(session: AsyncSession, user: UserORM) -> str:
    sub_result = await session.execute(
        select(SubscriptionORM).where(SubscriptionORM.user_id == user.id)
    )
    sub = sub_result.scalar_one_or_none()
    if sub and sub.stripe_customer_id:
        return sub.stripe_customer_id
    if not sub:
        sub = SubscriptionORM(user_id=user.id)
        session.add(sub)
        await session.flush()
    customer = stripe.Customer.create(email=user.email, name=user.name, metadata={"user_id": str(user.id)})
    sub.stripe_customer_id = customer.id
    await session.commit()
    return customer.id


async def create_checkout_session(user: UserORM, price_id: str, success_url: str, cancel_url: str) -> str | None:
    from scraper.db import session_scope
    async with session_scope() as session:
        customer_id = await get_or_create_customer(session, user)
    try:
        session_obj = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user.id)},
        )
        return session_obj.url
    except stripe.StripeError as e:
        logger.error("stripe_checkout_error", error=str(e))
        return None


async def create_portal_session(user: UserORM, return_url: str) -> str | None:
    from scraper.db import session_scope
    async with session_scope() as session:
        sub_result = await session.execute(
            select(SubscriptionORM).where(SubscriptionORM.user_id == user.id)
        )
        sub = sub_result.scalar_one_or_none()
        if not sub or not sub.stripe_customer_id:
            return None
        customer_id = sub.stripe_customer_id
    try:
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return portal.url
    except stripe.StripeError as e:
        logger.error("stripe_portal_error", error=str(e))
        return None


async def handle_webhook(payload: bytes, sig_header: str) -> str | None:
    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("stripe_webhook_secret_not_set")
        return None
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.StripeError as e:
        logger.error("stripe_webhook_verification_error", error=str(e))
        return None
    event_type = event.get("type")
    data = event["data"]["object"]
    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data)
    elif event_type == "invoice.paid":
        await _handle_invoice_paid(data)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data)
    return event_type


async def _handle_checkout_completed(data: dict) -> None:
    from scraper.db import session_scope
    user_id = int(data.get("metadata", {}).get("user_id", 0))
    if not user_id:
        return
    subscription_id = data.get("subscription")
    async with session_scope() as session:
        sub_result = await session.execute(
            select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
        )
        sub = sub_result.scalar_one_or_none()
        if sub and subscription_id:
            sub.stripe_subscription_id = subscription_id
            sub.status = "active"
            await session.commit()


async def _handle_invoice_paid(data: dict) -> None:
    from scraper.db import session_scope
    subscription_id = data.get("subscription")
    if not subscription_id:
        return
    async with session_scope() as session:
        sub_result = await session.execute(
            select(SubscriptionORM).where(SubscriptionORM.stripe_subscription_id == subscription_id)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            sub.status = "active"
            if data.get("period_start"):
                sub.current_period_start = datetime.fromtimestamp(data["period_start"])
            if data.get("period_end"):
                sub.current_period_end = datetime.fromtimestamp(data["period_end"])
            await session.commit()


async def _handle_subscription_updated(data: dict) -> None:
    from scraper.db import session_scope
    subscription_id = data.get("id")
    if not subscription_id:
        return
    async with session_scope() as session:
        sub_result = await session.execute(
            select(SubscriptionORM).where(SubscriptionORM.stripe_subscription_id == subscription_id)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            status = data.get("status", sub.status)
            sub.status = status
            sub.cancel_at_period_end = data.get("cancel_at_period_end", False)
            if data.get("current_period_start"):
                sub.current_period_start = datetime.fromtimestamp(data["current_period_start"])
            if data.get("current_period_end"):
                sub.current_period_end = datetime.fromtimestamp(data["current_period_end"])
            items = data.get("items", {}).get("data", [])
            if items:
                price_id = items[0].get("price", {}).get("id", "")
                for plan_name, plan_info in PLANS.items():
                    if plan_info["price_id"] == price_id:
                        sub.plan = plan_name
                        break
            user_result = await session.execute(select(UserORM).where(UserORM.id == sub.user_id))
            user = user_result.scalar_one_or_none()
            if user:
                user.subscription_tier = sub.plan
            await session.commit()


async def _handle_subscription_deleted(data: dict) -> None:
    from scraper.db import session_scope
    subscription_id = data.get("id")
    if not subscription_id:
        return
    async with session_scope() as session:
        sub_result = await session.execute(
            select(SubscriptionORM).where(SubscriptionORM.stripe_subscription_id == subscription_id)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            sub.status = "canceled"
            sub.plan = "free"
            user_result = await session.execute(select(UserORM).where(UserORM.id == sub.user_id))
            user = user_result.scalar_one_or_none()
            if user:
                user.subscription_tier = "free"
            await session.commit()


async def get_subscription(session: AsyncSession, user_id: int) -> SubscriptionORM | None:
    result = await session.execute(
        select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
    )
    return result.scalar_one_or_none()
