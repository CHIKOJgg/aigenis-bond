"""Analytics API mirroring the Telegram bot's capabilities.

Every endpoint returns the same data the bot shows, as JSON, so the website
can replicate the bot 1:1. Pro/Enterprise endpoints are gated by subscription
tier via `RequireFeature` (see api.access_control). Free endpoints (market
overview, scores, stats) are always available.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from api.access_control import (
    RequireFeature,
    get_optional_user_id,
)
from desk import carry as desk_carry
from desk import duration as desk_duration
from desk import relative_value as desk_rv
from desk import repo as desk_repo
from desk import stress as desk_stress
from desk import yield_curve as desk_curve
from desk.repository import latest_rv_signals, latest_stress_runs
from forecast.engine import forecast_horizons
from ml.repository import latest_model_version, predictions_for_bond
from notifications.repository import list_recent
from portfolio.optimizer import allocate
from portfolio.scenarios import run_all_scenarios
from recommendations.engine import recommend_bonds
from scoring.models import UserPreferences
from scoring.repository import get_score, top_scores
from scraper.db import session_scope
from scraper.models import Bond
from scraper.orm import BondORM
from telegram_bot.preferences_repository import get_preferences

router = APIRouter(prefix="/api/v1", tags=["analytics"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _all_bonds() -> list[Bond]:
    async with session_scope() as session:
        rows = (await session.execute(select(BondORM))).scalars().all()
        return [_orm_to_bond(b) for b in rows]


def _orm_to_bond(b: BondORM) -> Bond:
    return Bond(
        internal_id=b.internal_id,
        name=b.name,
        currency=b.currency,
        yield_to_maturity=b.yield_to_maturity,
        coupon_rate=b.coupon_rate,
        coupon_frequency=b.coupon_frequency,
        maturity_date=b.maturity_date,
        price=b.price,
        issuer=b.issuer,
        status=b.status,
        nominal=b.nominal,
        fetched_at=b.fetched_at,
    )


def _default_prefs(user_id: int) -> UserPreferences:
    return UserPreferences(
        user_id=user_id,
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("500"),
        share_usd=0.5,
        share_byn=0.3,
        share_metals=0.1,
        share_eur=0.1,
        strategy="Balanced",
        watchlist=[],
    )


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


@router.get("/bonds/{currency}")
async def api_bonds_by_currency(currency: str):
    bonds = await _all_bonds()
    out = [b for b in bonds if str(b.currency).upper() == currency.upper()]
    return [
        {
            "internal_id": b.internal_id,
            "name": b.name,
            "currency": b.currency,
            "yield_to_maturity": float(b.yield_to_maturity) if b.yield_to_maturity else None,
            "price": float(b.price) if b.price else None,
            "issuer": b.issuer,
            "maturity_date": b.maturity_date.isoformat() if b.maturity_date else None,
            "status": b.status,
        }
        for b in out
    ]


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
@router.get(
    "/recommendations",
    dependencies=[Depends(RequireFeature("access_recommendations"))],
)
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
    prefs = _default_prefs(0)
    recs = recommend_bonds(bond_dicts, prefs, history_by_bond={}, top_k=top_k)
    return [
        {
            "rank": r.rank,
            "internal_id": r.internal_id,
            "name": r.name,
            "decision": r.decision,
            "confidence": round(float(r.confidence), 3),
            "score": round(float(r.score), 2) if r.score is not None else None,
            "predicted_return_pct": round(float(r.predicted_return_pct), 3)
            if r.predicted_return_pct is not None
            else None,
        }
        for r in recs
    ]


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
    }


# --------------------------------------------------------------------------- #
# Pro: Portfolio / Forecast / Scenarios
# --------------------------------------------------------------------------- #
@router.get("/portfolio", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_portfolio():
    bonds = await _all_bonds()
    prefs = _default_prefs(0)
    alloc = allocate(bonds, prefs, top_n=10)
    forecasts = forecast_horizons(
        initial_capital=prefs.initial_capital,
        monthly_contribution=prefs.monthly_contribution,
        expected_annual_return_pct=max(alloc.expected_return, 0.1),
        volatility_pct=alloc.volatility,
    )
    return {
        "strategy": alloc.strategy,
        "expected_return": round(float(alloc.expected_return), 3),
        "sharpe": round(float(alloc.sharpe), 3),
        "sortino": round(float(alloc.sortino), 3),
        "max_drawdown": round(float(alloc.max_drawdown), 3),
        "var_95": round(float(alloc.var_95), 3),
        "forecast": [
            {
                "horizon_years": f.horizon_years,
                "expected_capital": f.expected_capital,
                "pessimistic_capital": f.pessimistic_capital,
                "optimistic_capital": f.optimistic_capital,
            }
            for f in forecasts
        ],
    }


@router.get("/forecast", dependencies=[Depends(RequireFeature("access_forecast"))])
async def api_forecast():
    prefs = _default_prefs(0)
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
async def api_scenarios():
    prefs = _default_prefs(0)
    results = run_all_scenarios(
        current_usd_byn=Decimal("3.30"),
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
