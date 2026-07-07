from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy import text as sa_text

from api.admin.router import router as admin_router
from api.auth.router import router as auth_router
from api.billing.router import router as billing_router
from scraper.config import get_settings
from scraper.db import check_db_health, dispose, session_scope
from scraper.errors import ScraperError
from scraper.logging import get_logger
from scraper.orm import BondORM, BondScoreORM

logger = get_logger("api")

app = FastAPI(
    title="Aigenis Bonds API",
    description="Production-grade REST API for bond fixed income data",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

settings = get_settings()
_cors_origins = os.environ.get("CORS_ORIGINS", "").split(",") if os.environ.get("CORS_ORIGINS") else ["*"]

# Include routers
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(admin_router)

# --- Rate limiting ---

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = int(os.environ.get("API_RATE_LIMIT", "60"))
_RATE_WINDOW = int(os.environ.get("API_RATE_WINDOW", "60"))


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path in ("/health", "/ready", "/openapi.json", "/docs", "/redoc"):
        return await call_next(request)
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    timestamps = _rate_limit_store[client]
    cutoff = now - _RATE_WINDOW
    timestamps[:] = [t for t in timestamps if t > cutoff]
    if len(timestamps) >= _RATE_LIMIT:
        return JSONResponse(status_code=429, content={"error": "Too many requests", "retry_after": _RATE_WINDOW})
    timestamps.append(now)
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
        price=float(b.price) if b.price else None,
        yield_to_maturity=float(b.yield_to_maturity) if b.yield_to_maturity else None,
        coupon_rate=float(b.coupon_rate) if b.coupon_rate else None,
        coupon_frequency=b.coupon_frequency,
        maturity_date=b.maturity_date.isoformat() if b.maturity_date else None,
        status=b.status,
        issuer=b.issuer,
        fetched_at=b.fetched_at.isoformat() if b.fetched_at else None,
    )


# --- Static files (frontend) ---

_frontend_dir = os.environ.get("FRONTEND_DIR", "")
if _frontend_dir and os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
    logger.info("frontend_mounted", directory=_frontend_dir)


@app.on_event("shutdown")
async def shutdown():
    await dispose()
