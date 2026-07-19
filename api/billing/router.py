"""YooKassa billing routes for subscription payments.

Payments are processed through YooKassa (ЮKassa) — the leading CIS payment
aggregator. Telegram Stars remain available inside the bot.
"""
from __future__ import annotations

import ipaddress
import os

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

# Official YooKassa notification source networks.
# https://yookassa.ru/developers/using-api/webhooks#ip
_YOOKASSA_NETWORKS: tuple[str, ...] = (
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/25",
    "77.75.156.11/32",
    "77.75.156.35/32",
    "77.75.154.128/25",
    "2a02:5180::/32",
)


def _allowed_networks() -> list[ipaddress._BaseNetwork]:
    """Return the set of networks allowed to POST webhooks.

    Defaults to YooKassa's published ranges; override with
    ``YOOKASSA_WEBHOOK_IPS`` (comma-separated CIDRs) for staging/self-hosted
    proxies. Set it to ``*`` to disable IP filtering (NOT recommended).
    """
    override = os.getenv("YOOKASSA_WEBHOOK_IPS", "").strip()
    raw = [c.strip() for c in override.split(",") if c.strip()] if override else list(
        _YOOKASSA_NETWORKS
    )
    nets: list[ipaddress._BaseNetwork] = []
    for cidr in raw:
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("invalid_webhook_cidr", cidr=cidr)
    return nets


def _client_ip(request: Request) -> str | None:
    """Resolve the caller IP, honouring a single trusted proxy hop.

    When TRUSTED_PROXY=1 we take the last entry of X-Forwarded-For (added by
    our own reverse proxy). Otherwise we use the raw socket peer.
    """
    if os.getenv("TRUSTED_PROXY", "").strip() in ("1", "true", "yes"):
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            # Right-most IP is the one our proxy observed.
            return xff.split(",")[-1].strip()
    return request.client.host if request.client else None


def _ip_allowed(ip: str | None) -> bool:
    if ip is None:
        return False
    nets = _allowed_networks()
    if any(str(n) == "*/0" for n in nets):  # never true, kept for clarity
        return True
    if os.getenv("YOOKASSA_WEBHOOK_IPS", "").strip() == "*":
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in n for n in nets)



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
        referral_code=req.referral_code,
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

    Security: YooKassa does not sign webhooks. We (1) restrict the caller to
    YooKassa's published IP ranges and (2) re-verify every event against the
    YooKassa API (see ``billing_service.handle_webhook``) so a forged body is
    inert even if it reaches this endpoint.
    """
    ip = _client_ip(request)
    if not _ip_allowed(ip):
        logger.warning("webhook_ip_rejected", ip=ip)
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.body()
    event_type = await billing_service.handle_webhook(body)
    if not event_type:
        raise HTTPException(status_code=400, detail="Invalid webhook")
    return {"received": True, "type": event_type}
