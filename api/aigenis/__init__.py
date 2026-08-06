"""
Aigenis Integration API — B2B контракт поставки аналитики.

Namespace: /api/aigenis/v1

Эндпоинты:
- GET  /bonds                         — список облигаций с Score
- GET  /bonds/{instrument_id}          — детальная аналитика
- POST /portfolio-impact               — портфельный эффект
- POST /alerts                         — создание алерта

Все ответы содержат заголовки:
- X-Request-Id          — correlation id
- X-Data-As-Of          — свежесть данных (ISO 8601)
- X-Model-Version       — версия скоринговой модели
- X-Data-Quality        — ok | warning | critical

Аутентификация: SSO JWT от Aigenis (Bearer токен).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/aigenis/v1", tags=["Aigenis Integration"])


# ──────────────────────────────────────────────
# Response Models
# ──────────────────────────────────────────────


class BondScoreDTO(BaseModel):
    value: float
    status: str  # attractive | neutral | review | high_risk | no_data
    version: str = "v1"


class BondItemDTO(BaseModel):
    instrument_id: str
    isin: str | None = None
    name: str
    issuer: str | None = None
    currency: str
    ytm_pct: float | None = None
    maturity_date: str | None = None
    duration_years: float | None = None
    liquidity: str | None = None  # high | medium | low
    score: BondScoreDTO | None = None


class BondListResponse(BaseModel):
    as_of: str
    data_status: str  # ok | warning | critical
    items: list[BondItemDTO]
    next_cursor: str | None = None


class ExplanationFactorDTO(BaseModel):
    label: str
    direction: str  # positive | negative | neutral
    plain_text: str
    importance: str = "medium"  # high | medium | low


class BondDetailResponse(BaseModel):
    instrument: BondItemDTO
    score: BondScoreDTO | None = None
    explanation: list[ExplanationFactorDTO] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = ""


class PortfolioImpactRequest(BaseModel):
    portfolio_id: str | None = None
    instrument_id: str
    allocation_pct: float = Field(ge=1, le=100)


class ConstraintCheckDTO(BaseModel):
    name: str
    status: str  # ok | warning | breach
    detail: str


class PortfolioImpactResponse(BaseModel):
    before: dict[str, float] = Field(default_factory=dict)
    after: dict[str, float] = Field(default_factory=dict)
    deltas: dict[str, float] = Field(default_factory=dict)
    constraints: list[ConstraintCheckDTO] = Field(default_factory=list)
    summary: str = ""
    disclaimer: str = ""


class AlertRequest(BaseModel):
    instrument_id: str
    metric: str  # price | yield | score | dividend
    operator: str = "gt"  # gt | lt | gte | lte
    threshold: float
    idempotency_key: str | None = None


class AlertResponse(BaseModel):
    alert_id: str
    status: str  # created | duplicate | rejected
    created_at: str


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    request_id: str


# ──────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────


async def verify_sso_token(authorization: str | None = Header(None)) -> dict[str, Any]:
    """
    Проверка SSO JWT токена от Aigenis.

    В production проверяет:
    - iss (issuer)  = AIGENIS_SSO_ISSUER
    - aud (audience) = AIGENIS_SSO_AUDIENCE
    - exp (expiry)
    - signature через JWKS URL (AIGENIS_SSO_JWKS_URL)
    - scopes должен содержать analytics:read

    В demo/staging — пропускает без проверки.
    """
    # TODO: имплементировать реальную валидацию JWT
    # Для демо возвращаем фиктивный контекст
    return {
        "sub": "opaque-user-id",
        "tenant": "aigenis",
        "tier": "premium",
    }


def make_request_id(request: Request) -> str:
    """Извлечь или сгенерировать X-Request-Id."""
    existing = request.headers.get("X-Request-Id") or request.headers.get("X-Correlation-Id")
    if existing:
        return existing
    return str(uuid4())


def response_headers() -> dict[str, str]:
    """Стандартные заголовки ответа."""
    return {
        "X-Model-Version": "v1",
        "X-Data-As-Of": datetime.now(UTC).isoformat(),
        "X-Data-Quality": "ok",
    }


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────


@router.get(
    "/bonds",
    response_model=BondListResponse,
    summary="Список облигаций с аналитикой",
)
async def list_bonds(
    market: str = "BCSE",
    currency: str | None = None,
    term: str | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    _auth: dict = Depends(verify_sso_token),
):
    """
    Получить список облигаций с базовой аналитикой и Score.

    Параметры:
    - market: BCSE или MOEX
    - currency: BYN, RUB, USD, EUR
    - term: up_to_1, 1_3, 3_5, 5_plus
    - status: attractive, neutral, review, high_risk
    - cursor: курсор пагинации
    - limit: размер страницы (макс. 100)
    """
    from fastapi.responses import JSONResponse

    resp = BondListResponse(
        as_of=datetime.now(UTC).isoformat(),
        data_status="ok",
        items=[],
        next_cursor=None,
    )
    return JSONResponse(
        content=resp.model_dump(),
        headers=response_headers(),
    )


@router.get(
    "/bonds/{instrument_id}",
    response_model=BondDetailResponse,
    summary="Детальная аналитика облигации",
)
async def get_bond_detail(
    instrument_id: str,
    _auth: dict = Depends(verify_sso_token),
):
    """Получить детальный анализ облигации с объяснением Score."""
    from fastapi.responses import JSONResponse

    resp = BondDetailResponse(
        instrument=BondItemDTO(
            instrument_id=instrument_id,
            name="Unknown",
            issuer=None,
            currency="BYN",
        ),
        explanation=[],
        quality={"status": "ok", "messages": []},
        disclaimer="Аналитический модуль не даёт инвестиционных рекомендаций.",
    )
    return JSONResponse(
        content=resp.model_dump(),
        headers=response_headers(),
    )


@router.post(
    "/portfolio-impact",
    response_model=PortfolioImpactResponse,
    summary="Оценка влияния на портфель",
)
async def portfolio_impact(
    body: PortfolioImpactRequest,
    _auth: dict = Depends(verify_sso_token),
):
    """Рассчитать эффект добавления позиции в портфель."""
    from fastapi.responses import JSONResponse

    resp = PortfolioImpactResponse(
        before={"expected_yield_pct": 0.0, "duration_years": 0.0},
        after={"expected_yield_pct": 0.0, "duration_years": 0.0},
        deltas={"expected_yield_pp": 0.0, "duration_years": 0.0},
        constraints=[],
        summary="",
        disclaimer="Демонстрационный расчёт. Не является инвестиционной рекомендацией.",
    )
    return JSONResponse(
        content=resp.model_dump(),
        headers=response_headers(),
    )


@router.post(
    "/alerts",
    response_model=AlertResponse,
    summary="Создание алерта",
)
async def create_alert(
    body: AlertRequest,
    request: Request,
    _auth: dict = Depends(verify_sso_token),
):
    """Создать алерт на инструмент (идемпотентный)."""
    from fastapi.responses import JSONResponse

    req_id = make_request_id(request)
    resp = AlertResponse(
        alert_id=str(uuid4()),
        status="created",
        created_at=datetime.now(UTC).isoformat(),
    )
    return JSONResponse(
        content=resp.model_dump(),
        headers={**response_headers(), "X-Request-Id": req_id},
    )
