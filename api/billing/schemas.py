from pydantic import BaseModel


class CreatePaymentRequest(BaseModel):
    """Create a YooKassa payment for a subscription plan."""
    plan: str  # "pro" | "enterprise"
    success_url: str = "/?billing=success"
    cancel_url: str = "/subscribe"


class PaymentResponse(BaseModel):
    payment_id: str
    confirmation_url: str | None = None


class SubscriptionResponse(BaseModel):
    plan: str
    status: str
    current_period_start: str | None = None
    current_period_end: str | None = None
    cancel_at_period_end: bool = False
    provider: str = "yookassa"


class YooKassaWebhookEvent(BaseModel):
    type: str
    event: str
    object: dict
