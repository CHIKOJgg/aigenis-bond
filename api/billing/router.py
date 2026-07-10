"""YooKassa billing routes for subscription payments.

Payments are processed through YooKassa (ЮKassa) — the leading CIS payment
aggregator. Telegram Stars remain available inside the bot.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.deps import _get_current_user, _get_session
from api.auth.service import get_user_by_id
from api.billing import service as billing_service
from api.billing.schemas import (
    CreatePaymentRequest,
    PaymentResponse,
    SubscriptionResponse,
)
from api.billing.service import PLANS, is_yookassa_configured
from scraper.logging import get_logger

logger = get_logger("api.billing")

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans")
async def list_plans():
    """List available subscription plans with YooKassa prices."""
    return [
        {
            "id": "free",
            "name": "Free",
            "price": 0,
            "currency": "BYN",
            "features": [
                "Доступ к списку облигаций",
                "Базовый скоринг",
                "10 запросов/мин к API",
            ],
        },
        {
            "id": "pro",
            "name": "Pro",
            "price": float(PLANS["pro"]["price"]),
            "currency": "BYN",
            "features": [
                "Всё из Free",
                "Fixed Income Desk (RV, duration, carry, repo, stress)",
                "ML-прогнозы и рекомендации",
                "Портфель и оптимизация",
                "60 запросов/мин к API",
            ],
        },
        {
            "id": "enterprise",
            "name": "Enterprise",
            "price": float(PLANS["enterprise"]["price"]),
            "currency": "BYN",
            "features": [
                "Всё из Pro",
                "300 запросов/мин к API",
                "Приоритетная поддержка",
                "Индивидуальные интеграции",
            ],
        },
    ]


@router.post("/create-payment", response_model=PaymentResponse)
async def create_payment(
    req: CreatePaymentRequest,
    user_id: int = Depends(_get_current_user),
    session: AsyncSession = Depends(_get_session),
):
    """Create a YooKassa payment for subscription."""
    if not is_yookassa_configured():
        raise HTTPException(
            status_code=503,
            detail="YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY не настроены на сервере.",
        )
    if req.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Неизвестный тариф")

    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    base = req.success_url
    if base.startswith("/"):
        base = f"https://{req.success_url}"  # fallback

    result = await billing_service.create_payment(
        user=user,
        plan=req.plan,
        success_url=req.success_url,
        cancel_url=req.cancel_url,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Не удалось создать платёж")

    return PaymentResponse(
        payment_id=result["payment_id"],
        confirmation_url=result.get("confirmation_url"),
    )


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_my_subscription(
    user_id: int = Depends(_get_current_user),
    session: AsyncSession = Depends(_get_session),
):
    """Get current user's subscription status."""
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
async def yookassa_webhook(request: Request):
    """Webhook endpoint for YooKassa payment notifications.

    Configure this URL in your YooKassa merchant dashboard:
    https://yookassa.ru/merchant/notifications
    """
    body = await request.body()
    event_type = await billing_service.handle_webhook(body)
    if not event_type:
        raise HTTPException(status_code=400, detail="Invalid webhook")
    return {"received": True, "type": event_type}
