from __future__ import annotations

import contextlib
import os
import threading
import time
import uuid
from collections import defaultdict
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy import text as sa_text

from api.access_control import add_feature_access_headers
from api.admin.router import router as admin_router
from api.aigenis import router as aigenis_router
from api.analytics import router as analytics_router
from api.auth.deps import _get_current_user
from api.auth.router import router as auth_router
from api.billing.router import router as billing_router
from api.demo import router as demo_router
from api.document_analysis import router as document_router
from api.frontend import frontend_dir, frontend_index
from api.news import router as news_router
from api.nlp import router as nlp_router
from api.partner.router import router as partner_router
from api.portfolio_api import router as portfolio_advanced_router
from api.pricing.router import router as pricing_router
from api.reports import router as reports_router
from api.seo import router as seo_router
from api.stocks import router as stocks_router
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
    version="4.0.0",
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
app.include_router(nlp_router)
app.include_router(news_router)
app.include_router(document_router)
app.include_router(portfolio_advanced_router)
app.include_router(reports_router)

# Payments are handled via Telegram Stars inside the bot and YooKassa
# (ЮKassa) for card / SBP / Apple Pay / Google Pay on the website.
app.include_router(billing_router)
logger.info("yookassa_billing_enabled")

# Partner API (B2B keys, webhooks, read-only analytics).
app.include_router(partner_router)
logger.info("partner_api_enabled")

# Pricing endpoint with IP-based currency detection (BYN/RUB/USD).
app.include_router(pricing_router)
logger.info("pricing_enabled")

# Public acquisition widget (SEO / partner iframes). Framing is explicitly
# permitted for this router via the CSP exception in `security_headers`.
app.include_router(widget_router)
logger.info("widget_enabled")

# Public, server-rendered SEO pages (bond leaderboard + per-bond pages,
# sitemap, robots). Free organic acquisition surface — see docs/aigenis/.
app.include_router(seo_router)
logger.info("seo_pages_enabled")

# MOEX Stock data (free public ISS source).
app.include_router(stocks_router)
logger.info("stocks_api_enabled")

# Demo showcase (/demo/*). Read-only live market data + fixtures for
# portfolio-impact; fail-closed for write/side-effect endpoints.
app.include_router(demo_router)
logger.info("demo_api_enabled")

# Aigenis integration boundary (B2B) — SSO JWT + entitlement scopes, separate
# namespace /api/aigenis/v1 with cursor pagination and data-lineage headers.
app.include_router(aigenis_router)
logger.info("aigenis_integration_api_enabled")

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
            "default-src 'self'; object-src 'none'; base-uri 'self'; script-src 'self'"
        )
        # Explicitly drop the DENY that would otherwise block the iframe.
        if "X-Frame-Options" in response.headers:
            del response.headers["X-Frame-Options"]
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
_rate_limit_lock = threading.Lock()
_RATE_LIMIT = int(os.environ.get("API_RATE_LIMIT", "60"))
_RATE_WINDOW = int(os.environ.get("API_RATE_WINDOW", "60"))
_RATE_BACKEND = os.environ.get("RATE_LIMIT_BACKEND", "memory").strip().lower()
_TRUSTED_PROXY = os.environ.get("TRUSTED_PROXY", "").strip() in ("1", "true", "yes")
_MAX_TRACKED_RATE_CLIENTS = 100_000  # bound memory: evict stale entries
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


async def _rate_identity_and_limit(request: Request) -> tuple[str, int]:
    """Return the limiter key and the request budget for this caller.

    Authenticated callers are limited per user id so that many users sharing a
    NAT/proxy IP do not exhaust one another's quota, and get a higher budget
    based on their *effective* subscription tier. Anonymous callers are limited
    per (trusted) client IP with the base budget. Per-tier feature access is
    enforced separately by the RequireFeature dependency on each endpoint.
    """
    from api.access_control import _get_current_user_from_request, _get_user_tier

    user_id = _get_current_user_from_request(request)
    tier = "free"
    if user_id:
        try:
            async with session_scope() as session:
                tier = (await _get_user_tier(session, user_id)) or "free"
        except Exception:
            tier = "free"
    # Tier-aware rate limits: free = base, higher tiers get a multiplier.
    tier_limits = {
        "free": _RATE_LIMIT,
        "pro": _RATE_LIMIT * 2,
        "enterprise": _RATE_LIMIT * 5,
        "api_pro": _RATE_LIMIT * 10,
        "whitelabel": _RATE_LIMIT * 20,
    }
    limit = tier_limits.get(tier, _RATE_LIMIT)
    if user_id:
        return f"user:{user_id}", limit
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
    except Exception as exc:  # pragma: no cover - fail closed on Redis outage
        logger.warning("rate_limit_redis_unavailable_blocking", error=str(exc))
        return False


def _memory_allow(client: str, limit: int) -> bool:
    now = time.monotonic()
    cutoff = now - _RATE_WINDOW
    with _rate_limit_lock:
        # Evict stale keys so the store is bounded by distinct clients seen
        # within one window (plus retained entries), not total unique IPs ever.
        if len(_rate_limit_store) > _MAX_TRACKED_RATE_CLIENTS:
            for key in [
                k
                for k in _rate_limit_store
                if not _rate_limit_store[k] or _rate_limit_store[k][-1] <= cutoff
            ]:
                _rate_limit_store.pop(key, None)
        timestamps = _rate_limit_store[client]
        timestamps[:] = [t for t in timestamps if t > cutoff]
        if len(timestamps) >= limit:
            return False
        timestamps.append(now)
    return True


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path in ("/health", "/ready", "/openapi.json", "/docs", "/redoc"):
        return await call_next(request)
    # Public SEO pages must stay crawlable — never rate-limit crawlers away.
    if request.url.path.startswith(
        ("/bonds", "/partners", "/sitemap.xml", "/robots.txt", "/calculator", "/guides")
    ):
        return await call_next(request)
    client, limit = await _rate_identity_and_limit(request)
    allowed = (
        await _redis_allow(client, limit)
        if _RATE_BACKEND == "redis"
        else _memory_allow(client, limit)
    )
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests", "retry_after": _RATE_WINDOW},
            headers={"Retry-After": str(_RATE_WINDOW)},
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
    market: str = "bcse"
    isin: str | None = None
    price: float | None = None
    yield_to_maturity: float | None = None
    bid: float | None = None
    ask: float | None = None
    bid_yield: float | None = None
    ask_yield: float | None = None
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
    version: str = "4.0.0"


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


# --- Middleware ---


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    start = time.monotonic()
    response = await call_next(request)
    duration = time.monotonic() - start
    response.headers["X-Request-Id"] = request_id
    logger.info(
        "api_request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration * 1000, 1),
    )
    return response


@app.exception_handler(ScraperError)
async def scraper_error_handler(request: Request, exc: ScraperError):
    request_id = getattr(request.state, "request_id", None)
    logger.error("api_error", error=str(exc), context=exc.context, request_id=request_id)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error=exc.message).model_dump(),
    )


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception("api_unhandled_error", error=str(exc), request_id=request_id)
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


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics for the API worker (scraped by prometheus:9090).

    The compose prometheus job targets ``api:8000/metrics``; without this
    endpoint the scrape returned 404 and the API was invisible in Grafana.
    """
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --- Bonds ---


@app.get("/api/v1/bonds", response_model=list[BondResponse])
async def list_bonds(
    currency: str | None = None,
    market: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[BondResponse]:
    if limit < 1 or limit > 2000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative")
    async with session_scope() as session:
        stmt = select(BondORM)
        if currency:
            stmt = stmt.where(BondORM.currency == currency.upper())
        if market and market in ("bcse", "moex"):
            stmt = stmt.where(BondORM.market == market)
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
    market: str | None = None,
) -> list[BondScoreResponse]:
    if limit < 1 or limit > 2000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")
    async with session_scope() as session:
        stmt = select(BondScoreORM)
        if market and market in ("bcse", "moex"):
            stmt = stmt.join(BondORM, BondScoreORM.internal_id == BondORM.internal_id, isouter=True)
            stmt = stmt.where(BondORM.market == market)
        if min_score is not None:
            stmt = stmt.where(BondScoreORM.score >= min_score)
        stmt = stmt.order_by(BondScoreORM.score.desc()).limit(limit).offset(offset)
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
        market=b.market,
        isin=b.isin,
        price=float(b.price) if b.price is not None else None,
        yield_to_maturity=float(b.yield_to_maturity) if b.yield_to_maturity is not None else None,
        bid=float(b.bid) if b.bid is not None else None,
        ask=float(b.ask) if b.ask is not None else None,
        bid_yield=float(b.bid_yield) if b.bid_yield is not None else None,
        ask_yield=float(b.ask_yield) if b.ask_yield is not None else None,
        coupon_rate=float(b.coupon_rate) if b.coupon_rate is not None else None,
        coupon_frequency=b.coupon_frequency,
        maturity_date=b.maturity_date.isoformat() if b.maturity_date else None,
        status=b.status,
        issuer=b.issuer,
        issuer_logo=b.issuer_logo,
        fetched_at=b.fetched_at.isoformat() if b.fetched_at else None,
    )


# --- Static files (frontend) ---

# SPA asset hashes never change, so let the browser cache them aggressively.
_frontend_dir = frontend_dir()
if _frontend_dir is not None:
    assets_dir = _frontend_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    logger.info("frontend_mounted", directory=str(_frontend_dir))


# SPA catch-all: every unmatched GET goes to the frontend index.html and the
# browser router takes over. SEO routes are registered earlier and already
# split bots vs humans on /bonds, /bonds/{id} and /calculator (see api/seo.py).
@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str) -> Response:
    if path.startswith(("api/", "auth/", "billing/", "admin/", "partner/")):
        raise HTTPException(status_code=404, detail="Not Found")
    index = frontend_index()
    if index is None:
        raise HTTPException(status_code=404, detail="Frontend build not available")
    return FileResponse(
        index,
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


def _validate_production_config() -> None:
    """Surface insecure configuration at startup instead of failing silently.

    Hard requirements (missing secret) are enforced earlier in
    ``api.auth.service._resolve_jwt_secret``; here we block startup for
    any detectable insecure configuration.
    """
    from api.auth.service import is_jwt_secret_weak

    if is_jwt_secret_weak():
        raise RuntimeError(
            "SECURITY: JWT_SECRET_KEY is using an insecure default. "
            "Set a strong random secret via JWT_SECRET_KEY before starting this service."
        )
    db_url = os.environ.get("DATABASE_URL", "")
    if "aigenis:aigenis" in db_url or ":aigenis@" in db_url:
        raise RuntimeError(
            "SECURITY: DATABASE_URL contains the default credentials 'aigenis:aigenis'. "
            "Change POSTGRES_PASSWORD and update DATABASE_URL accordingly."
        )
    # Fail closed: DEMO_MODE grants anonymous callers full Pro feature access
    # (api/access_control.get_current_tier). Running it in a production
    # environment silently opens the paywall — refuse to start. Deploy the demo
    # with AIGENIS_ENVIRONMENT=demo instead.
    if os.environ.get("DEMO_MODE", "").strip() in ("1", "true", "yes") and (
        os.environ.get("AIGENIS_ENVIRONMENT", "development").strip() == "production"
    ):
        raise RuntimeError(
            "SECURITY: DEMO_MODE=1 with AIGENIS_ENVIRONMENT=production opens the "
            "paywall to anonymous users. Set AIGENIS_ENVIRONMENT=demo for demo "
            "deployments, or disable DEMO_MODE for production."
        )


# Entry point for the `bonds-api` console script (pyproject.toml). Kept here so
# the installed package has a working command even when deployed outside the
# compose file (which runs uvicorn directly).
def run() -> None:
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("API_PORT", "8000")),
        workers=int(os.environ.get("API_WORKERS", "1")),
    )
