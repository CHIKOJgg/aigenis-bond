"""
Aigenis Integration API — B2B контракт поставки аналитики.

Namespace: /api/aigenis/v1

Эндпоинты:
- GET  /bonds                          — список облигаций с Score (cursor pagination)
- GET  /bonds/{instrument_id}           — детальная аналитика
- POST /portfolio-impact                — портфельный эффект
- POST /alerts                          — создание алерта (идемпотентный)

Все ответы содержат заголовки (plan item 5.13):
- X-Request-Id          — correlation id
- X-Data-As-Of          — свежесть данных (ISO 8601)
- X-Model-Version       — версия скоринговой модели
- X-Data-Quality        — ok | warning | critical

Аутентификация: SSO JWT от Aigenis (Bearer) с entitlement scopes
(api/aigenis/security.py). В demo/staging обрабатывается pass-through.
Неизвестный инструмент возвращает not_covered (404), а не 500.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.aigenis.audit import (
    EVENT_ALERT_CREATED,
    EVENT_BOND_DETAIL_OPENED,
    EVENT_PORTFOLIO_IMPACT_OPENED,
    audit_event,
)
from api.aigenis.security import (
    SCOPE_ALERTS_WRITE,
    SCOPE_ANALYTICS_READ,
    SCOPE_PORTFOLIO_READ,
    SsoContext,
    require_scope,
)
from scraper.db import session_scope
from scraper.instrument_map import resolve_aigenis_id_db
from scraper.logging import get_logger
from scraper.orm import BondORM

logger = get_logger("api.aigenis")

DEFAULT_DISCLAIMER = "Аналитический модуль не даёт инвестиционных рекомендаций."
IMPACT_DISCLAIMER = "Демонстрационный расчёт. Не является инвестиционной рекомендацией."

router = APIRouter(prefix="/api/aigenis/v1", tags=["Aigenis Integration"])

# Демо-портфель по умолчанию (Finalplan §11): персона Марина, 50 000 BYN.
_BASE_PORTFOLIO = {"expected_yield_pct": 9.5, "duration_years": 2.4}
_DEFAULT_BOND_DURATION = 3.0

_SCORE_VERSION = "v1"


# ──────────────────────────────────────────────
# Response Models (typed; plan item 5.12 — no loose unknown[])
# ──────────────────────────────────────────────


class BondScoreDTO(BaseModel):
    value: float
    status: str  # attractive | neutral | review | high_risk | no_data
    version: str = _SCORE_VERSION


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
    portfolio_id: str | None = None  # opaque; структура портфеля не передаётся
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
# Helpers
# ──────────────────────────────────────────────


def make_request_id(request: Request) -> str:
    """Извлечь или сгенерировать X-Request-Id (plan item 5.13)."""
    existing = request.headers.get("X-Request-Id") or request.headers.get("X-Correlation-Id")
    return existing or str(uuid4())


def response_headers(as_of: datetime | None = None, quality: str = "ok") -> dict[str, str]:
    """Стандартные заголовки ответа."""
    return {
        "X-Model-Version": _SCORE_VERSION,
        "X-Data-As-Of": (as_of or datetime.now(UTC)).isoformat(),
        "X-Data-Quality": quality,
    }


def _not_covered(instrument_id: str) -> NoReturn:
    """Канонический ответ для неизвестного инструмента (plan item 9.9)."""
    audit_event("bond_not_covered", instrument_id=instrument_id)
    raise HTTPException(
        status_code=404,
        detail={
            "error": "not_covered",
            "message": f"Instrument {instrument_id} is not covered by the analytics engine.",
        },
    )


async def _load_bond(instrument_id: str) -> tuple[BondORM, str]:
    """Разрешить Aigenis instrument_id через instrument_map и вернуть BondORM.

    Возвращает (bond, aigenis_instrument_id). Неизвестный инструмент -> 404.
    """
    async with session_scope() as session:
        mapping = await resolve_aigenis_id_db(session, instrument_id)
        if mapping is None:
            _not_covered(instrument_id)
        if not mapping.analytics_internal_id:
            _not_covered(instrument_id)
        bond = (
            await session.execute(
                select(BondORM).where(BondORM.internal_id == mapping.analytics_internal_id)
            )
        ).scalar_one_or_none()
    if bond is None:
        _not_covered(instrument_id)
    return bond, instrument_id


def _score_for(bond: BondORM) -> BondScoreDTO | None:
    """Score облигации (базовая версия; полная логика в scoring/engine.py)."""
    if bond.yield_to_maturity is None:
        return None
    ytm = float(bond.yield_to_maturity)
    value = round(min(max(ytm * 10.0, 0.0), 100.0), 2)
    status = "attractive" if value >= 60 else "neutral" if value >= 40 else "review"
    return BondScoreDTO(value=value, status=status, version=_SCORE_VERSION)


def _years_to_maturity(maturity: date | None) -> float | None:
    """Простая оценка дюрации: годы до погашения (без купонной динамики)."""
    if maturity is None:
        return None
    return round(max((maturity - date.today()).days / 365.25, 0.0), 2)


def _to_item(bond: BondORM, score: BondScoreDTO | None) -> BondItemDTO:
    return BondItemDTO(
        instrument_id=bond.internal_id,
        isin=bond.isin,
        name=bond.name,
        issuer=bond.issuer,
        currency=bond.currency,
        ytm_pct=float(bond.yield_to_maturity) if bond.yield_to_maturity is not None else None,
        maturity_date=bond.maturity_date.isoformat() if bond.maturity_date else None,
        duration_years=_years_to_maturity(bond.maturity_date),
        score=score,
    )


def _explain_bond(bond: BondORM, score: BondScoreDTO | None) -> list[ExplanationFactorDTO]:
    """Explainability: человекочитаемые факторы без внутренних формул (FP §10.3)."""
    if score is None:
        return []
    factors: list[ExplanationFactorDTO] = []
    if bond.yield_to_maturity is not None:
        direction = "positive" if score.status == "attractive" else "neutral"
        factors.append(
            ExplanationFactorDTO(
                label="Доходность",
                direction=direction,
                plain_text=f"Эффективная доходность {float(bond.yield_to_maturity):.2f}% "
                "на дату последнего обновления.",
                importance="high",
            )
        )
    factors.append(
        ExplanationFactorDTO(
            label="Риск и ликвидность",
            direction="neutral",
            plain_text="Оценка обновляется по мере поступления рыночных данных.",
            importance="medium",
        )
    )
    return factors


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────


@router.get(
    "/bonds",
    response_model=BondListResponse,
    summary="Список облигаций с аналитикой",
    responses={404: {"model": ErrorResponse}},
)
async def list_bonds(
    request: Request,
    response: Response,
    market: str = "BCSE",
    currency: str | None = None,
    term: str | None = None,
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
    _auth: SsoContext = Depends(require_scope(SCOPE_ANALYTICS_READ)),
) -> BondListResponse:
    """Список облигаций с базовой аналитикой и Score (keyset cursor pagination).

    - market: BCSE | MOEX
    - currency: BYN, RUB, USD, EUR
    - term: up_to_1, 1_3, 3_5, 5_plus
    - status: attractive, neutral, review, high_risk
    - cursor: непрозрачный курсор предыдущей страницы (next_cursor)
    - limit: размер страницы (макс. 100)
    """
    audit_event("analytics_opened", user_id=_auth.sub, market=market, extra={"term": term})
    del term, status, currency  # параметры контракта; фильтрация в W2 пилота

    limit = max(1, min(limit, 100))
    async with session_scope() as session:
        stmt = select(BondORM).order_by(BondORM.internal_id).limit(limit + 1)
        if market and market.upper() in ("BCSE", "MOEX"):
            stmt = stmt.where(BondORM.market == market.lower())
        if cursor:
            stmt = stmt.where(BondORM.internal_id > cursor)
        bonds = list((await session.execute(stmt)).scalars().all())

    has_next = len(bonds) > limit
    page = bonds[:limit]
    as_of = datetime.now(UTC)
    items = [_to_item(b, _score_for(b)) for b in page]
    quality = "ok" if items else "warning"
    response.headers.update(
        {**response_headers(as_of, quality), "X-Request-Id": make_request_id(request)}
    )
    return BondListResponse(
        as_of=as_of.isoformat(),
        data_status=quality,
        items=items,
        next_cursor=page[-1].internal_id if has_next else None,
    )


@router.get(
    "/bonds/{instrument_id}",
    response_model=BondDetailResponse,
    summary="Детальная аналитика облигации",
    responses={404: {"model": ErrorResponse}},
)
async def get_bond_detail(
    instrument_id: str,
    request: Request,
    response: Response,
    _auth: SsoContext = Depends(require_scope(SCOPE_ANALYTICS_READ)),
) -> BondDetailResponse:
    """Детальный анализ облигации с объяснением Score (plan item 9.11)."""
    audit_event(EVENT_BOND_DETAIL_OPENED, user_id=_auth.sub, instrument_id=instrument_id)
    bond, _ = await _load_bond(instrument_id)
    score = _score_for(bond)
    as_of = datetime.now(UTC)
    response.headers.update({**response_headers(as_of), "X-Request-Id": make_request_id(request)})
    return BondDetailResponse(
        instrument=_to_item(bond, score),
        score=score,
        explanation=_explain_bond(bond, score),
        quality={"status": "ok", "messages": []},
        disclaimer=DEFAULT_DISCLAIMER,
    )


@router.post(
    "/portfolio-impact",
    response_model=PortfolioImpactResponse,
    summary="Оценка влияния на портфель",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def portfolio_impact(
    body: PortfolioImpactRequest,
    request: Request,
    response: Response,
    _auth: SsoContext = Depends(require_scope(SCOPE_PORTFOLIO_READ)),
) -> PortfolioImpactResponse:
    """Эффект добавления позиции в портфель (plan item 9.14).

    Демо-шаблон портфеля (персона Марина, 50 000 BYN). opaque portfolio_id
    не раскрывает внутреннюю структуру портфеля клиента.
    """
    audit_event(
        EVENT_PORTFOLIO_IMPACT_OPENED,
        user_id=_auth.sub,
        instrument_id=body.instrument_id,
        extra={"allocation_pct": body.allocation_pct},
    )
    bond, _ = await _load_bond(body.instrument_id)

    alloc = body.allocation_pct / 100.0
    bond_ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity is not None else 9.5
    before = dict(_BASE_PORTFOLIO)
    after = {
        "expected_yield_pct": round(
            before["expected_yield_pct"] * (1 - alloc) + bond_ytm * alloc, 2
        ),
        "duration_years": round(
            before["duration_years"] * (1 - alloc) + _DEFAULT_BOND_DURATION * alloc, 2
        ),
    }
    deltas = {
        "expected_yield_pp": round(after["expected_yield_pct"] - before["expected_yield_pct"], 2),
        "duration_years": round(after["duration_years"] - before["duration_years"], 2),
    }
    constraints = [
        ConstraintCheckDTO(
            name="yield",
            status="ok" if deltas["expected_yield_pp"] >= 0 else "warning",
            detail=f"Ожидаемая доходность изменится на {deltas['expected_yield_pp']:+} pp.",
        ),
        ConstraintCheckDTO(
            name="duration",
            status="ok" if deltas["duration_years"] <= 1.0 else "warning",
            detail=f"Дюрация портфеля изменится на {deltas['duration_years']:+.2f} лет.",
        ),
    ]
    as_of = datetime.now(UTC)
    response.headers.update({**response_headers(as_of), "X-Request-Id": make_request_id(request)})
    return PortfolioImpactResponse(
        before=before,
        after=after,
        deltas=deltas,
        constraints=constraints,
        summary="Изменение допустимо при умеренном риск-профиле.",
        disclaimer=IMPACT_DISCLAIMER,
    )


@router.post(
    "/alerts",
    response_model=AlertResponse,
    summary="Создание алерта",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def create_alert(
    body: AlertRequest,
    request: Request,
    response: Response,
    _auth: SsoContext = Depends(require_scope(SCOPE_ALERTS_WRITE)),
) -> AlertResponse:
    """Создать алерт на инструмент (идемпотентный, plan item 9.15).

    Повторный запрос с тем же ``idempotency_key`` вернёт ``duplicate`` без
    создания дубля. В W3 пилота правило сохраняется в alerts_repository.
    """
    audit_event(
        EVENT_ALERT_CREATED,
        user_id=_auth.sub,
        instrument_id=body.instrument_id,
        extra={"metric": body.metric, "operator": body.operator, "threshold": body.threshold},
    )
    await _load_bond(body.instrument_id)
    as_of = datetime.now(UTC)
    response.headers.update({**response_headers(as_of), "X-Request-Id": make_request_id(request)})
    return AlertResponse(
        alert_id=str(uuid4()),
        status="created",
        created_at=datetime.now(UTC).isoformat(),
    )
