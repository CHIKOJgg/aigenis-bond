"""Analytics API mirroring the Telegram bot's capabilities.

Every endpoint returns the same data the bot shows, as JSON, so the website
can replicate the bot 1:1. Pro/Enterprise endpoints are gated by subscription
tier via `RequireFeature` (see api.access_control). Free endpoints (market
overview, scores, stats) are always available.
"""
from __future__ import annotations

import os
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from api import _helpers as _h
from api.access_control import (
    RequireFeature,
    get_current_tier,
    get_optional_user_id,
)
from desk import carry as desk_carry
from desk import duration as desk_duration
from desk import relative_value as desk_rv
from desk import repo as desk_repo
from desk import stress as desk_stress
from desk import yield_curve as desk_curve
from desk.repository import latest_rv_signals, latest_stress_runs
from forecast.engine import forecast_capital, forecast_horizons
from ml.repository import latest_model_version, predictions_for_bond
from notifications.alerts_repository import (
    create_rule,
    delete_rule,
    list_events,
    list_rules,
)
from notifications.repository import list_recent
from portfolio.income import bond_cashflows, portfolio_income
from portfolio.optimizer import allocate
from portfolio.positions_repository import (
    list_positions,
    remove_position,
    total_value,
    upsert_position,
)
from portfolio.rebalance import build_plan, maybe_auto_rebalance
from portfolio.scenarios import run_all_scenarios
from recommendations.engine import recommend_bonds, recommend_for_issuer
from scoring.disclaimer import DISCLAIMER_FULL
from scoring.engine import score_bond
from scoring.explain import explain_score
from scoring.models import UserPreferences
from scoring.repository import get_score, score_from_orm, top_scores
from scraper.config import get_settings
from scraper.db import session_scope
from scraper.models import Bond
from scraper.orm import BondORM, BondScoreORM, CompanyORM
from telegram_bot.preferences_repository import get_preferences
from telegram_bot.subscriptions import STAR_PLANS

router = APIRouter(prefix="/api/v1", tags=["analytics"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _all_bonds() -> list[Bond]:
    async with session_scope() as session:
        rows = (await session.execute(select(BondORM))).scalars().all()
        return [_h.orm_to_bond(b) for b in rows]


# --------------------------------------------------------------------------- #
# Free: subscription info (Telegram Stars + YooKassa).
# --------------------------------------------------------------------------- #
@router.get("/subscribe-info")
async def api_subscribe_info():
    username = (get_settings().telegram.bot_username or "").lstrip("@")
    deep_link = f"https://t.me/{username}?start=subscribe" if username else None
    yookassa_configured = bool(os.environ.get("YOOKASSA_SHOP_ID", "") and os.environ.get("YOOKASSA_SECRET_KEY", ""))
    yookassa_plans = []
    if yookassa_configured:
        yookassa_plans = [
            {
                "tier": "pro",
                "name": "Pro",
                "price": os.environ.get("YOOKASSA_PRO_PRICE", "29.00"),
                "currency": os.environ.get("YOOKASSA_CURRENCY", "BYN"),
                "interval": "month",
            },
            {
                "tier": "enterprise",
                "name": "Enterprise",
                "price": os.environ.get("YOOKASSA_ENTERPRISE_PRICE", "99.00"),
                "currency": os.environ.get("YOOKASSA_CURRENCY", "BYN"),
                "interval": "month",
            },
        ]
    return {
        "provider": "telegram_stars",
        "yookassa_configured": yookassa_configured,
        "yookassa_plans": yookassa_plans,
        "bot_username": username or None,
        "deep_link": deep_link,
        "plans": [
            {
                "tier": p.tier,
                "name": p.name,
                "stars": p.stars,
                "duration_days": p.duration_days,
                "blurb": p.blurb,
            }
            for p in STAR_PLANS.values()
        ],
    }


# --------------------------------------------------------------------------- #
# Free: market overview
# --------------------------------------------------------------------------- #
@router.get("/top")
async def api_top(limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0)):
    async with session_scope() as session:
        rows = await top_scores(session, limit=limit, offset=offset)
    return [
        {"internal_id": s.internal_id, "score": float(s.score), "tier": s.tier}
        for s in rows
    ]


@router.get("/bonds/currency/{currency}")
async def api_bonds_by_currency(currency: str):
    bonds = await _all_bonds()
    out = [b for b in bonds if str(b.currency).upper() == currency.upper()]
    return [
        {
            "internal_id": b.internal_id,
            "name": b.name,
            "currency": b.currency,
            "yield_to_maturity": float(b.yield_to_maturity) if b.yield_to_maturity is not None else None,
            "price": float(b.price) if b.price is not None else None,
            "issuer": b.issuer,
            "maturity_date": b.maturity_date.isoformat() if b.maturity_date else None,
            "status": b.status,
        }
        for b in out
    ]


# --------------------------------------------------------------------------- #
# Free / Pro: Single-bond deep-dive card ("should I buy this bond?")
# --------------------------------------------------------------------------- #
async def _get_bond_or_404(internal_id: str) -> Bond:
    async with session_scope() as session:
        row = (
            await session.execute(select(BondORM).where(BondORM.internal_id == internal_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Bond {internal_id} not found")
        return _h.orm_to_bond(row)


async def _score_for_bond(b: Bond):
    """Return a BondScore, preferring the stored one (persisted breakdown)."""
    async with session_scope() as session:
        orm = await get_score(session, b.internal_id)
    if orm is not None:
        return score_from_orm(orm)
    return score_bond(
        internal_id=b.internal_id,
        yield_to_maturity=b.yield_to_maturity,
        currency=b.currency,
        maturity_date=b.maturity_date,
        status=b.status,
        issuer=b.issuer,
        price=b.price,
    )


@router.get("/bond/{internal_id}", dependencies=[Depends(RequireFeature("access_bond_detail"))])
async def api_bond_card(
    internal_id: str,
    tier: str = Depends(get_current_tier),
):
    """Карточка облигации: факты + Score + вердикт.

    Free-пользователь видит факты, число Score и тир, но полный разбор
    («почему») скрыт. Pro получает объяснение сразу внутри карточки —
    это и есть точка апселла.
    """
    bond = await _get_bond_or_404(internal_id)
    score = await _score_for_bond(bond)
    is_pro = tier in {"pro", "enterprise"}
    payload: dict = {
        "bond": _h.bond_facts(bond),
        "score": round(float(score.score), 2),
        "tier": score.tier,
    }
    if is_pro:
        ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity else None
        payload["analysis"] = explain_score(score, currency=bond.currency, ytm_pct=ytm).as_dict()
        payload["analysis_locked"] = False
    else:
        payload["analysis"] = None
        payload["analysis_locked"] = True
        payload["upgrade_hint"] = "Полный разбор и вердикт доступны в подписке Pro."
    return payload


@router.get(
    "/bond/{internal_id}/analysis",
    dependencies=[Depends(RequireFeature("access_bond_analysis"))],
)
async def api_bond_analysis(internal_id: str):
    """Полный разбор одной облигации: объяснение Score, ML-прогноз, RV-сигнал.

    Единый ответ на вопрос «покупать или нет и почему» — ключевая ценность Pro.
    """
    bond = await _get_bond_or_404(internal_id)
    score = await _score_for_bond(bond)
    ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity else None
    explained = explain_score(score, currency=bond.currency, ytm_pct=ytm)

    all_bonds = await _all_bonds()
    rv_signal = None
    for s in desk_rv.relative_value_signals(all_bonds):
        if s.internal_id == internal_id:
            rv_signal = {
                "side": s.side,
                "z_score": round(float(s.z_score), 3) if s.z_score is not None else None,
                "spread_pct": round(float(s.spread_pct), 3) if s.spread_pct is not None else None,
            }
            break

    ml_prediction = None
    async with session_scope() as session:
        rows = await predictions_for_bond(session, internal_id, limit=1)
    if rows:
        p = rows[0]
        ml_prediction = {
            "decision": p.decision,
            "confidence": round(float(p.confidence), 3),
            "predicted_ytm": float(p.predicted_ytm) if p.predicted_ytm is not None else None,
            "predicted_return_pct": float(p.predicted_return_pct)
            if p.predicted_return_pct is not None
            else None,
            "explanation": p.explanation or [],
        }

    return {
        "bond": _h.bond_facts(bond),
        "analysis": explained.as_dict(),
        "relative_value": rv_signal,
        "ml_prediction": ml_prediction,
        "disclaimer": DISCLAIMER_FULL,
    }


@router.get(
    "/bond/{internal_id}/cashflow",
    dependencies=[Depends(RequireFeature("access_portfolio"))],
)
async def api_bond_cashflow(
    internal_id: str,
    amount: float = Query(1000.0, gt=0),
):
    """График купонных выплат при вложении ``amount`` в облигацию.

    «Сколько денег и когда я получу» — суть fixed income. Возвращает даты и
    суммы купонов + возврат номинала при погашении, годовой доход и доходность
    на вложенные средства (yield-on-cost).
    """
    bond = await _get_bond_or_404(internal_id)
    flows = bond_cashflows(
        internal_id=internal_id,
        amount_invested=Decimal(str(amount)),
        coupon_rate=bond.coupon_rate,
        coupon_frequency=bond.coupon_frequency,
        maturity_date=bond.maturity_date,
        price=bond.price,
    )
    total_coupons = sum(
        (f.amount for f in flows if f.kind == "coupon"), start=Decimal("0")
    )
    ann = Decimal("0")
    if bond.coupon_rate and bond.coupon_rate > 0:
        face = Decimal(str(amount)) * Decimal("100") / bond.price if bond.price else Decimal(str(amount))
        ann = (face * bond.coupon_rate / Decimal("100")).quantize(Decimal("0.01"))
    return {
        "bond": _h.bond_facts(bond),
        "amount_invested": round(amount, 2),
        "annual_income": float(ann),
        "yield_on_cost": round(float(ann / Decimal(str(amount)) * 100), 2) if amount > 0 else 0.0,
        "total_coupons": float(total_coupons),
        "cashflows": [f.as_dict() for f in flows],
    }


# --------------------------------------------------------------------------- #
# Pro: Desk analytics
# --------------------------------------------------------------------------- #
@router.get("/desk/rv", dependencies=[Depends(RequireFeature("access_desk_rv"))])
async def api_rv():
    bonds = await _all_bonds()
    signals = desk_rv.relative_value_signals(bonds)
    return [
        {
            "internal_id": s.internal_id,
            "side": s.side,
            "z_score": round(float(s.z_score), 3) if s.z_score is not None else None,
            "spread_pct": round(float(s.spread_pct), 3) if s.spread_pct is not None else None,
        }
        for s in signals
    ]


@router.get("/desk/duration", dependencies=[Depends(RequireFeature("access_desk_rv"))])
async def api_duration(bond_id: str | None = Query(None)):
    bonds = await _all_bonds()
    if bond_id:
        bond = next((b for b in bonds if b.internal_id == bond_id), None)
        if bond is None:
            raise HTTPException(status_code=404, detail=f"Bond {bond_id} not found")
        rep = desk_duration.duration_report(bond)
        title = f"duration:{bond.internal_id}"
    else:
        weights = {b.internal_id: Decimal("1") / Decimal(len(bonds) or 1) for b in bonds}
        rep = desk_duration.portfolio_duration(bonds, weights=weights)
        title = "duration:portfolio"
    return {
        "title": title,
        "macaulay_duration": round(float(rep.macaulay_duration), 4),
        "modified_duration": round(float(rep.modified_duration), 4),
        "convexity": round(float(rep.convexity), 4),
        "dv01": round(float(rep.dv01), 5),
        "key_rate_durations": {k: round(float(v), 5) for k, v in rep.key_rate_durations.items()},
    }


@router.get("/desk/carry", dependencies=[Depends(RequireFeature("access_desk_carry"))])
async def api_carry(funding: float = Query(5.0, ge=0.0)):
    bonds = await _all_bonds()
    trades = desk_carry.rank_carry(bonds, funding_rate_pct=funding)
    return [
        {
            "internal_id": t.internal_id,
            "coupon_pct": round(float(t.coupon_pct), 3),
            "rolldown_bps": round(float(t.rolldown_bps), 2),
            "expected_pnl_pct": round(float(t.expected_pnl_pct), 4),
        }
        for t in trades
    ]


class RepoRequest(BaseModel):
    bond_id: str
    notional: float = 1000.0
    tenor_days: int = 30
    repo_rate_pct: float = 5.0


@router.post("/desk/repo", dependencies=[Depends(RequireFeature("access_desk_repo"))])
async def api_repo(req: RepoRequest):
    bonds = await _all_bonds()
    bond = next((b for b in bonds if b.internal_id == req.bond_id), None)
    if bond is None:
        raise HTTPException(status_code=404, detail=f"Bond {req.bond_id} not found")
    haircut = desk_repo.haircut_by_issuer(bond.issuer)
    deal = desk_repo.repo_deal(
        bond,
        notional=Decimal(str(req.notional)),
        haircut_pct=haircut,
        repo_rate_pct=req.repo_rate_pct,
        tenor_days=req.tenor_days,
    )
    return {
        "internal_id": req.bond_id,
        "collateral_value": float(deal.collateral_value),
        "haircut_pct": float(deal.haircut_pct),
        "cash_lent": float(deal.cash_lent),
        "repo_rate_pct": float(deal.repo_rate_pct),
        "tenor_days": deal.tenor_days,
        "accrued_interest": float(deal.accrued_interest),
    }


@router.get("/desk/stress", dependencies=[Depends(RequireFeature("access_desk_stress"))])
async def api_stress():
    bonds = await _all_bonds()
    weights = {b.internal_id: Decimal("1000") for b in bonds}
    out = []
    for name, scn in desk_stress.PRESET_SCENARIOS.items():
        res = desk_stress.run_stress(scn, [(b, weights[b.internal_id]) for b in bonds])
        out.append(
            {
                "scenario": name,
                "kind": scn.kind,
                "pnl_pct": round(float(res.pnl_pct), 4),
                "pnl": round(float(res.pnl), 2),
            }
        )
    return out


@router.get("/desk/curve", dependencies=[Depends(RequireFeature("access_desk_curve"))])
async def api_curve():
    bonds = await _all_bonds()
    by_cur: dict[str, list] = {}
    for b in bonds:
        by_cur.setdefault(str(b.currency), []).append(b)
    out = []
    for cur, bs in by_cur.items():
        curve = desk_curve.curve_from_bonds(bs)
        if not curve.points:
            continue
        params = desk_curve.fit_nelson_siegel(curve.points)
        out.append(
            {
                "currency": cur,
                "slope": round(float(curve.slope()), 4),
                "beta0": round(float(params.beta0), 4),
                "beta1": round(float(params.beta1), 4),
                "beta2": round(float(params.beta2), 4),
                "points": [
                    {"tenor": p.tenor, "years": p.years, "rate_pct": round(float(p.rate_pct), 4)}
                    for p in curve.points
                ],
            }
        )
    return out


@router.get("/desk/status", dependencies=[Depends(RequireFeature("access_desk_rv"))])
async def api_desk_status():
    async with session_scope() as session:
        rv = await latest_rv_signals(session, limit=5)
        stress_runs = await latest_stress_runs(session, limit=3)
    return {
        "rv": [
            {"internal_id": s.internal_id, "z_score": round(float(s.z_score), 3), "side": s.side}
            for s in rv
        ],
        "stress": [
            {"scenario_name": r.scenario_name, "pnl_pct": round(float(r.pnl_pct), 4)}
            for r in stress_runs
        ],
    }


# --------------------------------------------------------------------------- #
# Pro: Recommendations / ML
# --------------------------------------------------------------------------- #
@router.get("/recommendations", dependencies=[Depends(RequireFeature("access_recommendations"))])
async def api_recommendations(top_k: int = Query(5, ge=1, le=20)):
    bonds = await _all_bonds()
    bond_dicts = [
        {
            "internal_id": b.internal_id,
            "name": b.name,
            "currency": b.currency,
            "yield_to_maturity": b.yield_to_maturity,
            "coupon_rate": b.coupon_rate,
            "maturity_date": b.maturity_date,
            "price": b.price,
            "status": b.status,
            "issuer": b.issuer,
        }
        for b in bonds
    ]
    prefs = _h.default_prefs(0)
    recs = recommend_bonds(bond_dicts, prefs, history_by_bond={}, top_k=top_k)
    issuer_by_id = {b["internal_id"]: b.get("issuer") for b in bond_dicts}
    return [
        {
            "rank": r.rank,
            "internal_id": r.internal_id,
            "name": r.name,
            "issuer": issuer_by_id.get(r.internal_id),
            "decision": r.decision,
            "confidence": round(float(r.confidence), 3),
            "score": round(float(r.score), 2) if r.score is not None else None,
            "predicted_return_pct": round(float(r.predicted_return_pct), 3)
            if r.predicted_return_pct is not None
            else None,
            "reasons": r.reasons,
            "risks": r.risks,
        }
        for r in recs
    ]


@router.get("/companies")
async def api_companies(
    sector: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Топ эмитентов (компаний) с агрегатами по их облигациям.

    Бесплатно: базовая детализация рынка. Агрегаты (число выпусков, средний
    YTM, средний тир) считаются на лету из ``bonds`` и ``bond_scores``.
    """
    async with session_scope() as session:
        comp_rows = (
            await session.execute(select(CompanyORM))
        ).scalars().all()
        companies = {c.issuer: c for c in comp_rows}
        bond_rows = (
            await session.execute(select(BondORM))
        ).scalars().all()
        score_rows = (
            await session.execute(select(BondScoreORM))
        ).scalars().all()
        scores_by_id = {s.internal_id: s for s in score_rows}

    by_issuer: dict[str, list[BondORM]] = {}
    for b in bond_rows:
        if b.issuer:
            by_issuer.setdefault(b.issuer, []).append(b)

    out = []
    for issuer, bs in by_issuer.items():
        if sector:
            comp = companies.get(issuer)
            if not comp or comp.sector != sector:
                continue
        ytms = [float(b.yield_to_maturity) for b in bs if b.yield_to_maturity is not None]
        tiers = [scores_by_id[b.internal_id].tier for b in bs if b.internal_id in scores_by_id and scores_by_id[b.internal_id].tier]
        avg_ytm = round(sum(ytms) / len(ytms), 2) if ytms else None
        comp = companies.get(issuer)
        out.append(
            {
                "issuer": issuer,
                "name": (comp.name if comp and comp.name else issuer) if comp else issuer,
                "sector": comp.sector if comp else None,
                "description": comp.description if comp else None,
                "why_important": comp.why_important if comp else None,
                "logo_url": comp.logo_url if comp else None,
                "bond_count": len(bs),
                "avg_yield_to_maturity": avg_ytm,
                "top_tier": _h.most_common(tiers),
                "currencies": sorted({str(b.currency) for b in bs}),
            }
        )

    out.sort(key=lambda c: (c["bond_count"], c["avg_yield_to_maturity"] or 0), reverse=True)
    return out[:limit]


@router.get("/companies/{issuer}")
async def api_company_detail(issuer: str):
    """Карточка компании-эмитента: описание, агрегаты, облигации, рекомендация.

    Бесплатно. Рекомендация по компании собирается из рекомендаций по её
    выпускам (``recommend_for_issuer``).
    """
    async with session_scope() as session:
        comp = (
            await session.execute(select(CompanyORM).where(CompanyORM.issuer == issuer))
        ).scalars().one_or_none()
        bond_rows = (
            await session.execute(select(BondORM).where(BondORM.issuer == issuer))
        ).scalars().all()
        score_rows = (
            await session.execute(
                select(BondScoreORM).where(BondScoreORM.internal_id.in_([b.internal_id for b in bond_rows]))
            )
        ).scalars().all()
        scores_by_id = {s.internal_id: s for s in score_rows}

    if not bond_rows and not comp:
        raise HTTPException(status_code=404, detail=f"Компания '{issuer}' не найдена")

    bonds = [_h.orm_to_bond(b) for b in bond_rows]
    bond_dicts = [
        {
            "internal_id": b.internal_id,
            "name": b.name,
            "currency": b.currency,
            "yield_to_maturity": b.yield_to_maturity,
            "coupon_rate": b.coupon_rate,
            "maturity_date": b.maturity_date,
            "price": b.price,
            "status": b.status,
            "issuer": b.issuer,
        }
        for b in bonds
    ]
    company_rec = None
    if bond_dicts:
        prefs = _h.default_prefs(0)
        rec = recommend_for_issuer(bond_dicts, prefs, history_by_bond={})
        if rec:
            company_rec = {
                "decision": rec.decision,
                "confidence": round(float(rec.confidence), 3),
                "score": round(float(rec.score), 2) if rec.score is not None else None,
                "predicted_return_pct": round(float(rec.predicted_return_pct), 3)
                if rec.predicted_return_pct is not None
                else None,
                "reasons": rec.reasons,
                "risks": rec.risks,
            }

    bond_list = []
    for b in bond_rows:
        s = scores_by_id.get(b.internal_id)
        bond_list.append(
            {
                "internal_id": b.internal_id,
                "name": b.name,
                "currency": b.currency,
                "yield_to_maturity": float(b.yield_to_maturity) if b.yield_to_maturity is not None else None,
                "maturity_date": b.maturity_date.isoformat() if b.maturity_date else None,
                "price": float(b.price) if b.price is not None else None,
                "issuer": b.issuer,
                "score": float(s.score) if s else None,
                "tier": s.tier if s else None,
            }
        )

    return {
        "issuer": issuer,
        "name": comp.name if comp and comp.name else issuer,
        "sector": comp.sector if comp else None,
        "description": comp.description if comp else None,
        "why_important": comp.why_important if comp else None,
        "website": comp.website if comp else None,
        "logo_url": comp.logo_url if comp else None,
        "bond_count": len(bond_rows),
        "bonds": bond_list,
        "recommendation": company_rec,
    }


@router.get("/search")
async def api_search(q: str = Query(..., min_length=1)):
    """Поиск по облигациям и компаниям (бесплатно).

    Ищет по имени/ISIN/внутреннему ID облигации и по названию/эмитенту/сектору
    компании. Возвращает два списка: ``bonds`` и ``companies``.
    """
    q_lower = q.lower().strip()
    async with session_scope() as session:
        bond_rows = (
            await session.execute(select(BondORM))
        ).scalars().all()
        comp_rows = (
            await session.execute(select(CompanyORM))
        ).scalars().all()

    bond_hits = []
    for b in bond_rows:
        haystack = " ".join(
            str(x) for x in (b.name, b.isin, b.internal_id, b.issuer) if x
        ).lower()
        if q_lower in haystack:
            bond_hits.append(
                {
                    "internal_id": b.internal_id,
                    "name": b.name,
                    "currency": b.currency,
                    "yield_to_maturity": float(b.yield_to_maturity) if b.yield_to_maturity is not None else None,
                    "issuer": b.issuer,
                }
            )
        if len(bond_hits) >= 30:
            break

    comp_hits = []
    for c in comp_rows:
        haystack = " ".join(
            str(x) for x in (c.name, c.issuer, c.sector, c.description) if x
        ).lower()
        if q_lower in haystack:
            comp_hits.append({"issuer": c.issuer, "name": c.name or c.issuer, "sector": c.sector})
        if len(comp_hits) >= 30:
            break

    return {"query": q, "bonds": bond_hits, "companies": comp_hits}


@router.get("/ml/status", dependencies=[Depends(RequireFeature("access_ml"))])
async def api_ml_status():
    async with session_scope() as session:
        mv_reg = await latest_model_version(session, "ytm_regression")
        mv_clf = await latest_model_version(session, "buy_classifier")
    return {
        "ytm_regression": (
            {"version": mv_reg.version, "train_rows": mv_reg.train_rows, "metrics": mv_reg.metrics}
            if mv_reg
            else None
        ),
        "buy_classifier": (
            {"version": mv_clf.version, "train_rows": mv_clf.train_rows, "metrics": mv_clf.metrics}
            if mv_clf
            else None
        ),
    }


@router.get("/ml/predict/{bond_id}", dependencies=[Depends(RequireFeature("access_ml"))])
async def api_ml_predict(bond_id: str):
    async with session_scope() as session:
        rows = await predictions_for_bond(session, bond_id, limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="No prediction for this bond")
    p = rows[0]
    return {
        "internal_id": bond_id,
        "decision": p.decision,
        "confidence": round(float(p.confidence), 3),
        "predicted_ytm": float(p.predicted_ytm) if p.predicted_ytm is not None else None,
        "predicted_return_pct": float(p.predicted_return_pct)
        if p.predicted_return_pct is not None
        else None,
        "explanation": p.explanation or [],
        "disclaimer": DISCLAIMER_FULL,
    }


# --------------------------------------------------------------------------- #
# Pro: Portfolio / Forecast / Scenarios
# --------------------------------------------------------------------------- #
@router.get("/forecast", dependencies=[Depends(RequireFeature("access_forecast"))])
async def api_forecast(user_id: int | None = Depends(get_optional_user_id)):
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id or 0)
    forecasts = forecast_horizons(
        initial_capital=prefs.initial_capital,
        monthly_contribution=prefs.monthly_contribution,
        expected_annual_return_pct=7.0,
        volatility_pct=4.0,
    )
    return [
        {
            "horizon_years": f.horizon_years,
            "expected_capital": f.expected_capital,
            "pessimistic_capital": f.pessimistic_capital,
            "optimistic_capital": f.optimistic_capital,
        }
        for f in forecasts
    ]


@router.get("/scenarios", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_scenarios(user_id: int | None = Depends(get_optional_user_id)):
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id or 0)
        from notifications.fx_repository import latest_fx

        fx = await latest_fx(session, "USD/BYN")
    current = fx.rate if fx else Decimal("3.30")
    results = run_all_scenarios(
        current_usd_byn=current,
        usd_share=prefs.share_usd,
        byn_share=prefs.share_byn,
        metals_share=prefs.share_metals,
        eur_share=prefs.share_eur,
    )
    return [
        {
            "scenario": r.scenario,
            "usd_byn_end": float(r.usd_byn_end),
            "fx_change_pct": round(float(r.fx_change_pct), 2),
            "portfolio_value_change_pct": round(float(r.portfolio_value_change_pct), 3),
        }
        for r in results
    ]


# --------------------------------------------------------------------------- #
# Pro: Alerts
# --------------------------------------------------------------------------- #
@router.get("/alerts", dependencies=[Depends(RequireFeature("access_alerts"))])
async def api_alerts(limit: int = Query(10, ge=1, le=50)):
    async with session_scope() as session:
        alerts = await list_recent(session, limit=limit)
    return [{"title": a.title, "message": a.message} for a in alerts]


# --------------------------------------------------------------------------- #
# Free (authenticated): Watchlist
# --------------------------------------------------------------------------- #
@router.get("/watchlist")
async def api_watchlist(user_id: int | None = Depends(get_optional_user_id)):
    if user_id is None:
        return []
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
        if not prefs.watchlist:
            return []
        result = await session.execute(
            select(BondORM).where(BondORM.internal_id.in_(prefs.watchlist))
        )
        watch_bonds = {b.internal_id: b.name for b in result.scalars().all()}
        lines = []
        for iid in prefs.watchlist:
            sc = await get_score(session, iid)
            lines.append(
                {
                    "internal_id": iid,
                    "name": watch_bonds.get(iid, ""),
                    "score": round(float(sc.score), 2) if sc else None,
                }
            )
    return lines


# --------------------------------------------------------------------------- #
# Pro: Personal portfolio (mirrors the Telegram bot, for the website)
# --------------------------------------------------------------------------- #
class PositionRequest(BaseModel):
    internal_id: str
    amount: float = 1000.0


def _build_forecast(prefs: UserPreferences, expected_return: float, volatility: float) -> list[dict]:
    return [
        {
            "horizon_years": f.horizon_years,
            "expected_capital": f.expected_capital,
            "pessimistic_capital": f.pessimistic_capital,
            "optimistic_capital": f.optimistic_capital,
        }
        for f in forecast_horizons(
            initial_capital=prefs.initial_capital,
            monthly_contribution=prefs.monthly_contribution,
            expected_annual_return_pct=max(expected_return, 0.1),
            volatility_pct=volatility,
        )
    ]


@router.get("/positions", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_list_positions(user_id: int | None = Depends(get_optional_user_id)):
    uid = user_id or 0
    async with session_scope() as session:
        positions = await list_positions(session, uid)
    bonds = {b.internal_id: b for b in await _all_bonds()}
    items = []
    for p in positions:
        b = bonds.get(p.internal_id)
        items.append(
            {
                "internal_id": p.internal_id,
                "amount": float(p.amount),
                "name": b.name if b else None,
                "currency": b.currency if b else None,
                "yield_to_maturity": float(b.yield_to_maturity)
                if (b and b.yield_to_maturity)
                else None,
                "price": float(b.price) if (b and b.price) else None,
            }
        )
    return {"positions": items, "total_invested": round(sum(i["amount"] for i in items), 2)}


@router.post("/positions", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_add_position(
    req: PositionRequest,
    user_id: int | None = Depends(get_optional_user_id),
):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    uid = user_id or 0
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == req.internal_id))
        ).scalar_one_or_none()
        if bond is None:
            raise HTTPException(status_code=404, detail=f"Bond {req.internal_id} not found")
        await upsert_position(session, uid, req.internal_id, Decimal(str(req.amount)))
    return {"status": "ok", "internal_id": req.internal_id, "amount": req.amount}


@router.delete("/positions/{internal_id}", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_remove_position(
    internal_id: str,
    user_id: int | None = Depends(get_optional_user_id),
):
    uid = user_id or 0
    async with session_scope() as session:
        await remove_position(session, uid, internal_id)
    return {"status": "ok", "internal_id": internal_id}


@router.get("/portfolio/plan", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_portfolio_plan(user_id: int | None = Depends(get_optional_user_id)):
    """Rebalance plan: target allocation vs the user's actual holdings."""
    uid = user_id or 0
    async with session_scope() as session:
        prefs = await get_preferences(session, uid)
        positions = await list_positions(session, uid)
    if not positions:
        return {"mode": "empty", "max_drift_observed": 0.0, "estimated_cost": 0.0, "actions": []}
    bonds = await _all_bonds()
    total = total_value(positions) or prefs.initial_capital
    plan = build_plan(
        bonds=bonds, prefs=prefs, current_positions=positions, current_total=total
    )
    if plan is None:
        return {"mode": "portfolio", "max_drift_observed": 0.0, "estimated_cost": 0.0, "actions": []}
    return {
        "mode": "portfolio",
        "strategy": plan.strategy,
        "max_drift_observed": round(float(plan.max_drift_observed), 4),
        "estimated_cost": round(float(plan.estimated_cost), 2),
        "actions": [
            {
                "internal_id": a.internal_id,
                "side": a.side,
                "amount": float(a.amount),
                "weight_before": a.weight_before,
                "weight_after": a.weight_after,
                "reason": a.reason,
            }
            for a in plan.actions
        ],
    }


@router.get("/portfolio/income", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_portfolio_income(
    user_id: int | None = Depends(get_optional_user_id),
    horizon_months: int = Query(12, ge=1, le=120),
):
    """Календарь купонного дохода по фактическим позициям пользователя.

    Отвечает на главный вопрос держателя облигаций: сколько денег в год я
    получаю, какая доходность на вложенное, когда следующая выплата и как
    доход распределён по месяцам.
    """
    uid = user_id or 0
    async with session_scope() as session:
        positions = await list_positions(session, uid)
    if not positions:
        return {
            "mode": "empty",
            "total_invested": 0.0,
            "annual_income": 0.0,
            "yield_on_cost": 0.0,
            "next_payment": None,
            "monthly_calendar": [],
            "per_bond": [],
        }
    bonds_by_id = {b.internal_id: b for b in await _all_bonds()}
    holdings = []
    for p in positions:
        b = bonds_by_id.get(p.internal_id)
        holdings.append(
            {
                "internal_id": p.internal_id,
                "amount": float(p.amount),
                "name": b.name if b else None,
                "currency": b.currency if b else None,
                "coupon_rate": b.coupon_rate if b else None,
                "coupon_frequency": b.coupon_frequency if b else None,
                "maturity_date": b.maturity_date if b else None,
                "price": b.price if b else None,
            }
        )
    result = portfolio_income(holdings, horizon_months=horizon_months)
    result["mode"] = "portfolio"
    return result


@router.get("/portfolio", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_portfolio(user_id: int | None = Depends(get_optional_user_id)):
    """Personalized portfolio: real holdings + metrics, or a starter basket.

    Unlike the previous implementation (which always assumed a default
    10 000 / 500 capital), this uses the authenticated user's actual positions
    and saved preferences — so the website now matches the Telegram bot.
    """
    uid = user_id or 0
    async with session_scope() as session:
        prefs = await get_preferences(session, uid)
        positions = await list_positions(session, uid)
    bonds = await _all_bonds()
    bonds_by_id = {b.internal_id: b for b in bonds}

    if not positions:
        alloc = allocate(bonds, prefs, top_n=10)
        return {
            "mode": "recommendation",
            "strategy": alloc.strategy,
            "positions_count": 0,
            "total_invested": 0,
            "expected_return": round(float(alloc.expected_return), 3),
            "sharpe": round(float(alloc.sharpe), 3),
            "sortino": round(float(alloc.sortino), 3),
            "max_drawdown": round(float(alloc.max_drawdown), 3),
            "var_95": round(float(alloc.var_95), 3),
            "forecast": _build_forecast(prefs, alloc.expected_return, alloc.volatility),
        }

    held = [b for b in bonds if b.internal_id in {p.internal_id for p in positions}]
    alloc = allocate(held, prefs, top_n=max(len(held), 1))
    total = total_value(positions)
    holdings = []
    for p in positions:
        b = bonds_by_id.get(p.internal_id)
        weight = float(p.amount / total) if total > 0 else 0.0
        holdings.append(
            {
                "internal_id": p.internal_id,
                "name": b.name if b else None,
                "currency": b.currency if b else None,
                "amount": float(p.amount),
                "weight": round(weight, 4),
                "yield_to_maturity": float(b.yield_to_maturity)
                if (b and b.yield_to_maturity)
                else None,
            }
        )
    return {
        "mode": "portfolio",
        "strategy": prefs.strategy,
        "positions_count": len(positions),
        "total_invested": round(float(total), 2),
        "expected_return": round(float(alloc.expected_return), 3),
        "sharpe": round(float(alloc.sharpe), 3),
        "sortino": round(float(alloc.sortino), 3),
        "max_drawdown": round(float(alloc.max_drawdown), 3),
        "var_95": round(float(alloc.var_95), 3),
        "holdings": sorted(holdings, key=lambda h: h["amount"], reverse=True),
        "forecast": _build_forecast(prefs, alloc.expected_return, alloc.volatility),
    }


# --------------------------------------------------------------------------- #
# Pro: Goal-based allocation ("подобрать под мою цель")
# --------------------------------------------------------------------------- #
class AllocateRequest(BaseModel):
    amount: float = Field(10000.0, gt=0)
    horizon_years: int = Field(3, ge=1, le=30)
    risk: str = "Balanced"
    share_usd: float | None = None
    share_byn: float | None = None
    share_metals: float | None = None
    share_eur: float | None = None
    top_n: int = Field(10, ge=1, le=30)


_VALID_STRATEGIES = {
    "Conservative",
    "Balanced",
    "Aggressive",
    "Carry Trade",
    "Dollarization",
    "Maximum Reward/Risk",
}


@router.post("/allocate", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_allocate(
    req: AllocateRequest,
    user_id: int | None = Depends(get_optional_user_id),
):
    """Подобрать конкретную корзину облигаций под сумму, срок и риск-профиль.

    Это самая понятная ценность для пользователя: «у меня X, горизонт Y лет,
    риск Z — что купить прямо сейчас». Возвращает доли, ожидаемую доходность и
    проекцию капитала. Не требует наличия сохранённого портфеля.
    """
    if req.risk not in _VALID_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"unknown risk '{req.risk}'")
    prefs = UserPreferences(
        user_id=user_id or 0,
        initial_capital=Decimal(str(req.amount)),
        monthly_contribution=Decimal("0"),
        share_usd=req.share_usd if req.share_usd is not None else 0.5,
        share_byn=req.share_byn if req.share_byn is not None else 0.3,
        share_metals=req.share_metals if req.share_metals is not None else 0.1,
        share_eur=req.share_eur if req.share_eur is not None else 0.1,
        strategy=req.risk,
    )
    bonds = await _all_bonds()
    alloc = allocate(bonds, prefs, top_n=req.top_n)
    bonds_by_id = {b.internal_id: b for b in bonds}

    basket = []
    for iid, amount in alloc.items.items():
        b = bonds_by_id.get(iid)
        if b is None:
            continue
        basket.append(
            {
                "internal_id": iid,
                "name": b.name,
                "currency": b.currency,
                "yield_to_maturity": float(b.yield_to_maturity)
                if b.yield_to_maturity
                else None,
                "amount": round(float(amount), 2),
                "weight": round(float(amount / prefs.initial_capital), 4)
                if prefs.initial_capital > 0
                else 0.0,
            }
        )
    projection = forecast_capital(
        initial_capital=prefs.initial_capital,
        monthly_contribution=Decimal("0"),
        expected_annual_return_pct=max(float(alloc.expected_return), 0.1),
        horizon_years=req.horizon_years,
        volatility_pct=alloc.volatility,
    )
    return {
        "strategy": alloc.strategy,
        "total_allocated": round(
            sum(float(a) for a in alloc.items.values()), 2
        ),
        "expected_return": round(float(alloc.expected_return), 3),
        "sharpe": round(float(alloc.sharpe), 3),
        "sortino": round(float(alloc.sortino), 3),
        "max_drawdown": round(float(alloc.max_drawdown), 3),
        "var_95": round(float(alloc.var_95), 3),
        "basket": sorted(basket, key=lambda x: x["amount"], reverse=True),
        "projection": {
            "horizon_years": projection.horizon_years,
            "expected_capital": projection.expected_capital,
            "pessimistic_capital": projection.pessimistic_capital,
            "optimistic_capital": projection.optimistic_capital,
        },
    }


# --------------------------------------------------------------------------- #
# Pro: Rebalance plan + apply
# --------------------------------------------------------------------------- #
class BuildPlanRequest(BaseModel):
    positions: list[dict] | None = None
    drift_threshold: float = 0.05
    top_n: int = Field(10, ge=1, le=30)


@router.post("/build_plan", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_build_plan(
    req: BuildPlanRequest,
    user_id: int | None = Depends(get_optional_user_id),
):
    """План ребалансировки: целевое распределение vs текущих позиций.

    Если ``positions`` не переданы — берутся сохранённые позиции пользователя.
    """
    uid = user_id or 0
    bonds = await _all_bonds()
    async with session_scope() as session:
        prefs = await get_preferences(session, uid)

    if req.positions:
        current = [
            type("Pos", (), {"internal_id": p["internal_id"], "amount": Decimal(str(p["amount"]))})
            for p in req.positions
        ]
        total = sum((p.amount for p in current), start=Decimal("0"))
    else:
        async with session_scope() as session:
            current = await list_positions(session, uid)
        total = total_value(current) or prefs.initial_capital

    if not current:
        return {"mode": "empty", "max_drift_observed": 0.0, "estimated_cost": 0.0, "actions": []}

    plan = build_plan(
        bonds=bonds,
        prefs=prefs,
        current_positions=current,
        current_total=total,
        drift_threshold=req.drift_threshold,
        top_n=req.top_n,
    )
    if plan is None:
        return {"mode": "ok", "max_drift_observed": 0.0, "estimated_cost": 0.0, "actions": []}
    return {
        "mode": "plan",
        "strategy": plan.strategy,
        "max_drift_observed": round(float(plan.max_drift_observed), 4),
        "estimated_cost": round(float(plan.estimated_cost), 2),
        "actions": [
            {
                "internal_id": a.internal_id,
                "side": a.side,
                "amount": float(a.amount),
                "weight_before": a.weight_before,
                "weight_after": a.weight_after,
                "reason": a.reason,
            }
            for a in plan.actions
        ],
    }


@router.post("/rebalance", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_rebalance(
    user_id: int | None = Depends(get_optional_user_id),
    drift_threshold: float = 0.05,
):
    """Применить ребалансировку к сохранённым позициям пользователя."""
    uid = user_id or 0
    bonds = await _all_bonds()
    async with session_scope() as session:
        prefs = await get_preferences(session, uid)
    plan = await maybe_auto_rebalance(
        user_id=uid, prefs=prefs, bonds=bonds, drift_threshold=drift_threshold
    )
    if plan is None:
        return {"rebalanced": False, "reason": "drift ниже порога — действие не требуется"}
    return {
        "rebalanced": True,
        "strategy": plan.strategy,
        "max_drift_observed": round(float(plan.max_drift_observed), 4),
        "estimated_cost": round(float(plan.estimated_cost), 2),
        "actions": [
            {
                "internal_id": a.internal_id,
                "side": a.side,
                "amount": float(a.amount),
            }
            for a in plan.actions
        ],
    }


# --------------------------------------------------------------------------- #
# Pro: User-configurable alerts on the watchlist / any bond
# --------------------------------------------------------------------------- #
class AlertRuleRequest(BaseModel):
    internal_id: str
    metric: str = Field("price", pattern="^(price|ytm)$")
    direction: str = Field("below", pattern="^(above|below)$")
    threshold: float
    note: str | None = None


@router.post("/alerts/rules", dependencies=[Depends(RequireFeature("access_alerts"))])
async def api_create_alert_rule(
    req: AlertRuleRequest,
    user_id: int | None = Depends(get_optional_user_id),
):
    uid = user_id or 0
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == req.internal_id))
        ).scalar_one_or_none()
        if bond is None:
            raise HTTPException(status_code=404, detail=f"Bond {req.internal_id} not found")
        rule = await create_rule(
            session,
            user_id=uid,
            internal_id=req.internal_id,
            metric=req.metric,
            direction=req.direction,
            threshold=Decimal(str(req.threshold)),
            note=req.note,
        )
        return {
            "id": rule.id,
            "internal_id": rule.internal_id,
            "metric": rule.metric,
            "direction": rule.direction,
            "threshold": float(rule.threshold),
            "active": rule.active,
        }


@router.get("/alerts/rules", dependencies=[Depends(RequireFeature("access_alerts"))])
async def api_list_alert_rules(user_id: int | None = Depends(get_optional_user_id)):
    uid = user_id or 0
    async with session_scope() as session:
        rules = await list_rules(session, uid)
    return [
        {
            "id": r.id,
            "internal_id": r.internal_id,
            "metric": r.metric,
            "direction": r.direction,
            "threshold": float(r.threshold),
            "note": r.note,
            "active": r.active,
            "last_value": float(r.last_value) if r.last_value is not None else None,
            "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
        }
        for r in rules
    ]


@router.delete(
    "/alerts/rules/{rule_id}", dependencies=[Depends(RequireFeature("access_alerts"))]
)
async def api_delete_alert_rule(
    rule_id: int,
    user_id: int | None = Depends(get_optional_user_id),
):
    uid = user_id or 0
    async with session_scope() as session:
        removed = await delete_rule(session, uid, rule_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "ok", "id": rule_id}


@router.get("/alerts/feed", dependencies=[Depends(RequireFeature("access_alerts"))])
async def api_alert_feed(
    user_id: int | None = Depends(get_optional_user_id),
    limit: int = Query(50, ge=1, le=200),
):
    """Лента сработавших пользовательских алертов (не системных)."""
    uid = user_id or 0
    async with session_scope() as session:
        events = await list_events(session, uid, limit=limit)
    return [
        {
            "id": e.id,
            "internal_id": e.internal_id,
            "metric": e.metric,
            "message": e.message,
            "value": float(e.value) if e.value is not None else None,
            "delivered": e.delivered,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


