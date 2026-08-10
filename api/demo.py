"""Demo blueprint — fixtures-only public surface for `/demo/*`.

All responses are deterministic and read from the bundled
``demo-data/v1/`` dataset; no live API calls, no payments, no Telegram,
no audit of real users. Guarded by DEMO_DISABLE_SIDE_EFFECTS so the
blueprint is a safe showcase for pre-sale and pilot presentations.

Phase 1 (item 1.13) — deterministic ``POST /api/v1/demo/portfolio-impact``.
"""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from desk.ytm import to_price_pct, ytm_from_price
from scraper.db import session_scope
from scraper.logging import get_logger
from scraper.orm import BondHistoryORM, BondORM

logger = get_logger("api.demo")

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])

_TIER_STATUS = {
    "S": "attractive",
    "A": "attractive",
    "B": "neutral",
    "C": "review",
    "D": "high_risk",
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
        solved = ytm_from_price(
            price_pct=price_pct,
            coupon_rate_pct=float(bond.coupon_rate),
            coupon_frequency=int(bond.coupon_frequency or 2),
            maturity=bond.maturity_date,
            asof=ref,
        )
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

    return {
        "yield_to_maturity": ytm,
        "computed_ytm": computed_ytm,
        "distressed": distressed,
        "duration_years": duration_years,
        "score": score_payload,
    }


DATA_ROOT = Path(__file__).resolve().parents[1] / "demo-data" / "v1"

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
    }


@router.get("/market-data")
async def live_market_data(
    market: str = Query("bcse", pattern="^(bcse|moex)$"),
    currency: str | None = Query(None, min_length=3, max_length=3),
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    """Read-only, sanitized market snapshot for the protected demo UI.

    The old public demo shipped fabricated fixture securities.  This endpoint
    reads the latest licensed ingestion snapshot, never accepts writes, and
    exposes only instrument fields needed by the showcase.  Access to this
    route must stay behind the demo network/Cloudflare Access policy.
    """
    async with session_scope() as session:
        stmt = (
            select(BondORM)
            .where(BondORM.market == market)
            .where(BondORM.status == "active")
            .order_by(BondORM.fetched_at.desc(), BondORM.name.asc())
            .limit(limit)
        )
        if currency:
            stmt = stmt.where(BondORM.currency == currency.upper())
        rows = (await session.execute(stmt)).scalars().all()

    bonds = [_bond_payload(bond, _bond_analytics(bond)) for bond in rows]
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
            select(BondORM)
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
            stmt = stmt.where(BondORM.market == market)
        if currency:
            stmt = stmt.where(BondORM.currency == currency.upper())
        rows = (
            (await session.execute(stmt.order_by(BondORM.name.asc()).limit(limit))).scalars().all()
        )

    bonds = [_bond_payload(bond, _bond_analytics(bond)) for bond in rows]
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
