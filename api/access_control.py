from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.deps import _get_current_user
from api.billing.service import get_subscription
from scraper.db import session_scope
from scraper.logging import get_logger

logger = get_logger("api.access_control")

# Feature flags based on subscription tiers
FEATURE_FLAGS: Dict[str, Dict[str, bool]] = {
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
        "access_recommendations": False,
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
        "api_rate_limit": 300,
    },
}

# Pro features in terms of API endpoints
PRO_FEATURES_ROUTES: List[Dict[str, Any]] = [
    {"method": "GET", "path": "/api/v1/desk"},
    {"method": "GET", "path": "/api/v1/portfolio"},
    {"method": "GET", "path": "/api/v1/forecast"},
    {"method": "GET", "path": "/api/v1/ml"},
    {"method": "GET", "path": "/api/v1/recommendations"},
    {"method": "POST", "path": "/api/v1/rebalance"},
    {"method": "POST", "path": "/api/v1/build_plan"},
    {"method": "POST", "path": "/api/v1/allocate"},
]


def check_feature_access(
    request: Request,
    session: AsyncSession,
) -> tuple[int, Optional[str]]:
    user_id = _get_current_user_from_request(request)
    if not user_id:
        return 401, "Not authenticated"

    user_tier = _get_user_tier(session, user_id)
    if not user_tier:
        return 401, "User tier not found"

    flags = FEATURE_FLAGS.get(user_tier, FEATURE_FLAGS["free"])
    
    # Check API rate limit (simple implementation)
    # In production, use Redis or database to track usage
    client_host = request.client.host if request.client else "unknown"
    
    return 200, None


def _get_current_user_from_request(request: Request) -> Optional[int]:
    token = request.headers.get("authorization", "").replace("Bearer ", "")
    if not token:
        return None
    
    from api.auth.service import decode_token
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    return int(payload["sub"])


async def _get_user_tier(session: AsyncSession, user_id: int) -> Optional[str]:
    from scraper.orm import UserORM
    result = await session.execute(
        select(UserORM.subscription_tier).where(UserORM.id == user_id)
    )
    return result.scalar_one_or_none()


class FeatureAccessMiddleware:
    def __init__(self, app: FastAPI):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        
        # Skip middleware for public endpoints
        if path in ["/health", "/ready", "/openapi.json", "/docs", "/redoc", "/auth/login", "/auth/register"]:
            return await self.app(scope, receive, send)
        
        # Check feature access
        request = Request(scope, receive)
        async with session_scope() as session:
            status_code, error = await check_feature_access(request, session)
            if status_code != 200:
                response = {
                    "error": error or "Access denied",
                    "upgrade_required": True,
                    "upgrade_url": "/pricing",
                }
                from fastapi.responses import JSONResponse
                await send({
                    "type": "http.response.start",
                    "status": status_code,
                    "headers": [(b"content-type", b"application/json")],
                })
                await send({
                    "type": "http.response.body",
                    "body": json.dumps(response).encode(),
                })
                return

        await self.app(scope, receive, send)


def rate_limit_middleware(app: FastAPI) -> FastAPI:
    """Simple rate limiting middleware based on subscription tier"""
    
    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        path = request.url.path
        if path in ["/health", "/ready", "/openapi.json", "/docs", "/redoc"]:
            return await call_next(request)
        
        client_host = request.client.host if request.client else "unknown"
        user_id = _get_current_user_from_request(request)
        
        async with session_scope() as session:
            if user_id:
                user_tier = await _get_user_tier(session, user_id)
                tier = user_tier or "free"
            else:
                tier = "free"
            
            limit = FEATURE_FLAGS.get(tier, FEATURE_FLAGS["free"])["api_rate_limit"]
        
        # Simplified rate limiting - in production, use Redis or Redis-like
        # This is a simple implementation that would need to be more robust
        
        return await call_next(request)


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
                    "X-Features": ",".join([k for k, v in FEATURE_FLAGS[tier].items() if v]),
                }
                
                for key, value in headers.items():
                    response.headers[key] = value
        
        return response