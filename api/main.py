from __future__ import annotations

import contextlib
import os
import time
from collections import defaultdict
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy import text as sa_text

from api.access_control import add_feature_access_headers
from api.admin.router import router as admin_router
from api.analytics import router as analytics_router
from api.auth.deps import _get_current_user
from api.auth.router import router as auth_router
from api.billing.router import router as billing_router
from api.partner.router import router as partner_router
from api.widget import router as widget_router
from scraper.config import get_settings
from scraper.db import check_db_health, dispose, session_scope
from scraper.errors import ScraperError
from scraper.logging import get_logger
from scraper.orm import BondORM, BondScoreORM

logger = get_logger("api")

@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    _validate_production_config()
    from scraper.observability import init_sentry

    _settings = get_settings()
    init_sentry(_settings.aigenis.sentry_dsn, environment=_settings.aigenis.environment)
    yield
    await dispose()


app = FastAPI(
    title="Aigenis Bonds API",
    description="Production-grade REST API for bond fixed income data",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

settings = get_settings()
# CORS: allow only explicitly configured origins. Never use wildcard with credentials.
# In development, set CORS_ORIGINS=http://localhost:5173,http://localhost:80
# In production, set to your actual domain: https://app.example.com
_cors_env = os.environ.get("CORS_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
if not _cors_origins:
    logger.warning(
        "CORS_ORIGINS not configured — API will reject all cross-origin requests. "
        "Set CORS_ORIGINS in .env for your frontend domain(s)."
    )

# Include routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(analytics_router)

# Payments are handled via Telegram Stars inside the bot and YooKassa
# (ЮKassa) for card / SBP / Apple Pay / Google Pay on the website.
app.include_router(billing_router)
logger.info("yookassa_billing_enabled")

# Partner API (B2B keys, webhooks, read-only analytics).
app.include_router(partner_router)
logger.info("partner_api_enabled")

# Public acquisition widget (SEO / partner iframes). Framing is explicitly
# permitted for this router via the CSP exception in `security_headers`.
app.include_router(widget_router)
logger.info("widget_enabled")

# --- Security headers ---
# Applied to every response (except the docs/OpenAPI endpoints) to harden the
# app against clickjacking, MIME sniffing, and a baseline of XSS vectors.
_SECURITY_HEADERS_SKIP_PATHS = {"/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in _SECURITY_HEADERS_SKIP_PATHS:
        return response
    # The public widget is designed to be embedded in partner sites / blogs.
    # Allow framing from any origin for /widget paths only; everything else is
    # locked down with frame-ancestors 'none'.
    if request.url.path.startswith("/widget"):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; object-src 'none'; "
            "base-uri 'self'; script-src 'self'"
        )
        # Explicitly drop the DENY that would otherwise block the iframe.
        response.headers.pop("X-Frame-Options", None)
        return response
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; object-src 'none'; frame-ancestors 'none'; "
        "base-uri 'self'; script-src 'self'",
    )
    return response


# Expose the caller's subscription tier / feature flags on every response.
add_feature_access_headers(app)

# --- Rate limiting ---
# In-memory limiter works for a single instance. For horizontal scaling set
# RATE_LIMIT_BACKEND=redis (uses REDIS_URL) so the counter is shared across
# every API replica.
#
# Identity resolution:
#   * authenticated requests are keyed and limited per user id (and per tier),
#     so one user behind a shared NAT/proxy cannot exhaust everyone's quota and
#     paying tiers get their higher limits;
#   * anonymous requests fall back to the client IP, read from the last
#     X-Forwarded-For hop ONLY when TRUSTED_PROXY is set (otherwise the socket
#     peer), so the limiter is not trivially bypassed by spoofing the header.

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = int(os.environ.get("API_RATE_LIMIT", "60"))
_RATE_WINDOW = int(os.environ.get("API_RATE_WINDOW", "60"))
_RATE_BACKEND = os.environ.get("RATE_LIMIT_BACKEND", "memory").strip().lower()
_TRUSTED_PROXY = os.environ.get("TRUSTED_PROXY", "").strip() in ("1", "true", "yes")
_redis_client: Any = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


def _client_ip(request: Request) -> str:
    if _TRUSTED_PROXY:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            # Right-most entry is the address observed by our own proxy.
            return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _rate_identity_and_limit(request: Request) -> tuple[str, int]:
    """Return the limiter key and the request budget for this caller.

    Authenticated callers are limited per user id so that many users sharing a
    NAT/proxy IP do not exhaust one another's quota. Anonymous callers are
    limited per (trusted) client IP. Per-tier feature access is enforced
    separately by the RequireFeature dependency on each endpoint.
    """
    from api.access_control import _get_current_user_from_request

    user_id = _get_current_user_from_request(request)
    if user_id:
        return f"user:{user_id}", _RATE_LIMIT
    return f"ip:{_client_ip(request)}", _RATE_LIMIT


async def _redis_allow(client: str, limit: int) -> bool:
    """Fixed-window counter shared across instances via Redis."""
    try:
        redis = _get_redis()
        key = f"ratelimit:{client}:{int(time.time()) // _RATE_WINDOW}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, _RATE_WINDOW)
        return count <= limit
    except Exception as exc:  # pragma: no cover - fail open, log and fall back
        logger.warning("rate_limit_redis_unavailable", error=str(exc))
        return True


def _memory_allow(client: str, limit: int) -> bool:
    now = time.monotonic()
    timestamps = _rate_limit_store[client]
    cutoff = now - _RATE_WINDOW
    timestamps[:] = [t for t in timestamps if t > cutoff]
    if len(timestamps) >= limit:
        return False
    timestamps.append(now)
    return True


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path in ("/health", "/ready", "/openapi.json", "/docs", "/redoc"):
        return await call_next(request)
    client, limit = _rate_identity_and_limit(request)
    allowed = (
        await _redis_allow(client, limit)
        if _RATE_BACKEND == "redis"
        else _memory_allow(client, limit)
    )
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests", "retry_after": _RATE_WINDOW},
        )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic response models ---


class BondResponse(BaseModel):
    internal_id: str
    name: str
    currency: str
    price: float | None = None
    yield_to_maturity: float | None = None
    coupon_rate: float | None = None
    coupon_frequency: int | None = None
    maturity_date: str | None = None
    status: str
    issuer: str | None = None
    issuer_logo: str | None = None
    fetched_at: str | None = None


class BondScoreResponse(BaseModel):
    internal_id: str
    score: float
    tier: str | None = None


class HealthResponse(BaseModel):
    status: str
    db: str
    uptime_seconds: float | None = None
    version: str = "3.0.0"


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


# --- Middleware ---


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration = time.monotonic() - start
    logger.info(
        "api_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration * 1000, 1),
    )
    return response


@app.exception_handler(ScraperError)
async def scraper_error_handler(_request: Request, exc: ScraperError):
    logger.error("api_error", error=str(exc), context=exc.context)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error=exc.message).model_dump(),
    )


@app.exception_handler(Exception)
async def global_error_handler(_request: Request, exc: Exception):
    logger.exception("api_unhandled_error", error=str(exc))
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error="Internal server error").model_dump(),
    )


# --- Health ---

_start_time = time.monotonic()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_status = await check_db_health()
    return HealthResponse(
        status="ok" if db_status["status"] == "ok" else "degraded",
        db=db_status["status"],
        uptime_seconds=time.monotonic() - _start_time,
    )


@app.get("/ready")
async def readiness() -> HealthResponse:
    db_status = await check_db_health()
    if db_status["status"] != "ok":
        raise HTTPException(status_code=503, detail="Database unavailable")
    return HealthResponse(status="ok", db="ok", uptime_seconds=time.monotonic() - _start_time)


# --- Bonds ---


@app.get("/api/v1/bonds", response_model=list[BondResponse])
async def list_bonds(
    currency: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[BondResponse]:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative")
    async with session_scope() as session:
        stmt = select(BondORM)
        if currency:
            stmt = stmt.where(BondORM.currency == currency.upper())
        stmt = stmt.limit(limit).offset(offset)
        result = await session.execute(stmt)
        bonds = list(result.scalars().all())
    return [_bond_to_response(b) for b in bonds]


@app.get("/api/v1/bonds/{internal_id}", response_model=BondResponse)
async def get_bond(internal_id: str) -> BondResponse:
    async with session_scope() as session:
        result = await session.execute(select(BondORM).where(BondORM.internal_id == internal_id))
        bond = result.scalar_one_or_none()
    if bond is None:
        raise HTTPException(status_code=404, detail=f"Bond {internal_id} not found")
    return _bond_to_response(bond)


# --- Watchlist (favorites), persisted server-side per user -----------------
class WatchlistResponse(BaseModel):
    watchlist: list[str]


@app.post("/api/v1/watchlist", response_model=WatchlistResponse)
async def add_to_watchlist(
    internal_id: str,
    user_id: int = Depends(_get_current_user),
) -> WatchlistResponse:
    """Add a bond to the current user's watchlist (favorites)."""
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == internal_id))
        ).scalar_one_or_none()
        if bond is None:
            raise HTTPException(status_code=404, detail=f"Bond {internal_id} not found")
        from telegram_bot.preferences_repository import add_to_watchlist as repo_add

        prefs = await repo_add(session, user_id, internal_id)
    return WatchlistResponse(watchlist=prefs.watchlist)


@app.delete("/api/v1/watchlist/{internal_id}", response_model=WatchlistResponse)
async def remove_from_watchlist(
    internal_id: str,
    user_id: int = Depends(_get_current_user),
) -> WatchlistResponse:
    """Remove a bond from the current user's watchlist (favorites)."""
    from telegram_bot.preferences_repository import remove_from_watchlist as repo_remove

    async with session_scope() as session:
        prefs = await repo_remove(session, user_id, internal_id)
    return WatchlistResponse(watchlist=prefs.watchlist)


@app.get("/api/v1/scores", response_model=list[BondScoreResponse])
async def list_scores(
    limit: int = 20,
    offset: int = 0,
    min_score: float | None = None,
) -> list[BondScoreResponse]:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 1000")
    async with session_scope() as session:
        stmt = select(BondScoreORM).order_by(BondScoreORM.score.desc()).limit(limit).offset(offset)
        if min_score is not None:
            stmt = stmt.where(BondScoreORM.score >= min_score)
        result = await session.execute(stmt)
        scores = list(result.scalars().all())
    return [
        BondScoreResponse(
            internal_id=s.internal_id,
            score=float(s.score) if s.score else 0,
            tier=s.tier,
        )
        for s in scores
    ]


@app.get("/api/v1/stats")
async def get_stats() -> dict[str, Any]:
    async with session_scope() as session:
        total = await session.execute(sa_text("SELECT COUNT(*) FROM bonds"))
        active = await session.execute(
            sa_text("SELECT COUNT(*) FROM bonds WHERE status = 'active'")
        )
        by_currency = await session.execute(
            sa_text("SELECT currency, COUNT(*) as cnt FROM bonds GROUP BY currency")
        )
    return {
        "total_bonds": total.scalar() or 0,
        "active_bonds": active.scalar() or 0,
        "by_currency": {row[0]: row[1] for row in by_currency.fetchall()},
    }


def _bond_to_response(b: BondORM) -> BondResponse:
    return BondResponse(
        internal_id=b.internal_id,
        name=b.name,
        currency=b.currency,
        price=float(b.price) if b.price is not None else None,
        yield_to_maturity=float(b.yield_to_maturity) if b.yield_to_maturity is not None else None,
        coupon_rate=float(b.coupon_rate) if b.coupon_rate is not None else None,
        coupon_frequency=b.coupon_frequency,
        maturity_date=b.maturity_date.isoformat() if b.maturity_date else None,
        status=b.status,
        issuer=b.issuer,
        issuer_logo=b.issuer_logo,
        fetched_at=b.fetched_at.isoformat() if b.fetched_at else None,
    )


# --- Static files (frontend) ---

_frontend_dir = os.environ.get("FRONTEND_DIR", "")
if _frontend_dir and os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
    logger.info("frontend_mounted", directory=_frontend_dir)


def _validate_production_config() -> None:
    """Surface insecure configuration at startup instead of failing silently.

    Hard requirements (missing secret) are enforced earlier in
    ``api.auth.service._resolve_jwt_secret``; here we only warn loudly.
    """
    from api.auth.service import is_jwt_secret_weak

    if is_jwt_secret_weak():
        logger.warning(
            "security_risk: JWT_SECRET_KEY is using an insecure default — set a strong random "
            "secret via JWT_SECRET_KEY before exposing this service."
        )
    db_url = os.environ.get("DATABASE_URL", "")
    if "aigenis:aigenis" in db_url or ":aigenis@" in db_url:
        logger.warning("security_risk: DATABASE_URL uses the default credentials — change POSTGRES_PASSWORD.")


