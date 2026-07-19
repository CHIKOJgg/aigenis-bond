from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.logging import get_logger
from scraper.orm import SubscriptionORM, UserORM

logger = get_logger("api.pricing")

PLANS = {
    "free": {
        "price": 0,
        "currency": "BYN",
        "interval": None,
        "features": {
            "max_bonds": -1,
            "max_api_calls": 10,
            "include_desk": False,
            "include_ml": False,
            "include_portfolio": False,
        },
    },
    "pro": {
        "price": 2900,
        "currency": "BYN",
        "interval": "month",
        "features": {
            "max_bonds": 1000,
            "max_api_calls": 60,
            "include_desk": True,
            "include_ml": True,
            "include_portfolio": True,
        },
    },
    "enterprise": {
        "price": 9900,
        "currency": "BYN",
        "interval": "month",
        "features": {
            "max_bonds": -1,
            "max_api_calls": 300,
            "include_desk": True,
            "include_ml": True,
            "include_portfolio": True,
            "include_custom": True,
        },
    },
}


async def get_available_plans() -> list[dict[str, Any]]:
    """Return pricing plans for frontend display"""
    plans = []

    for plan_id, plan_data in PLANS.items():
        if plan_id == "free":
            price = 0
            price_display = "Free"
            price_note = ""
        else:
            price = plan_data["price"]
            price_display = f"${price / 100:.2f}"
            price_note = "per month"

        plans.append({
            "id": plan_id,
            "name": plan_data.get("name", plan_id.capitalize()),
            "price": price,
            "price_display": price_display,
            "currency": plan_data["currency"],
            "interval": plan_data["interval"],
            "price_note": price_note,
            "features": plan_data["features"],
            "popular": plan_id == "pro",
        })

    return plans


async def get_current_plan(user_id: int, session: AsyncSession) -> dict[str, Any]:
    """Get current subscription plan for a user"""
    result = await session.execute(
        select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        return PLANS["free"]

    return PLANS.get(subscription.plan, PLANS["free"])


async def can_user_access_feature(user_id: int, feature: str, session: AsyncSession) -> bool:
    """Check if user can access a specific feature"""
    subscription_result = await session.execute(
        select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
    )
    subscription = subscription_result.scalar_one_or_none()

    tier = "free" if not subscription else subscription.plan

    available_plans = PLANS
    return tier in available_plans and feature in available_plans[tier]["features"]


async def get_user_usage_stats(user_id: int, session: AsyncSession) -> dict[str, Any]:
    """Get usage statistics for a user based on their current plan"""
    current_plan = await get_current_plan(user_id, session)

    # Count bonds accessed by the user (example)
    # This would need to be implemented with actual data collection
    bonds_accessed = 0
    max_bonds = current_plan["features"]["max_bonds"]
    bonds_remaining = max_bonds - bonds_accessed if max_bonds > 0 else None

    # Current tier
    tier = await _get_user_tier(session, user_id)

    return {
        "current_tier": tier,
        "current_plan": current_plan["name"],
        "limits": {
            "max_bonds": max_bonds if max_bonds > 0 else "Unlimited",
            "bonds_used": bonds_accessed,
            "bonds_remaining": bonds_remaining if bonds_remaining is not None else None,
        },
        "next_billing": await _get_next_billing_date(session, user_id),
    }


async def _get_user_tier(session: AsyncSession, user_id: int) -> str:
    """Get the current tier of a user"""
    result = await session.execute(
        select(UserORM.subscription_tier).where(UserORM.id == user_id)
    )
    return result.scalar_one_or_none() or "free"


async def _get_next_billing_date(session: AsyncSession, user_id: int) -> str | None:
    """Get the next billing date for a user with a paid subscription"""
    result = await session.execute(
        select(SubscriptionORM.current_period_end).where(SubscriptionORM.user_id == user_id)
    )
    next_billing = result.scalar_one_or_none()

    if next_billing:
        return next_billing.isoformat()

    return None


async def calculate_upgrade_cost(from_plan: str, to_plan: str) -> dict[str, Any]:
    """Calculate the cost difference between two plans"""
    if from_plan == to_plan:
        return {"difference": 0, "price_change": 0, "upgrade": False}

    from_cost = PLANS[from_plan]["price"]
    to_cost = PLANS[to_plan]["price"]

    price_diff = to_cost - from_cost

    # Find the best plan to upgrade to (considering interval)
    from_interval = PLANS[from_plan]["interval"]
    to_interval = PLANS[to_plan]["interval"]

    if from_interval != to_interval:
        if from_interval == "month" and to_interval == "month":
            rate = 1.0
        elif from_interval == "month" and to_interval is None:
            rate = 12.0  # month to year
        elif from_interval is None and to_interval == "month":
            rate = 1.0 / 12.0  # year to month
        else:
            rate = 1.0
    else:
        rate = 1.0

    effective_diff = price_diff * rate

    return {
        "difference": to_cost - from_cost,
        "price_change": price_diff,
        "effective_price_change": effective_diff,
        "upgrade": True,
        "upgrade_amount": abs(effective_diff),
        "upgrade_from": from_plan,
        "upgrade_to": to_plan,
    }
