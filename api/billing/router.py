from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.deps import _get_current_user, _get_session
from api.auth.schemas import UserResponse
from api.auth.service import get_user_by_id
from api.billing import service as billing_service
from api.billing.schemas import (
    CheckoutSessionRequest,
    PortalSessionResponse,
    SubscriptionResponse,
)
from scraper.logging import get_logger

logger = get_logger("api.billing")

router = APIRouter(prefix="/billing", tags=["billing"])


def _is_stripe_configured() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY", ""))


@router.get("/plans")
async def list_plans():
    plans = [
        {"id": "free", "name": "Free", "price": 0, "currency": "USD", "features": [
            "Access to bond listings",
            "Basic scoring",
            "Limited API calls (10/min)",
        ]},
        {"id": "pro", "name": "Pro", "price": 29, "currency": "USD", "features": [
            "Everything in Free",
            "Full bond desk (curve, RV, carry, repo, stress)",
            "ML predictions",
            "Portfolio tools",
            "API calls (60/min)",
        ]},
        {"id": "enterprise", "name": "Enterprise", "price": 99, "currency": "USD", "features": [
            "Everything in Pro",
            "Higher API limits (300/min)",
            "Priority support",
            "Custom integrations",
        ]},
    ]
    return plans


@router.post("/checkout", response_model=PortalSessionResponse)
async def create_checkout(
    req: CheckoutSessionRequest,
    user_id: int = Depends(_get_current_user),
    session: AsyncSession = Depends(_get_session),
):
    if not _is_stripe_configured():
        raise HTTPException(status_code=503, detail="Payments not configured. Set STRIPE_SECRET_KEY.")
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    plan = None
    for k, v in billing_service.PLANS.items():
        if v["price_id"] == req.price_id:
            plan = k
            break
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid price_id")
    url = await billing_service.create_checkout_session(user, req.price_id, req.success_url, req.cancel_url)
    if not url:
        raise HTTPException(status_code=500, detail="Could not create checkout session")
    return PortalSessionResponse(url=url)


@router.post("/portal", response_model=PortalSessionResponse)
async def create_portal(
    user_id: int = Depends(_get_current_user),
    session: AsyncSession = Depends(_get_session),
):
    if not _is_stripe_configured():
        raise HTTPException(status_code=503, detail="Payments not configured")
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    base = os.getenv("APP_BASE_URL", "http://localhost:8000")
    url = await billing_service.create_portal_session(user, f"{base}/settings/billing")
    if not url:
        raise HTTPException(status_code=400, detail="No active subscription to manage")
    return PortalSessionResponse(url=url)


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_my_subscription(
    user_id: int = Depends(_get_current_user),
    session: AsyncSession = Depends(_get_session),
):
    sub = await billing_service.get_subscription(session, user_id)
    if not sub:
        return SubscriptionResponse(plan="free", status="inactive")
    return SubscriptionResponse(
        plan=sub.plan,
        status=sub.status,
        current_period_start=sub.current_period_start.isoformat() if sub.current_period_start else None,
        current_period_end=sub.current_period_end.isoformat() if sub.current_period_end else None,
        cancel_at_period_end=sub.cancel_at_period_end,
    )


@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")
    payload = await request.body()
    event_type = await billing_service.handle_webhook(payload, stripe_signature)
    if not event_type:
        raise HTTPException(status_code=400, detail="Invalid webhook")
    return {"received": True, "type": event_type}
