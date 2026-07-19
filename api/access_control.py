from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.db import session_scope

# Feature flags based on subscription tiers
FEATURE_FLAGS: dict[str, dict[str, bool]] = {
    "free": {
        "access_bond_list": True,
        "access_bond_detail": True,
        "access_scores": True,
        "access_stats": True,
        "access_desk_curve": False,
        "access_desk_rv": False,
        "access_desk_carry": False,
        "access_desk_repo": False,
        "access_desk_stress": False,
        "access_portfolio": False,
        "access_forecast": False,
        "access_ml": False,
        "access_alerts": False,
        "access_recommendations": True,
        "access_bond_analysis": False,
        "access_companies": True,
        "access_search": True,
        "max_currencies": 3,
        "api_rate_limit": 10,
    },
    "pro": {
        "access_bond_list": True,
        "access_bond_detail": True,
        "access_scores": True,
        "access_stats": True,
        "access_desk_curve": True,
        "access_desk_rv": True,
        "access_desk_carry": True,
        "access_desk_repo": True,
        "access_desk_stress": True,
        "access_portfolio": True,
        "access_forecast": True,
        "access_ml": True,
        "access_alerts": True,
        "access_recommendations": True,
        "access_bond_analysis": True,
        "max_currencies": 99,
        "api_rate_limit": 60,
    },
    "enterprise": {
        "access_bond_list": True,
        "access_bond_detail": True,
        "access_scores": True,
        "access_stats": True,
        "access_desk_curve": True,
        "access_desk_rv": True,
        "access_desk_carry": True,
        "access_desk_repo": True,
        "access_desk_stress": True,
        "access_portfolio": True,
        "access_forecast": True,
        "access_ml": True,
        "access_alerts": True,
        "access_recommendations": True,
        "access_bond_analysis": True,
        "max_currencies": 99,
        "api_rate_limit": 300,
    },
    # Demo tier: a read-only, fully-featured showcase used for the public
    # (Cloudflare Tunnel) demo. Behaves like `pro` for reads but is flagged so
    # the frontend can render a "DEMO" watermark and the backend can throttle.
    "demo": {
        "access_bond_list": True,
        "access_bond_detail": True,
        "access_scores": True,
        "access_stats": True,
        "access_desk_curve": True,
        "access_desk_rv": True,
        "access_desk_carry": True,
        "access_desk_repo": True,
        "access_desk_stress": True,
        "access_portfolio": True,
        "access_forecast": True,
        "access_ml": True,
        "access_alerts": True,
        "access_recommendations": True,
        "access_bond_analysis": True,
        "is_demo": True,
        "max_currencies": 99,
        "api_rate_limit": 10,
    },
}

def _get_current_user_from_request(request: Request) -> int | None:
    token = request.headers.get("authorization", "").replace("Bearer ", "")
    if not token:
        return None

    from api.auth.service import decode_token
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    return int(payload["sub"])


async def _get_user_tier(session: AsyncSession, user_id: int) -> str | None:
    from scraper.orm import UserORM
    from telegram_bot.subscriptions import effective_tier
    result = await session.execute(
        select(UserORM.subscription_tier, UserORM.subscription_expires_at, UserORM.trial_end).where(
            UserORM.id == user_id
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    tier, expires_at, trial_end = row
    return effective_tier(tier, expires_at, trial_end)


def add_feature_access_headers(app: FastAPI) -> FastAPI:
    @app.middleware("http")
    async def add_headers(request: Request, call_next):
        response = await call_next(request)

        # Check if user is authenticated and add feature headers
        user_id = _get_current_user_from_request(request)
        if user_id:
            async with session_scope() as session:
                user_tier = await _get_user_tier(session, user_id)
                tier = user_tier or "free"

                headers = {
                    "X-User-Tier": tier,
                    "X-API-Rate-Limit": str(FEATURE_FLAGS[tier]["api_rate_limit"]),
                    "X-Is-Demo": "true" if FEATURE_FLAGS[tier].get("is_demo") else "false",
                    "X-Features": ",".join([k for k, v in FEATURE_FLAGS[tier].items() if v]),
                }

                for key, value in headers.items():
                    response.headers[key] = value

        return response


# --- Per-endpoint feature gating dependency ---------------------------------
# Robust alternative to path-matching middleware: each pro endpoint declares
# the feature flag it requires; free users get a 402 with upgrade hint.
async def get_current_tier(request: Request) -> str:
    user_id = _get_current_user_from_request(request)
    if not user_id:
        # Public demo mode (e.g. Cloudflare Tunnel showcase): anonymous callers
        # get read-only full access, flagged as demo so the frontend can show a
        # watermark and the backend can throttle.
        if os.getenv("DEMO_MODE", "").strip() in ("1", "true", "yes"):
            return "demo"
        return "free"
    async with session_scope() as session:
        tier = await _get_user_tier(session, user_id)
    return tier or "free"


async def get_optional_user_id(request: Request) -> int | None:
    return _get_current_user_from_request(request)


class RequireFeature:
    """FastAPI dependency: allow only tiers that have `flag` enabled."""

    def __init__(self, flag: str) -> None:
        self.flag = flag

    async def __call__(self, tier: str = Depends(get_current_tier)) -> None:
        flags = FEATURE_FLAGS.get(tier, FEATURE_FLAGS["free"])
        if not flags.get(self.flag, False):
            raise HTTPException(
                status_code=402,
                detail="Эта функция доступна в подписке Pro / Enterprise.",
                headers={"X-Upgrade-Required": "true"},
            )
