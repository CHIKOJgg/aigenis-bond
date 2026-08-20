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
from sqlalchemy import func, select

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
from scoring.engine import score_bond
from scoring.explain import explain_score
from scoring.models import BondScore, ScoreBreakdown
from scraper.db import session_scope
from scraper.instrument_map import resolve_aigenis_id_db
from scraper.logging import get_logger
from scraper.orm import BondORM
from scraper.orm.bonds import BondScoreORM
from scraper.orm.users import AlertORM

logger = get_logger("api.aigenis")

DEFAULT_DISCLAIMER = "Аналитический модуль не даёт инвестиционных рекомендаций."
IMPACT_DISCLAIMER = "Демонстрационный расчёт. Не является инвестиционной рекомендацией."

router = APIRouter(prefix="/api/aigenis/v1", tags=["Aigenis Integration"])

# Демо-портфель по умолчанию (Finalplan §11): персона Марина, 50 000 BYN.
_BASE_PORTFOLIO = {"expected_yield_pct": 9.5, "duration_years": 2.4}
_DEFAULT_BOND_DURATION = 3.0

_SCORE_VERSION = "v1"

# Tier (S/A/B/C/D) -> contract status vocabulary, kept identical to the demo
# surface (api/demo.py _TIER_STATUS) so the B2B feed and the demo never disagree.
_TIER_STATUS = {
    "S": "attractive",
    "A": "attractive",
    "B": "neutral",
    "C": "review",
    "D": "high_risk",
}

_TERM_BUCKETS = {"up_to_1": (0.0, 1.0), "1_3": (1.0, 3.0), "3_5": (3.0, 5.0), "5_plus": (5.0, 1e9)}


def _score_dto(bond: BondORM, score_orm: BondScoreORM | None) -> BondScoreDTO | None:
    """Real Reward/Risk Score, sourced from the precomputed ``bond_scores`` table.

    Falls back to the engine itself only when a precomputed row is missing, so
    the B2B contract always returns the same score the demo computes (never the
    obsolete ``YTM * 10`` heuristic).
    """
    if score_orm is not None and score_orm.score is not None:
        tier = score_orm.tier or "D"
        return BondScoreDTO(
            value=round(float(score_orm.score), 2),
            status=_TIER_STATUS.get(tier, "review"),
            version=_SCORE_VERSION,
        )
    if bond.yield_to_maturity is None:
        return None
    try:
        bs = score_bond(
            internal_id=bond.internal_id,
            yield_to_maturity=bond.yield_to_maturity,
            currency=bond.currency,
            maturity_date=bond.maturity_date,
            status=bond.status or "unknown",
            issuer=bond.issuer,
            price=bond.price,
            nominal=bond.nominal,
            coupon_rate=bond.coupon_rate,
            indexation_currency=bond.indexation_currency,
            market=(bond.market or "bcse"),
        )
        return BondScoreDTO(
            value=round(float(bs.score), 2),
            status=_TIER_STATUS.get(bs.tier, "review"),
            version=_SCORE_VERSION,
        )
    except Exception:
        logger.warning("aigenis_score_compute_failed", internal_id=bond.internal_id)
        return None


def _real_as_of(bonds: list[BondORM]) -> datetime | None:
    """Honest data-freshness stamp: newest ``fetched_at`` among the rows served."""
    stamps = [b.fetched_at for b in bonds if getattr(b, "fetched_at", None) is not None]
    return max(stamps) if stamps else None


def _quality_from_asof(as_of: datetime | None) -> str:
    """Real data-quality signal based on actual data age (not a constant 'ok')."""
    if as_of is None:
        return "warning"
    now = datetime.now(UTC)
    if as_of.tzinfo is None:
        # SQLite round-trips DateTime(timezone=True) without an offset.
        as_of = as_of.replace(tzinfo=UTC)
    age_h = (now - as_of).total_seconds() / 3600.0
    if age_h > 72:
        return "critical"
    if age_h > 36:
        return "warning"
    return "ok"


def _term_years(maturity_date: date | None) -> float | None:
    if maturity_date is None:
        return None
    return max((maturity_date - date.today()).days / 365.25, 0.0)


def _term_bucket(maturity_date: date | None) -> str | None:
    y = _term_years(maturity_date)
    if y is None:
        return None
    if y < 1:
        return "up_to_1"
    if y < 3:
        return "1_3"
    if y < 5:
        return "3_5"
    return "5_plus"


def _explain_factors(
    bond: BondORM, score_orm: BondScoreORM | None, score_dto: BondScoreDTO | None
) -> list[ExplanationFactorDTO]:
    """Engine-derived, human-readable explainability (replaces the placeholder text)."""
    if score_orm is None or score_dto is None or not score_orm.breakdown:
        return []
    try:
        bs = BondScore(
            internal_id=bond.internal_id,
            score=score_dto.value,
            breakdown=ScoreBreakdown(**score_orm.breakdown),
            computed_at=score_orm.computed_at,
        )
        explained = explain_score(
            bs,
            currency=bond.currency,
            ytm_pct=float(bond.yield_to_maturity) if bond.yield_to_maturity is not None else None,
            coupon_pct=float(bond.coupon_rate) if bond.coupon_rate is not None else None,
        )
        return [
            ExplanationFactorDTO(
                label=f.label,
                direction=f.impact,
                plain_text=f.detail,
                importance="high" if abs(f.points) >= 10 else "medium",
            )
            for f in explained.factors
        ]
    except Exception:
        logger.warning("aigenis_explain_failed", internal_id=bond.internal_id)
        return []


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

    The list endpoint returns ``instrument_id == internal_id``, so when the
    instrument map has no entry we fall back to a direct primary-key lookup.
    This keeps ``GET /bonds`` and ``GET /bonds/{id}`` consistent (no 404s for
    instruments the list just returned).
    """
    async with session_scope() as session:
        mapping = await resolve_aigenis_id_db(session, instrument_id)
        if mapping is not None and mapping.analytics_internal_id:
            bond = (
                await session.execute(
                    select(BondORM).where(BondORM.internal_id == mapping.analytics_internal_id)
                )
            ).scalar_one_or_none()
            if bond is not None:
                return bond, instrument_id
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == instrument_id))
        ).scalar_one_or_none()
    if bond is None:
        _not_covered(instrument_id)
    return bond, instrument_id


def _bond_duration_years(bond: Any) -> float | None:
    """Modified duration of a bond (years), the standard price-sensitivity measure.

    Falls back to time-to-maturity only when the coupon schedule / yield needed
    to compute a real duration is unavailable. Duration is independent of the
    nominal (it is a ratio), so a missing nominal does not bias the result.
    """
    if bond.maturity_date is None:
        return None
    try:
        from decimal import Decimal

        from desk.duration import modified_duration

        ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity is not None else 0.0
        coupon = float(bond.coupon_rate) if bond.coupon_rate is not None else ytm
        freq = int(bond.coupon_frequency or 2)
        dur = modified_duration(
            nominal=bond.nominal or Decimal("1000"),
            coupon_rate_pct=coupon,
            coupon_frequency=freq,
            ytm_pct=ytm,
            maturity=bond.maturity_date,
            ref=date.today(),
            issue_date=getattr(bond, "start_date", None),
        )
        return round(dur, 2)
    except Exception:
        return round(max((bond.maturity_date - date.today()).days / 365.25, 0.0), 2)


def _to_item(bond: BondORM, score: BondScoreDTO | None) -> BondItemDTO:
    return BondItemDTO(
        instrument_id=bond.internal_id,
        isin=bond.isin,
        name=bond.name,
        issuer=bond.issuer,
        currency=bond.currency,
        ytm_pct=float(bond.yield_to_maturity) if bond.yield_to_maturity is not None else None,
        maturity_date=bond.maturity_date.isoformat() if bond.maturity_date else None,
        duration_years=_bond_duration_years(bond),
        score=score,
    )


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

    if term is not None and term not in _TERM_BUCKETS:
        term = None
    if status is not None and status not in _TIER_STATUS.values():
        status = None
    limit = max(1, min(limit, 100))

    async with session_scope() as session:
        collected: list[tuple[BondORM, BondScoreORM | None]] = []
        batch_cursor = cursor
        exhausted = True
        has_more = False
        for _ in range(20):  # safety bound on pagination batches
            # Select BondORM only; the joined Score ORM entity cannot be cleanly
            # unpacked from a flattened result row, so scores are fetched per
            # batch below.
            stmt = (
                select(BondORM)
                .where(func.lower(BondORM.market) == market.lower())
                .order_by(BondORM.internal_id)
                .limit(200)
            )
            if currency:
                stmt = stmt.where(BondORM.currency == currency.upper())
            if batch_cursor:
                stmt = stmt.where(BondORM.internal_id > batch_cursor)
            bonds = list((await session.execute(stmt)).scalars().all())
            if not bonds:
                break
            ids = [b.internal_id for b in bonds]
            sres = await session.execute(
                select(BondScoreORM).where(BondScoreORM.internal_id.in_(ids))
            )
            smap = {so.internal_id: so for so in sres.scalars().all()}
            for bond in bonds:
                so = smap.get(bond.internal_id)
                sd = _score_dto(bond, so)
                if status and (sd is None or sd.status != status):
                    continue
                if term and _term_bucket(bond.maturity_date) != term:
                    continue
                collected.append((bond, so))
                if len(collected) >= limit:
                    has_more = True
                    break
            batch_cursor = bonds[-1].internal_id
            if len(bonds) < 200:
                exhausted = True
                break
            exhausted = False

    page = collected[:limit]
    has_next = has_more or not exhausted
    as_of = _real_as_of([b for b, _ in page])
    quality = _quality_from_asof(as_of)
    items = [_to_item(b, _score_dto(b, so)) for b, so in page]
    response.headers.update(
        {**response_headers(as_of, quality), "X-Request-Id": make_request_id(request)}
    )
    return BondListResponse(
        as_of=as_of.isoformat() if as_of else datetime.now(UTC).isoformat(),
        data_status=quality,
        items=items,
        next_cursor=page[-1][0].internal_id if has_next else None,
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
    async with session_scope() as session:
        score_orm = (
            await session.execute(
                select(BondScoreORM).where(BondScoreORM.internal_id == bond.internal_id)
            )
        ).scalar_one_or_none()
    score = _score_dto(bond, score_orm)
    explanation = _explain_factors(bond, score_orm, score)
    as_of = bond.fetched_at
    quality = _quality_from_asof(as_of) if score is not None else "warning"
    response.headers.update(
        {**response_headers(as_of, quality), "X-Request-Id": make_request_id(request)}
    )
    return BondDetailResponse(
        instrument=_to_item(bond, score),
        score=score,
        explanation=explanation,
        quality={"status": quality, "messages": []},
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
    bond_duration = _bond_duration_years(bond) or _DEFAULT_BOND_DURATION
    before = dict(_BASE_PORTFOLIO)
    after = {
        "expected_yield_pct": round(
            before["expected_yield_pct"] * (1 - alloc) + bond_ytm * alloc, 2
        ),
        "duration_years": round(before["duration_years"] * (1 - alloc) + bond_duration * alloc, 2),
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
    as_of = bond.fetched_at
    response.headers.update(
        {
            **response_headers(as_of, _quality_from_asof(as_of)),
            "X-Request-Id": make_request_id(request),
        }
    )
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

    Повторный запрос с тем же ``idempotency_key`` возвращает существующий алерт
    со статусом ``duplicate`` без создания дубля. Правило сохраняется в таблицу
    ``alerts`` (AlertORM).
    """
    audit_event(
        EVENT_ALERT_CREATED,
        user_id=_auth.sub,
        instrument_id=body.instrument_id,
        extra={"metric": body.metric, "operator": body.operator, "threshold": body.threshold},
    )
    bond, _ = await _load_bond(body.instrument_id)

    async with session_scope() as session:
        if body.idempotency_key:
            existing = (
                await session.execute(
                    select(AlertORM).where(AlertORM.dedup_key == body.idempotency_key)
                )
            ).scalar_one_or_none()
            if existing is not None:
                response.headers.update(
                    {**response_headers(None), "X-Request-Id": make_request_id(request)}
                )
                return AlertResponse(
                    alert_id=existing.dedup_key,
                    status="duplicate",
                    created_at=existing.created_at.isoformat(),
                )
        alert = AlertORM(
            user_id=None,
            kind=f"signal_{body.metric}",
            title=f"Alert {body.metric} {body.operator} {body.threshold}",
            message=f"{bond.name or body.instrument_id}: {body.metric} "
            f"{body.operator} {body.threshold}",
            internal_id=bond.internal_id,
            payload={
                "metric": body.metric,
                "operator": body.operator,
                "threshold": body.threshold,
                "instrument_id": body.instrument_id,
            },
            dedup_key=body.idempotency_key,
        )
        session.add(alert)
        await session.flush()
        alert_id = str(alert.id)
        created_at = alert.created_at

    response.headers.update({**response_headers(None), "X-Request-Id": make_request_id(request)})
    return AlertResponse(
        alert_id=alert_id,
        status="created",
        created_at=created_at.isoformat(),
    )
