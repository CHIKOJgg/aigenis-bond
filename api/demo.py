"""Demo blueprint — live read-only public surface for `/demo/*`.

Market responses are read from the production database populated by the
Aigenis provider; no write operations, payments or Telegram actions are exposed.
Guarded by DEMO_DISABLE_SIDE_EFFECTS so the blueprint is a safe showcase for
pre-sale and pilot presentations.

Phase 1 (item 1.13) — deterministic ``POST /api/v1/demo/portfolio-impact``.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select

from desk.ytm import to_price_pct, ytm_from_price
from scraper.db import session_scope
from scraper.logging import get_logger
from scraper.orm import BondHistoryORM, BondORM, BondScoreORM

logger = get_logger("api.demo")

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])

_TIER_STATUS = {
    "S": "attractive",
    "A": "attractive",
    "B": "neutral",
    "C": "review",
    "D": "high_risk",
}

_STRATEGY_RU = {
    "Conservative": "Консервативная",
    "Balanced": "Сбалансированная",
    "Aggressive": "Агрессивная",
    "Carry Trade": "Carry Trade",
    "Dollarization": "Долларизация",
    "Maximum Reward/Risk": "Макс. доходность/риск",
    "Metals++": "Металлы++",
}


def _issuer_risk_payload(
    issuer: str | None,
    *,
    is_government: bool,
    credit_component: float | None,
    status: str,
) -> dict[str, Any]:
    """Expose the engine's explainable issuer-risk view, not a credit rating."""
    from scoring.engine import _classify_issuer

    credit = credit_component if credit_component is not None else -2.0
    tier = _classify_issuer(issuer)

    if status in {"defaulted", "delisted"}:
        score, level = 15.0, "Критический"
        basis = "Статус выпуска указывает на дефолт или делистинг"
    elif is_government or tier == "sovereign" or credit >= 10:
        score, level = 90.0, "Очень низкий"
        basis = "Суверенный / государственный профиль эмитента"
    elif tier == "sub_sovereign" or credit >= 8:
        score, level = 82.0, "Очень низкий"
        basis = "Субсуверенный / муниципальный профиль эмитента"
    elif tier == "state_corp" or credit >= 6:
        score, level = 75.0, "Низкий"
        basis = "Государственная корпорация с высокой господдержкой"
    elif tier == "bank_systemic" or credit >= 4:
        score, level = 68.0, "Умеренно низкий"
        basis = "Системно значимый банк"
    elif tier == "bank" or credit >= 2:
        score, level = 62.0, "Умеренно низкий"
        basis = "Коммерческий банковский эмитент"
    elif tier == "corp" or credit >= 0:
        score, level = 56.0, "Умеренный"
        basis = "Стандартный корпоративный кредитный профиль"
    else:
        score, level = 36.0, "Высокий"
        basis = "Отрицательный кредитный компонент корпоративного эмитента"

    return {
        "score": score,
        "level": level,
        "basis": basis,
        "credit_component": round(credit, 2),
        "method": "Reward/Risk engine: issuer classification + credit component + status",
    }


def _bond_analytics(bond: BondORM) -> dict[str, Any]:
    """Derive YTM, duration and Reward/Risk Score v4 for one BCSE bond.

    The BCSE feed only ships reference fields (price, coupon, maturity), so the
    missing analytics are computed here: YTM from price/nominal/coupon/maturity,
    Macaulay duration from real future cash flows, and the score from the
    production scoring engine. If there is no market anchor (price or YTM),
    the score stays None so the UI can honestly show "недостаточно данных".
    """
    ref = date.today()
    ytm: float | None = None
    computed_ytm = False
    if bond.yield_to_maturity is not None and float(bond.yield_to_maturity) > 0:
        ytm = float(bond.yield_to_maturity)
    price_pct = to_price_pct(bond.price, bond.nominal)
    if (
        ytm is None
        and price_pct is not None
        and bond.coupon_rate is not None
        and bond.maturity_date is not None
    ):
        try:
            solved = ytm_from_price(
                price_pct=price_pct,
                coupon_rate_pct=float(bond.coupon_rate),
                coupon_frequency=int(bond.coupon_frequency or 2),
                maturity=bond.maturity_date,
                asof=ref,
            )
        except Exception:
            solved = None
        if solved is not None and solved > 0:
            ytm = round(solved, 4)
            computed_ytm = True

    duration_years: float | None = None
    if bond.maturity_date is not None:
        raw_dur: float | None = None
        if ytm is not None:
            try:
                from desk.duration import macaulay_duration

                raw_dur = macaulay_duration(
                    nominal=bond.nominal or Decimal("1000"),
                    coupon_rate_pct=(
                        float(bond.coupon_rate) if bond.coupon_rate is not None else ytm
                    ),
                    coupon_frequency=int(bond.coupon_frequency or 2),
                    ytm_pct=ytm,
                    maturity=bond.maturity_date,
                    ref=ref,
                    issue_date=bond.start_date,
                )
            except Exception:
                logger.warning(
                    "demo_duration_failed",
                    internal_id=bond.internal_id,
                    error="duration calc failed",
                )
                raw_dur = None
        if raw_dur is None:
            raw_dur = max((bond.maturity_date - ref).days / 365.25, 0.0)
        duration_years = round(raw_dur, 2)

    score_payload: dict[str, Any] | None = None
    has_price = price_pct is not None
    if has_price or ytm is not None:
        try:
            from scoring.engine import score_bond

            bs = score_bond(
                internal_id=bond.internal_id,
                yield_to_maturity=ytm,
                currency=bond.currency,
                maturity_date=bond.maturity_date,
                status=str(bond.status or "active"),
                issuer=bond.issuer,
                price=price_pct,
                nominal=Decimal("100"),
                coupon_rate=float(bond.coupon_rate) if bond.coupon_rate is not None else None,
                market=str(bond.market or "bcse"),
            )
        except Exception:
            bs = None
        if bs is not None:
            tier = bs.tier
            explanation: dict[str, Any] | None = None
            try:
                from scoring.explain import explain_score

                expl = explain_score(
                    bs,
                    currency=bond.currency,
                    ytm_pct=ytm,
                    coupon_pct=(float(bond.coupon_rate) if bond.coupon_rate is not None else None),
                )
                explanation = {
                    "verdict": expl.verdict,
                    "summary": expl.summary,
                    "strengths": expl.strengths,
                    "weaknesses": expl.weaknesses,
                    "factors": [f.as_dict() for f in expl.factors],
                }
            except Exception:
                logger.warning(
                    "demo_explain_failed",
                    internal_id=bond.internal_id,
                    error="explain failed",
                )
            score_payload = {
                "score": round(bs.score, 2),
                "tier": tier,
                "score_status": _TIER_STATUS.get(tier, "no_data"),
                "computed_at": bs.computed_at.isoformat(),
                "breakdown": bs.breakdown.model_dump(),
                "explanation": explanation,
            }

    # Distressed-debt marker: price < 80% of face with YTM > 30% means the
    # market prices near-default, so the quoted yield is not an opportunity —
    # it is a risk signal (the scoring engine also caps/penalizes it).
    distressed = price_pct is not None and ytm is not None and price_pct < 80.0 and ytm > 30.0

    accrued_val: float | None = None
    if bond.coupon_rate is not None and bond.maturity_date is not None:
        try:
            from desk.cashflow import accrued_interest

            accrued_val = accrued_interest(
                coupon_rate_pct=float(bond.coupon_rate),
                coupon_frequency=int(bond.coupon_frequency or 2),
                issue_date=bond.start_date,
                maturity_date=bond.maturity_date,
                asof=ref,
                face=float(bond.nominal) if bond.nominal else 100.0,
            )
        except Exception:
            pass

    return {
        "yield_to_maturity": ytm,
        "computed_ytm": computed_ytm,
        "distressed": distressed,
        "duration_years": duration_years,
        "score": score_payload,
        "accrued_interest": accrued_val,
    }


DATA_ROOT = Path(__file__).resolve().parents[1] / "demo-data" / "v1"


def _fast_bond_payload(bond: BondORM, score_row: BondScoreORM | None) -> dict[str, Any]:
    """Lightweight payload for the list endpoint — reads pre-computed scores."""
    ref = date.today()
    ytm = (
        float(bond.yield_to_maturity)
        if bond.yield_to_maturity and float(bond.yield_to_maturity) > 0
        else None
    )
    price_pct = to_price_pct(bond.price, bond.nominal)
    computed_ytm = False
    if (
        ytm is None
        and price_pct is not None
        and bond.coupon_rate is not None
        and bond.maturity_date is not None
    ):
        try:
            solved = ytm_from_price(
                price_pct,
                float(bond.coupon_rate),
                int(bond.coupon_frequency or 2),
                bond.maturity_date,
                ref,
            )
            if solved and solved > 0:
                ytm = round(solved, 4)
                computed_ytm = True
        except Exception:
            pass

    duration_years = None
    if bond.maturity_date is not None:
        try:
            from desk.duration import macaulay_duration

            raw_dur = macaulay_duration(
                nominal=bond.nominal or Decimal("1000"),
                coupon_rate_pct=float(bond.coupon_rate)
                if bond.coupon_rate is not None
                else (ytm or 0),
                coupon_frequency=int(bond.coupon_frequency or 2),
                ytm_pct=ytm or 0,
                maturity=bond.maturity_date,
                ref=ref,
                issue_date=bond.start_date,
            )
            duration_years = round(raw_dur, 2)
        except Exception:
            duration_years = round(max((bond.maturity_date - ref).days / 365.25, 0.0), 2)

    accrued_val: float | None = None
    if bond.coupon_rate is not None and bond.maturity_date is not None:
        try:
            from desk.cashflow import accrued_interest

            accrued_val = accrued_interest(
                coupon_rate_pct=float(bond.coupon_rate),
                coupon_frequency=int(bond.coupon_frequency or 2),
                issue_date=bond.start_date,
                maturity_date=bond.maturity_date,
                asof=ref,
                face=float(bond.nominal) if bond.nominal else 100.0,
            )
        except Exception:
            pass

    distressed = price_pct is not None and ytm is not None and price_pct < 80.0 and ytm > 30.0

    # Быстрый путь: предвычисленный score из bond_scores (никаких вызовов
    # тяжёлого scoring-движка на каждый бонд списка). Explanation не хранится
    # в bond_scores — UI подставляет фикстурное или считает в карточке.
    score_payload = None
    explanation = None
    if score_row is not None:
        try:
            score_payload = {
                "score": round(float(score_row.score), 2),
                "tier": score_row.tier,
                "score_status": _TIER_STATUS.get(score_row.tier or "", "no_data"),
                "computed_at": score_row.computed_at.isoformat(),
                "breakdown": score_row.breakdown,
                "explanation": None,
            }
        except Exception:
            score_payload = None
    if score_payload is None and (price_pct is not None or ytm is not None):
        try:
            from scoring.engine import score_bond
            from scoring.explain import explain_score

            bs = score_bond(
                internal_id=bond.internal_id,
                yield_to_maturity=ytm,
                currency=bond.currency,
                maturity_date=bond.maturity_date,
                status=str(bond.status or "active"),
                issuer=bond.issuer,
                price=price_pct,
                nominal=Decimal("100"),
                coupon_rate=float(bond.coupon_rate) if bond.coupon_rate is not None else None,
                market=str(bond.market or "bcse"),
            )
            expl = explain_score(
                bs,
                currency=bond.currency,
                ytm_pct=ytm,
                coupon_pct=float(bond.coupon_rate) if bond.coupon_rate is not None else None,
            )
            explanation = {
                "verdict": expl.verdict,
                "summary": expl.summary,
                "strengths": expl.strengths,
                "weaknesses": expl.weaknesses,
                "factors": [f.as_dict() for f in expl.factors],
            }
            score_payload = {
                "score": round(bs.score, 2),
                "tier": bs.tier,
                "score_status": _TIER_STATUS.get(bs.tier or "", "no_data"),
                "computed_at": bs.computed_at.isoformat(),
                "breakdown": bs.breakdown.model_dump(),
                "explanation": explanation,
            }
        except Exception:
            score_payload = None
            explanation = None

    score_breakdown = score_payload["breakdown"] if score_payload else {}
    return {
        "internal_id": bond.internal_id,
        "isin": bond.isin,
        "name": bond.name,
        "issuer": bond.issuer,
        "issuer_logo": bond.issuer_logo,
        "currency": bond.currency,
        "nominal": float(bond.nominal) if bond.nominal is not None else None,
        "coupon_rate": float(bond.coupon_rate) if bond.coupon_rate is not None else None,
        "coupon_frequency": bond.coupon_frequency,
        "maturity_date": bond.maturity_date.isoformat() if bond.maturity_date else None,
        "price": float(bond.price) if bond.price is not None else None,
        "yield_to_maturity": ytm,
        "computed_ytm": computed_ytm,
        "distressed": distressed,
        "duration_years": duration_years,
        "score": score_payload["score"] if score_payload else None,
        "tier": score_payload["tier"] if score_payload else None,
        "score_status": score_payload["score_status"] if score_payload else None,
        "breakdown": score_payload["breakdown"] if score_payload else None,
        "issuer_risk": _issuer_risk_payload(
            bond.issuer,
            is_government=bool(bond.is_government),
            credit_component=score_breakdown.get("credit_risk_component"),
            status=str(bond.status or "unknown"),
        ),
        "explanation": explanation,
        "market": bond.market,
        "status": bond.status,
        "is_government": bool(bond.is_government),
        "in_stock": bond.in_stock,
        "guarantor": bond.guarantor,
        "maturity_term_text": bond.maturity_term_text,
        "coupon_description": bond.coupon_description,
        "fetched_at": bond.fetched_at.isoformat() if bond.fetched_at else None,
        "term_days": bond.term_days,
        "accrued_interest": round(accrued_val, 4) if accrued_val is not None else None,
    }


AllocationPct = Literal[5, 10, 15]


class PortfolioImpactRequest(BaseModel):
    bond_id: str = Field(..., description="demo-bond-001..003 from fixtures")
    allocation_pct: AllocationPct = Field(10, description="5, 10 or 15 percent of demo portfolio")


class PortfolioImpactBefore(BaseModel):
    expected_yield_pct: float
    duration_years: float
    concentration_by_issuer: dict[str, float]


class PortfolioImpactAfter(BaseModel):
    expected_yield_pct: float
    duration_years: float
    concentration_by_issuer: dict[str, float]


class PortfolioImpactResponse(BaseModel):
    bond_id: str
    allocation_pct: AllocationPct
    delta_expected_yield_bps: float
    delta_duration_years: float
    concentration_warning: str
    risk_profile_fit: Literal["ok", "borderline", "off"]
    before: PortfolioImpactBefore
    after: PortfolioImpactAfter
    fixtures_version: str


def _bond_payload(bond: BondORM, analytics: dict[str, Any]) -> dict[str, Any]:
    """Sanitized public payload for one bond row (never exposes raw fields)."""
    score = analytics["score"]
    score_breakdown = score["breakdown"] if score else {}
    return {
        "internal_id": bond.internal_id,
        "isin": bond.isin,
        "name": bond.name,
        "issuer": bond.issuer,
        "issuer_logo": bond.issuer_logo,
        "currency": bond.currency,
        "nominal": float(bond.nominal) if bond.nominal is not None else None,
        "coupon_rate": float(bond.coupon_rate) if bond.coupon_rate is not None else None,
        "coupon_frequency": bond.coupon_frequency,
        "maturity_date": bond.maturity_date.isoformat() if bond.maturity_date else None,
        "price": float(bond.price) if bond.price is not None else None,
        # Source YTM if present, otherwise computed from price/coupon/maturity.
        "yield_to_maturity": analytics["yield_to_maturity"],
        "computed_ytm": analytics["computed_ytm"],
        "distressed": analytics["distressed"],
        "duration_years": analytics["duration_years"],
        "score": score["score"] if score else None,
        "tier": score["tier"] if score else None,
        "score_status": score["score_status"] if score else None,
        "breakdown": score["breakdown"] if score else None,
        "issuer_risk": _issuer_risk_payload(
            bond.issuer,
            is_government=bool(bond.is_government),
            credit_component=score_breakdown.get("credit_risk_component"),
            status=str(bond.status or "unknown"),
        ),
        "explanation": score["explanation"] if score else None,
        "market": bond.market,
        "status": bond.status,
        "is_government": bool(bond.is_government),
        "in_stock": bond.in_stock,
        "guarantor": bond.guarantor,
        "maturity_term_text": bond.maturity_term_text,
        "coupon_description": bond.coupon_description,
        "fetched_at": bond.fetched_at.isoformat() if bond.fetched_at else None,
        "term_days": bond.term_days,
        "accrued_interest": round(analytics["accrued_interest"], 4) if analytics.get("accrued_interest") is not None else None,
    }


@router.get("/market-data")
async def live_market_data(
    market: str = Query("bcse", pattern="^(bcse|moex)$"),
    currency: str | None = Query(None, min_length=3, max_length=3),
    limit: int = Query(2000, ge=1, le=2000),
) -> dict[str, Any]:
    """Read-only, sanitized market snapshot for the protected demo UI.

    Uses pre-computed scores from bond_scores table for fast response.
    Returns all active bonds by default (up to 2000).
    """
    async with session_scope() as session:
        stmt = (
            select(BondORM, BondScoreORM)
            .outerjoin(BondScoreORM, BondORM.internal_id == BondScoreORM.internal_id)
            .where(BondORM.market == market)
            .where(BondORM.status == "active")
            .order_by(BondORM.fetched_at.desc(), BondORM.name.asc())
            .limit(limit)
        )
        if currency:
            stmt = stmt.where(BondORM.currency == currency.upper())
        rows = (await session.execute(stmt)).all()

    bonds = []
    for bond, score in rows:
        try:
            bonds.append(_fast_bond_payload(bond, score))
        except Exception:
            logger.warning(
                "demo_bond_payload_failed",
                internal_id=bond.internal_id,
                error="payload build failed, skipped",
            )
    as_of = max((b["fetched_at"] for b in bonds if b["fetched_at"]), default=None)
    return {
        "source": "Aigenis official feed",
        "market": market,
        "currency": currency.upper() if currency else None,
        "as_of": as_of,
        "count": len(bonds),
        "bonds": bonds,
        "disclaimer": "Реальные данные лицензированного источника. Только для защищённого демо; не торговая рекомендация.",
    }


@router.get("/search")
async def demo_search(
    q: str = Query(..., min_length=1, max_length=120),
    market: str | None = Query(None, pattern="^(bcse|moex)$"),
    currency: str | None = Query(None, min_length=3, max_length=3),
    limit: int = Query(20, ge=1, le=50),
) -> dict[str, Any]:
    """Search the whole bond universe (name/ISIN/issuer/id) for the demo UI.

    Returns the same sanitized payload shape as ``/market-data`` so the drawer
    can be opened straight from search results. Read-only, no live calls.
    """
    term = q.strip()
    if not term:
        return {
            "query": q,
            "market": market,
            "count": 0,
            "bonds": [],
            "disclaimer": "Реальные данные лицензированного источника. Только для защищённого демо; не торговая рекомендация.",
        }
    async with session_scope() as session:
        stmt = (
            select(BondORM, BondScoreORM)
            .outerjoin(BondScoreORM, BondORM.internal_id == BondScoreORM.internal_id)
            .where(BondORM.status == "active")
            .where(
                or_(
                    BondORM.name.ilike(f"%{term}%"),
                    BondORM.issuer.ilike(f"%{term}%"),
                    BondORM.isin.ilike(f"%{term}%"),
                    BondORM.internal_id.ilike(f"%{term}%"),
                )
            )
        )
        if market:
            stmt = stmt.where(func.lower(BondORM.market) == market.lower())
        if currency:
            stmt = stmt.where(BondORM.currency == currency.upper())
        rows = (await session.execute(stmt.order_by(BondORM.name.asc()).limit(limit))).all()

    bonds = []
    for bond, score in rows:
        try:
            bonds.append(_fast_bond_payload(bond, score))
        except Exception:
            logger.warning(
                "demo_search_payload_failed",
                internal_id=bond.internal_id,
                error="payload build failed, skipped",
            )
    return {
        "query": term,
        "market": market,
        "count": len(bonds),
        "bonds": bonds,
        "disclaimer": "Реальные данные лицензированного источника. Только для защищённого демо; не торговая рекомендация.",
    }


@router.get("/bond/{internal_id}")
async def demo_bond_detail(internal_id: str) -> dict[str, Any]:
    """Full read-only detail for one bond: analytics + coupon calendar + history.

    History (up to 180 daily rows) is served only when the source has it
    (MOEX backfill); BCSE bonds return an empty list and the UI hides the
    chart instead of showing gaps.
    """
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == internal_id))
        ).scalar_one_or_none()
        if bond is None:
            raise HTTPException(status_code=404, detail=f"Bond {internal_id} not found")
        payload = _bond_payload(bond, _bond_analytics(bond))
        history_rows = (
            (
                await session.execute(
                    select(BondHistoryORM)
                    .where(BondHistoryORM.internal_id == internal_id)
                    .order_by(BondHistoryORM.date.desc())
                    .limit(180)
                )
            )
            .scalars()
            .all()
        )

    payload["history"] = [
        {
            "date": h.date.isoformat(),
            "price": float(h.price) if h.price is not None else None,
            "yield": float(h.yield_) if h.yield_ is not None else None,
        }
        for h in reversed(history_rows)
    ]
    payload["coupon_schedule"] = bond.coupon_schedule or None
    return payload


def _load_manifest() -> dict[str, Any]:
    p = DATA_ROOT / "manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("demo_manifest_read_failed", error=str(exc))
        return {}


def _load_json(name: str) -> dict[str, Any] | list[Any]:
    p = DATA_ROOT / name
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("demo_fixture_read_failed", file=name, error=str(exc))
        return []


def _build_impact(req: PortfolioImpactRequest) -> PortfolioImpactResponse:
    templates = _load_json("portfolio_templates.json")
    persona = _load_json("bonds_bcse.json") + _load_json("bonds_moex.json")

    bond = next(
        (b for b in persona if b.get("internal_id") == req.bond_id),
        None,
    )
    if bond is None:
        raise HTTPException(status_code=404, detail=f"Bond {req.bond_id} not in fixtures")

    template = templates.get("marina_50000_byn") if isinstance(templates, dict) else None
    if not isinstance(template, dict):
        template = {
            "expected_yield_pct": 9.5,
            "duration_years": 2.4,
            "concentration_by_issuer": {"demo": 100.0},
        }

    before_yield = float(template.get("expected_yield_pct", 9.5))
    before_duration = float(template.get("duration_years", 2.4))
    before_concentration = dict(template.get("concentration_by_issuer", {"demo": 100.0}))

    alloc = req.allocation_pct / 100.0
    bond_yield = float(bond.get("yield_to_maturity") or 0)
    bond_duration = float(bond.get("duration_years") or 3.0)

    after_yield = before_yield * (1.0 - alloc) + bond_yield * alloc
    after_duration = before_duration * (1.0 - alloc) + bond_duration * alloc

    issuer_key = str(bond.get("issuer") or req.bond_id)
    after_concentration = dict(before_concentration)
    after_concentration[issuer_key] = after_concentration.get(issuer_key, 0.0) + alloc * 100.0

    delta_yield_bps = round((after_yield - before_yield) * 100.0, 1)
    delta_duration = round(after_duration - before_duration, 2)

    if after_concentration.get(issuer_key, 0.0) > 25.0:
        risk_fit: Literal["ok", "borderline", "off"] = "off"
        concentration_warning = (
            f"Концентрация на эмитента {issuer_key} превысит 25% "
            "— изменение недопустимо при умеренном риск-профиле."
        )
    elif bond_duration > 4.0:
        risk_fit = "borderline"
        concentration_warning = "Дюрация > 4 лет — проверьте горизонт инвестирования."
    else:
        risk_fit = "ok"
        concentration_warning = "Изменение допустимо при умеренном риск-профиле."

    manifest = _load_manifest()
    fixtures_version = str(manifest.get("dataset_version", "v1"))

    return PortfolioImpactResponse(
        bond_id=req.bond_id,
        allocation_pct=req.allocation_pct,
        delta_expected_yield_bps=delta_yield_bps,
        delta_duration_years=delta_duration,
        concentration_warning=concentration_warning,
        risk_profile_fit=risk_fit,
        before=PortfolioImpactBefore(
            expected_yield_pct=round(before_yield, 2),
            duration_years=round(before_duration, 2),
            concentration_by_issuer={k: round(v, 2) for k, v in before_concentration.items()},
        ),
        after=PortfolioImpactAfter(
            expected_yield_pct=round(after_yield, 2),
            duration_years=round(after_duration, 2),
            concentration_by_issuer={k: round(v, 2) for k, v in after_concentration.items()},
        ),
        fixtures_version=fixtures_version,
    )


@router.post("/portfolio-impact", response_model=PortfolioImpactResponse)
async def portfolio_impact(req: PortfolioImpactRequest) -> PortfolioImpactResponse:
    """Детерминированный расчёт влияния бумаги на демо-портфель.

    Safe demo endpoint: never mutates DB, never calls live APIs.
    Side effects (Telegram, emails, payments) are blocked when
    ``DEMO_DISABLE_SIDE_EFFECTS=1`` is set; this endpoint also returns
    a static fixture-derived payload even when the flag is off.
    """
    if os.getenv("AIGENIS_ENV") == "production" and not os.getenv("DEMO_DISABLE_SIDE_EFFECTS"):
        raise HTTPException(
            status_code=403,
            detail="Demo endpoints require DEMO_DISABLE_SIDE_EFFECTS=1 in production.",
        )
    return _build_impact(req)


@router.get("/desk/curve")
async def demo_desk_curve(
    currency: str = Query("BYN"),
    market: str | None = Query(None),
) -> dict[str, Any]:
    """Read-only yield curve data for institutional demo view."""
    async with session_scope() as session:
        stmt = (
            select(BondORM)
            .where(BondORM.currency == currency.upper())
            .where(BondORM.status == "active")
        )
        if market and market.lower() in ("bcse", "moex"):
            stmt = stmt.where(BondORM.market == market.lower())
        bonds = list((await session.execute(stmt)).scalars().all())
        try:
            from desk.yield_curve import curve_from_bonds, fit_nelson_siegel

            yc = curve_from_bonds(bonds)
            params = fit_nelson_siegel(yc.points) if len(yc.points) >= 3 else None
            return {
                "currency": currency.upper(),
                "market": market.upper() if market else "ALL",
                "points": [p.model_dump() for p in yc.points],
                "params": params.model_dump() if params else None,
                "slope": yc.slope(),
            }
        except Exception as exc:
            logger.warning("demo_curve_failed", currency=currency.upper(), error=str(exc))
            return {
                "currency": currency.upper(),
                "market": market.upper() if market else "ALL",
                "points": [],
                "params": None,
                "slope": 0.0,
            }


@router.get("/desk/rv")
async def demo_desk_rv(
    currency: str = Query("BYN"),
    market: str | None = Query(None),
) -> list[dict[str, Any]]:
    """Read-only relative value anomaly signals for demo view."""
    async with session_scope() as session:
        stmt = (
            select(BondORM)
            .where(BondORM.currency == currency.upper())
            .where(BondORM.status == "active")
        )
        if market and market.lower() in ("bcse", "moex"):
            stmt = stmt.where(BondORM.market == market.lower())
        bonds = list((await session.execute(stmt)).scalars().all())
        try:
            from desk.relative_value import relative_value_signals

            signals = relative_value_signals(bonds)
            return [s.model_dump() for s in signals[:50]]
        except Exception as exc:
            logger.warning("demo_rv_failed", currency=currency.upper(), error=str(exc))
            return []


class StressTestRequest(BaseModel):
    scenario: str = Field("parallel_+100bp", description="Stress scenario key")
    market: str = Field("BCSE", description="Market filter: BCSE or MOEX")
    capital: float = Field(50000.0, description="Portfolio value for stress calc")


@router.post("/desk/stress")
async def demo_desk_stress(req: StressTestRequest) -> dict[str, Any]:
    """Engine #2: Institutional Stress Testing & VaR P&L Drawdown Analysis."""
    from desk.stress import PRESET_SCENARIOS, run_stress

    scenario = PRESET_SCENARIOS.get(req.scenario) or PRESET_SCENARIOS["parallel_+100bp"]

    async with session_scope() as session:
        stmt = select(BondORM).where(BondORM.status == "active")
        if req.market and req.market.lower() in ("bcse", "moex"):
            stmt = stmt.where(BondORM.market == req.market.lower())
        bonds = list((await session.execute(stmt)).scalars().all())

        if not bonds:
            stmt_fallback = select(BondORM).where(BondORM.status == "active")
            if req.market and req.market.lower() in ("bcse", "moex"):
                stmt_fallback = stmt_fallback.where(func.lower(BondORM.market) == req.market.lower())
            bonds = list((await session.execute(stmt_fallback)).scalars().all())

        # Облигации неделимы: капитал на позицию превращаем в целое количество
        # бумаг (лот) по реальной цене с учётом НКД, а не в дробную сумму.
        from desk.ytm import to_price_pct

        if req.capital <= 0 or not bonds:
            return {
                "scenario": {
                    "key": req.scenario,
                    "name": scenario.name,
                    "description": scenario.description,
                    "simple_description": scenario.simple_description,
                    "kind": scenario.kind,
                },
                "pnl_amount": 0.0,
                "pnl_pct": 0.0,
                "duration_before": 0.0,
                "duration_after": 0.0,
                "by_tenor": {"1Y": 0.0, "5Y": 0.0, "10Y": 0.0, "30Y": 0.0},
                "by_position": {},
                "positions": [],
                "var_95": 0.0,
                "available_scenarios": [
                    {
                        "key": k,
                        "name": v.name,
                        "description": v.description,
                        "simple_description": v.simple_description,
                    }
                    for k, v in PRESET_SCENARIOS.items()
                ],
            }

        try:
            top_bonds = bonds[:10]
            per_bond_target = req.capital / max(len(top_bonds), 1)
            bonds_with_amounts = []
            position_amounts: list[dict[str, Any]] = []

            for b in top_bonds:
                nom = float(b.nominal) if b.nominal else 100.0
                price_pct = to_price_pct(b.price, nom) if b.price is not None else 100.0
                price_pct = price_pct if price_pct is not None and price_pct > 0 else 100.0
                price_money = (price_pct / 100.0) * nom if nom > 0 else price_pct

                accrued = 0.0
                if b.coupon_rate is not None and b.maturity_date is not None:
                    try:
                        from desk.cashflow import accrued_interest

                        accrued = accrued_interest(
                            coupon_rate_pct=float(b.coupon_rate),
                            coupon_frequency=int(b.coupon_frequency or 2),
                            issue_date=b.start_date,
                            maturity_date=b.maturity_date,
                            asof=date.today(),
                            face=nom,
                        )
                    except Exception:
                        pass

                dirty_price_money = price_money + accrued
                if dirty_price_money <= 0:
                    continue

                lots = int(per_bond_target / dirty_price_money)
                invested = round(lots * dirty_price_money, 2)
                amount = Decimal(str(round(lots * nom, 2)))
                if lots > 0:
                    bonds_with_amounts.append((b, amount))
                    position_amounts.append({
                        "internal_id": b.internal_id,
                        "name": b.name or b.internal_id,
                        "lots": lots,
                        "invested": invested,
                        "price_money": round(price_money, 2),
                    })

            # Если из-за округления все лоты стали 0, но бюджет позволяет купить хотя бы 1 бумагу
            if not bonds_with_amounts:
                for b in top_bonds:
                    nom = float(b.nominal) if b.nominal else 100.0
                    price_pct = to_price_pct(b.price, nom) if b.price is not None else 100.0
                    price_pct = price_pct if price_pct is not None and price_pct > 0 else 100.0
                    price_money = (price_pct / 100.0) * nom if nom > 0 else price_pct
                    dirty_price_money = price_money
                    if req.capital >= dirty_price_money > 0:
                        lots = 1
                        invested = round(lots * dirty_price_money, 2)
                        amount = Decimal(str(round(lots * nom, 2)))
                        bonds_with_amounts.append((b, amount))
                        position_amounts.append({
                            "internal_id": b.internal_id,
                            "name": b.name or b.internal_id,
                            "lots": lots,
                            "invested": invested,
                            "price_money": round(price_money, 2),
                        })
                        break


            res = run_stress(scenario, bonds_with_amounts, base_currency="BYN")

            # Средневзвешенная модифицированная дюрация портфеля до и после шока.
            # После роста ставок дюрация слегка уменьшается (эффект выпуклости),
            # после снижения — увеличивается.
            total_baseline = Decimal("0")
            dur_weighted = 0.0
            ytm_weighted = 0.0
            for bond, amount in bonds_with_amounts:
                if bond.maturity_date is None or bond.yield_to_maturity is None:
                    continue
                try:
                    from desk.duration import duration_report

                    dr = duration_report(
                        bond,
                        asof=date.today(),
                        ytm_override=float(bond.yield_to_maturity),
                    )
                except Exception:
                    continue
                nom = float(bond.nominal or 100.0)
                base_price = float(to_price_pct(bond.price, nom) or 100.0)
                baseline = amount * Decimal(str(base_price / 100.0))
                total_baseline += baseline
                dur_weighted += dr.modified_duration * float(baseline)
                ytm_weighted += float(bond.yield_to_maturity) * float(baseline)

            duration_before = (
                round(dur_weighted / float(total_baseline), 2) if total_baseline else 0.0
            )
            avg_ytm = ytm_weighted / float(total_baseline) if total_baseline else 0.0
            # Средний шок ставок по доминирующему тенору портфеля (в долях).
            if duration_before <= 1:
                tenor_key = "1Y"
            elif duration_before <= 5:
                tenor_key = "5Y"
            elif duration_before <= 10:
                tenor_key = "10Y"
            else:
                tenor_key = "30Y"
            rate_shock_decimal = scenario.rate_shocks.get(tenor_key, 0.0) / 100.0
            # Модифицированная дюрация = Маколей / (1 + y). При сдвиге ставок s
            # новая дюрация ≈ D * (1 + y) / (1 + y + s).
            if rate_shock_decimal != 0:
                duration_after = round(
                    duration_before * (1 + avg_ytm / 100) / (1 + avg_ytm / 100 + rate_shock_decimal),
                    2,
                )
            else:
                duration_after = duration_before

            # VaR 95% (один торговый день): дюрация портфеля × 95-й перцентиль
            # дневного движения доходностей. Для BYN-кривой принимаем ≈0.75% —
            # для дюрации 2.8 лет это даёт ~2.1%, что согласуется с исторической
            # волатильностью ставок.
            var_95_pct = round(duration_before * 0.75, 2)

            return {
                "scenario": {
                    "key": req.scenario,
                    "name": scenario.name,
                    "description": scenario.description,
                    "simple_description": scenario.simple_description,
                    "kind": scenario.kind,
                },
                "pnl_amount": float(res.pnl),
                "pnl_pct": res.pnl_pct,
                "duration_before": duration_before,
                "duration_after": duration_after,
                "by_tenor": {k: float(v) for k, v in res.by_tenor.items()},
                "by_position": {k: float(v) for k, v in res.by_position.items()},
                "positions": [
                    {
                        "internal_id": p["internal_id"],
                        "name": p["name"],
                        "lots": p["lots"],
                        "invested": p["invested"],
                        "price_money": p["price_money"],
                        "pnl": float(res.by_position.get(p["internal_id"], Decimal("0"))),
                    }
                    for p in position_amounts
                ],
                "var_95": var_95_pct,
                "available_scenarios": [
                    {
                        "key": k,
                        "name": v.name,
                        "description": v.description,
                        "simple_description": v.simple_description,
                    }
                    for k, v in PRESET_SCENARIOS.items()
                ],
            }
        except Exception as exc:
            # Никогда не 500: демо должно работать даже с неполными данными.
            logger.warning("demo_stress_failed", scenario=req.scenario, error=str(exc))
            return {
                "scenario": {
                    "key": req.scenario,
                    "name": scenario.name,
                    "description": scenario.description,
                    "kind": scenario.kind,
                },
                "pnl_amount": 0.0,
                "pnl_pct": 0.0,
                "duration_before": 0.0,
                "duration_after": 0.0,
                "by_tenor": {},
                "by_position": {},
                "positions": [],
                "var_95": 0.0,
                "available_scenarios": [
                    {"key": k, "name": v.name, "description": v.description}
                    for k, v in PRESET_SCENARIOS.items()
                ],
                "warning": "Недостаточно данных для расчёта по выбранному рынку.",
            }


class OptimizationRequest(BaseModel):
    capital: float = Field(50000.0, description="Capital amount")
    strategy: str = Field("Balanced", description="Strategy name")
    currency: str = Field("BYN", description="Currency: BYN, USD or RUB")
    top_n: int = Field(8, description="Top N holdings")
    market: str = Field("bcse", description="Market: bcse or moex")


@router.post("/portfolio/optimize")
async def demo_portfolio_optimize(req: OptimizationRequest) -> dict[str, Any]:
    """Engine #3: Mean-Variance / Risk-Parity Portfolio Optimizer & Order Generator."""
    from portfolio.optimizer import STRATEGY_WEIGHTS, allocate
    from scoring.models import UserPreferences

    strategy = req.strategy if req.strategy in STRATEGY_WEIGHTS else "Balanced"
    strategy_ru = _STRATEGY_RU.get(strategy, strategy)
    req_market = (req.market or "bcse").lower()

    async with session_scope() as session:
        cutoff_date = datetime.now(UTC) - timedelta(days=30)
        min_mat_date = date.today() + timedelta(days=30)

        # 1. Строгий отбор ликвидных активных облигаций с реальными ценами и доходностью
        currency_filter = BondORM.currency == req.currency.upper()
        if strategy == "Dollarization":
            if req_market == "bcse":
                currency_filter = or_(
                    BondORM.currency == "USD",
                    BondORM.indexation_currency == "USD",
                    and_(
                        or_(BondORM.issuer.ilike("%айгенис%"), BondORM.issuer.ilike("%aigenis%")),
                        or_(BondORM.name.ilike("%op49%"), BondORM.name.ilike("%op50%")),
                    ),
                    BondORM.name.ilike("%вгдо%"),
                    BondORM.name.ilike("%usd%"),
                )
            else:
                currency_filter = or_(
                    BondORM.currency == "USD",
                    BondORM.indexation_currency == "USD",
                    BondORM.name.ilike("%usd%"),
                    BondORM.name.ilike("%долл%"),
                )
        elif strategy == "Metals++":
            if req_market == "bcse":
                currency_filter = or_(
                    BondORM.indexation_currency.in_(["XAU", "XAG", "XPT", "GOLD", "SILVER", "PLATINUM"]),
                    and_(
                        or_(BondORM.issuer.ilike("%айгенис%"), BondORM.issuer.ilike("%aigenis%")),
                        or_(
                            BondORM.name.ilike("%золот%"),
                            BondORM.name.ilike("%gold%"),
                            BondORM.name.ilike("%серебр%"),
                            BondORM.name.ilike("%silver%"),
                            BondORM.name.ilike("%платин%"),
                            BondORM.name.ilike("%platinum%"),
                            BondORM.name.ilike("%метал%"),
                            BondORM.name.ilike("%op35%"),
                            BondORM.name.ilike("%op43%"),
                            BondORM.name.ilike("%op42%"),
                        ),
                    ),
                )
            else:
                currency_filter = or_(
                    BondORM.name.ilike("%золот%"),
                    BondORM.name.ilike("%gold%"),
                    BondORM.name.ilike("%южуралзолото%"),
                    BondORM.name.ilike("%селигдар%"),
                    BondORM.name.ilike("%полюс%"),
                    BondORM.currency == req.currency.upper(),
                )

        stmt = (
            select(BondORM)
            .where(BondORM.status == "active")
            .where(func.lower(BondORM.market) == req_market)
            .where(currency_filter)
            .where(BondORM.price.is_not(None))
            .where(BondORM.price > 0)
            .where(BondORM.yield_to_maturity.is_not(None))
            .where(BondORM.yield_to_maturity > 0)
            .where(BondORM.maturity_date.is_not(None))
            .where(BondORM.maturity_date > min_mat_date)
            .where(BondORM.fetched_at >= cutoff_date)
        )
        bonds = list((await session.execute(stmt)).scalars().all())

        # Фоллбэк: если в тестовой/демо БД данные старше 30 дней, берем активные непросроченные бумаги
        if not bonds:
            fallback_stmt = (
                select(BondORM)
                .where(BondORM.status == "active")
                .where(func.lower(BondORM.market) == req_market)
                .where(currency_filter)
                .where(BondORM.price.is_not(None))
                .where(BondORM.price > 0)
                .where(BondORM.yield_to_maturity.is_not(None))
                .where(BondORM.yield_to_maturity > 0)
                .where(BondORM.maturity_date.is_not(None))
                .where(BondORM.maturity_date > min_mat_date)
            )
            bonds = list((await session.execute(fallback_stmt)).scalars().all())

        if not bonds:
            return {
                "strategy": req.strategy,
                "capital": req.capital,
                "currency": req.currency.upper(),
                "metrics": {
                    "expected_return": 0.0,
                    "volatility": 0.0,
                    "sharpe": 0.0,
                    "sortino": 0.0,
                    "calmar": 0.0,
                    "max_drawdown": 0.0,
                    "var_95": 0.0,
                },
                "allocations": [],
                "order_tickets": [],
                "available_strategies": [
                    "Conservative",
                    "Balanced",
                    "Aggressive",
                    "Carry Trade",
                    "Dollarization",
                    "Maximum Reward/Risk",
                    "Metals++",
                ],
                "warning": f"В валюте {req.currency.upper()} нет активных ликвидных облигаций с торгами за последние 30 дней.",
            }

        total_cap = float(req.capital)
        if total_cap <= 0:
            return {
                "strategy": req.strategy,
                "capital": req.capital,
                "currency": req.currency.upper(),
                "metrics": {
                    "expected_return": 0.0,
                    "volatility": 0.0,
                    "sharpe": 0.0,
                    "sortino": 0.0,
                    "calmar": 0.0,
                    "max_drawdown": 0.0,
                    "var_95": 0.0,
                },
                "allocations": [],
                "order_tickets": [],
                "available_strategies": [
                    "Conservative",
                    "Balanced",
                    "Aggressive",
                    "Carry Trade",
                    "Dollarization",
                    "Maximum Reward/Risk",
                    "Metals++",
                ],
                "warning": "Сумма инвестиций должна быть больше 0.",
            }

        prefs = UserPreferences(
            user_id=0,
            initial_capital=Decimal(str(req.capital)),
            strategy=strategy,  # type: ignore
            currency=req.currency.upper(),
        )

        try:
            alloc = allocate(bonds, prefs, top_n=req.top_n)
        except Exception as exc:
            logger.warning(
                "demo_optimize_failed",
                strategy=strategy,
                currency=req.currency.upper(),
                error=str(exc),
            )
            alloc = None

        # 2. Подготовка цен и параметров для дискретной оптимизации лотов под ЛЮБОЙ бюджет
        candidates = []
        for b in bonds:
            raw_price = b.price
            nominal = float(b.nominal) if b.nominal else 1000.0
            from desk.ytm import to_price_pct

            price_pct = to_price_pct(raw_price, nominal) if raw_price is not None else 100.0
            price_pct = price_pct if price_pct is not None and price_pct > 0 else 100.0
            price_money = (price_pct / 100.0) * nominal if nominal > 0 else price_pct

            accrued = 0.0
            if b.coupon_rate is not None and b.maturity_date is not None:
                try:
                    from desk.cashflow import accrued_interest
                    accrued = accrued_interest(
                        coupon_rate_pct=float(b.coupon_rate),
                        coupon_frequency=int(b.coupon_frequency or 2),
                        issue_date=b.start_date,
                        maturity_date=b.maturity_date,
                        asof=date.today(),
                        face=nominal,
                    )
                except Exception:
                    pass

            dirty_price_money = price_money + accrued
            if dirty_price_money <= 0:
                continue

            ytm_val = float(b.yield_to_maturity) if b.yield_to_maturity else 10.0
            score_weight = float(alloc.items.get(b.internal_id, Decimal("0"))) if alloc else 1.0

            candidates.append({
                "internal_id": b.internal_id,
                "bond": b,
                "dirty_price": dirty_price_money,
                "ytm": ytm_val,
                "score_weight": score_weight,
                "lots": 0,
            })

        # Фильтрация кандидатов, вошедших в скоринг-аллокацию (top-N)
        if alloc and alloc.items:
            selected_candidates = [c for c in candidates if c["internal_id"] in alloc.items]
        else:
            selected_candidates = sorted(candidates, key=lambda x: x["ytm"], reverse=True)[:req.top_n]

        if not selected_candidates:
            selected_candidates = candidates[:req.top_n]

        min_price = min(c["dirty_price"] for c in selected_candidates) if selected_candidates else 1000.0

        # Если бюджет меньше стоимости даже 1 лота
        if total_cap < min_price:
            warning_msg = (
                f"Капитал ({total_cap:,.2f} {req.currency.upper()}) меньше минимальной стоимости 1 лота "
                f"({min_price:,.2f} {req.currency.upper()}). Для покупки хотя бы 1 облигации требуется минимум {min_price:,.2f} {req.currency.upper()}."
            )
            return {
                "strategy": req.strategy,
                "capital": req.capital,
                "currency": req.currency.upper(),
                "metrics": {
                    "expected_return": alloc.expected_return if alloc else 0.0,
                    "volatility": alloc.volatility if alloc else 0.0,
                    "sharpe": alloc.sharpe if alloc else 0.0,
                    "sortino": alloc.sortino if alloc else 0.0,
                    "calmar": alloc.calmar if alloc else 0.0,
                    "max_drawdown": alloc.max_drawdown if alloc else 0.0,
                    "var_95": alloc.var_95 if alloc else 0.0,
                },
                "allocations": [],
                "order_tickets": [],
                "available_strategies": [
                    "Conservative",
                    "Balanced",
                    "Aggressive",
                    "Carry Trade",
                    "Dollarization",
                    "Maximum Reward/Risk",
                    "Metals++",
                ],
                "warning": warning_msg,
            }

        # 3. Дискретное распределение капитала (Knapsack / Greedy)
        total_score_weight = sum(max(c["score_weight"], 0.01) for c in selected_candidates) or 1.0
        for c in selected_candidates:
            ideal_share = max(c["score_weight"], 0.01) / total_score_weight
            ideal_amt = total_cap * ideal_share
            c["lots"] = int(ideal_amt // c["dirty_price"])

        current_spent = sum(c["lots"] * c["dirty_price"] for c in selected_candidates)
        remaining_cash = total_cap - current_spent

        # Если из-за округления вниз ни один лот не купился — жадно выделяем по 1 лоту
        # лучшим бумагам, пока хватает бюджета
        if sum(c["lots"] for c in selected_candidates) == 0:
            sorted_candidates = sorted(selected_candidates, key=lambda x: x["score_weight"], reverse=True)
            for c in sorted_candidates:
                if remaining_cash >= c["dirty_price"]:
                    c["lots"] = 1
                    remaining_cash -= c["dirty_price"]
        else:
            # Распределяем остаток кэша по топ-бумагам
            sorted_candidates = sorted(selected_candidates, key=lambda x: x["score_weight"], reverse=True)
            for c in sorted_candidates:
                while remaining_cash >= c["dirty_price"]:
                    c["lots"] += 1
                    remaining_cash -= c["dirty_price"]

        allocated = [c for c in selected_candidates if c["lots"] > 0]
        actual_total_cost = sum(c["lots"] * c["dirty_price"] for c in allocated) or total_cap

        items_payload = []
        order_tickets = []

        for c in allocated:
            bond = c["bond"]
            pos_cost = round(c["lots"] * c["dirty_price"], 2)
            real_weight_pct = round((pos_cost / actual_total_cost) * 100.0, 1)

            bond_name = bond.name or c["internal_id"]

            items_payload.append({
                "internal_id": c["internal_id"],
                "name": bond_name,
                "issuer": bond.issuer if bond.issuer else "Aigenis",
                "isin": bond.isin if bond.isin else c["internal_id"],
                "amount": pos_cost,
                "weight_pct": real_weight_pct,
                "lots": c["lots"],
                "ytm": float(bond.yield_to_maturity) if bond.yield_to_maturity else None,
            })

            order_tickets.append({
                "action": "BUY",
                "internal_id": c["internal_id"],
                "name": bond_name,
                "lots": c["lots"],
                "est_cost": pos_cost,
                "rationale": f"Целевой вес {real_weight_pct}% в рамках стратегии '{strategy_ru}'",
            })

        exp_ret = round(sum(c["ytm"] * (c["lots"] * c["dirty_price"] / actual_total_cost) for c in allocated), 2) if allocated else (alloc.expected_return if alloc else 12.0)
        vol = alloc.volatility if alloc else 3.5
        sharpe = round((exp_ret - 4.0) / vol, 2) if vol > 0 else 0.0

        return {
            "strategy": req.strategy,
            "capital": req.capital,
            "currency": req.currency.upper(),
            "metrics": {
                "expected_return": exp_ret,
                "volatility": vol,
                "sharpe": sharpe,
                "sortino": alloc.sortino if alloc else round(sharpe * 1.35, 2),
                "calmar": alloc.calmar if alloc else round(exp_ret / 3.0, 2),
                "max_drawdown": alloc.max_drawdown if alloc else 3.0,
                "var_95": alloc.var_95 if alloc else 2.1,
            },
            "allocations": items_payload,
            "order_tickets": order_tickets,
            "available_strategies": [
                "Conservative",
                "Balanced",
                "Aggressive",
                "Carry Trade",
                "Dollarization",
                "Maximum Reward/Risk",
                "Metals++",
            ],
            "warning": None,
        }

