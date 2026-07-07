from __future__ import annotations

from pydantic import BaseModel


class CheckoutSessionRequest(BaseModel):
    price_id: str
    success_url: str = "/?billing=success"
    cancel_url: str = "/pricing"


class PortalSessionResponse(BaseModel):
    url: str


class SubscriptionResponse(BaseModel):
    plan: str
    status: str
    current_period_start: str | None = None
    current_period_end: str | None = None
    cancel_at_period_end: bool = False
