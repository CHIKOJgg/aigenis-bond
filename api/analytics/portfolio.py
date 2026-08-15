"""Personal portfolio, forecast, watchlist, alerts and user-configurable alert rules."""

from __future__ import annotations

from decimal import Decimal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.access_control import RequireFeature, require_user_id
from api.analytics import router
from api.analytics._helpers import _all_bonds
from forecast.engine import forecast_capital, forecast_horizons
from notifications.alerts_repository import (
    create_rule,
    delete_rule,
    list_events,
    list_rules,
)
from notifications.repository import list_recent
from portfolio.income import portfolio_income
from portfolio.optimizer import allocate
from portfolio.positions_repository import (
    list_positions,
    remove_position,
    total_value,
    upsert_position,
)
from portfolio.rebalance import build_plan, maybe_auto_rebalance
from portfolio.scenarios import run_all_scenarios
from scoring.models import UserPreferences
from scoring.repository import get_score
from scraper.db import session_scope
from scraper.orm import BondORM, StockORM
from telegram_bot.preferences_repository import get_preferences


# --------------------------------------------------------------------------- #
# Pro: Forecast / Scenarios
# --------------------------------------------------------------------------- #
@router.get("/forecast", dependencies=[Depends(RequireFeature("access_forecast"))])
async def api_forecast(user_id: int = Depends(require_user_id)):
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
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
            "mc_percentiles": f.mc_percentiles,
            "cvar_95": f.cvar_95,
            "method": f.assumptions.get("method", "deterministic"),
        }
        for f in forecasts
    ]


@router.get("/scenarios", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_scenarios(user_id: int = Depends(require_user_id)):
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
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
# Pro: Alerts (system feed)
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
async def api_watchlist(user_id: int = Depends(require_user_id)):
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


def _build_forecast(
    prefs: UserPreferences, expected_return: float, volatility: float
) -> list[dict]:
    return [
        {
            "horizon_years": f.horizon_years,
            "expected_capital": f.expected_capital,
            "pessimistic_capital": f.pessimistic_capital,
            "optimistic_capital": f.optimistic_capital,
            "mc_percentiles": f.mc_percentiles,
            "cvar_95": f.cvar_95,
        }
        for f in forecast_horizons(
            initial_capital=prefs.initial_capital,
            monthly_contribution=prefs.monthly_contribution,
            expected_annual_return_pct=max(expected_return, 0.1),
            volatility_pct=volatility,
        )
    ]


async def _get_fx_rates(session) -> dict[str, float]:
    from notifications.fx_repository import latest_fx

    rates = {"BYN": 1.0}
    for pair, curr in [("USD/BYN", "USD"), ("EUR/BYN", "EUR"), ("RUB/BYN", "RUB")]:
        fx = await latest_fx(session, pair)
        if fx:
            rates[curr] = float(fx.rate)
        else:
            if curr == "USD":
                rates[curr] = 3.3
            elif curr == "EUR":
                rates[curr] = 3.6
            elif curr == "RUB":
                rates[curr] = 0.035
    return rates


@router.get("/positions", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_list_positions(user_id: int = Depends(require_user_id)):
    uid = user_id
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
    user_id: int = Depends(require_user_id),
):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    uid = user_id
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == req.internal_id))
        ).scalar_one_or_none()
        if bond is None:
            raise HTTPException(status_code=404, detail=f"Bond {req.internal_id} not found")
        await upsert_position(session, uid, req.internal_id, Decimal(str(req.amount)))
    return {"status": "ok", "internal_id": req.internal_id, "amount": req.amount}


@router.delete(
    "/positions/{internal_id}", dependencies=[Depends(RequireFeature("access_portfolio"))]
)
async def api_remove_position(
    internal_id: str,
    user_id: int = Depends(require_user_id),
):
    uid = user_id
    async with session_scope() as session:
        await remove_position(session, uid, internal_id)
    return {"status": "ok", "internal_id": internal_id}


@router.get("/portfolio/plan", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_portfolio_plan(user_id: int = Depends(require_user_id)):
    """Rebalance plan: target allocation vs the user's actual holdings."""
    uid = user_id
    async with session_scope() as session:
        prefs = await get_preferences(session, uid)
        positions = await list_positions(session, uid)
        fx_rates = await _get_fx_rates(session)
    if not positions:
        return {"mode": "empty", "max_drift_observed": 0.0, "estimated_cost": 0.0, "actions": []}
    bonds = await _all_bonds()
    bonds_by_id = {b.internal_id: b for b in bonds}
    total = total_value(positions, bonds_by_id, fx_rates) or prefs.initial_capital
    plan = build_plan(bonds=bonds, prefs=prefs, current_positions=positions, current_total=total)
    if plan is None:
        return {
            "mode": "portfolio",
            "max_drift_observed": 0.0,
            "estimated_cost": 0.0,
            "actions": [],
        }
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
    user_id: int = Depends(require_user_id),
    horizon_months: int = Query(12, ge=1, le=120),
):
    """Календарь купонного дохода по фактическим позициям пользователя.

    Отвечает на главный вопрос держателя облигаций: сколько денег в год я
    получаю, какая доходность на вложенное, когда следующая выплата и как
    доход распределён по месяцам.
    """
    uid = user_id
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
    async with session_scope() as session:
        fx_rates = await _get_fx_rates(session)
    result = portfolio_income(holdings, horizon_months=horizon_months, fx_rates=fx_rates)
    result["mode"] = "portfolio"
    return result


@router.get("/portfolio", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_portfolio(user_id: int = Depends(require_user_id)):
    """Personalized portfolio: real holdings + metrics, or a starter basket.

    Unlike the previous implementation (which always assumed a default
    10 000 / 500 capital), this uses the authenticated user's actual positions
    and saved preferences — so the website now matches the Telegram bot.
    """
    uid = user_id
    async with session_scope() as session:
        prefs = await get_preferences(session, uid)
        positions = await list_positions(session, uid)
        fx_rates = await _get_fx_rates(session)
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
            "calmar": round(float(alloc.calmar), 3),
            "forecast": _build_forecast(prefs, alloc.expected_return, alloc.volatility),
        }

    held = [b for b in bonds if b.internal_id in {p.internal_id for p in positions}]
    alloc = allocate(held, prefs, top_n=max(len(held), 1))
    total = total_value(positions, bonds_by_id, fx_rates)
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
        "calmar": round(float(alloc.calmar), 3),
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
    "Metals++",
}


@router.post("/allocate", dependencies=[Depends(RequireFeature("access_portfolio"))])
async def api_allocate(
    req: AllocateRequest,
    user_id: int = Depends(require_user_id),
):
    """Подобрать конкретную корзину облигаций под сумму, срок и риск-профиль.

    Это самая понятная ценность для пользователя: «у меня X, горизонт Y лет,
    риск Z — что купить прямо сейчас». Возвращает доли, ожидаемую доходность и
    проекцию капитала. Не требует наличия сохранённого портфеля.
    """
    if req.risk not in _VALID_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"unknown risk '{req.risk}'")
    prefs = UserPreferences(
        user_id=user_id,
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
                "yield_to_maturity": float(b.yield_to_maturity) if b.yield_to_maturity else None,
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
        "total_allocated": round(sum(float(a) for a in alloc.items.values()), 2),
        "expected_return": round(float(alloc.expected_return), 3),
        "sharpe": round(float(alloc.sharpe), 3),
        "sortino": round(float(alloc.sortino), 3),
        "max_drawdown": round(float(alloc.max_drawdown), 3),
        "var_95": round(float(alloc.var_95), 3),
        "calmar": round(float(alloc.calmar), 3),
        "basket": sorted(basket, key=lambda x: x["amount"], reverse=True),
        "projection": {
            "horizon_years": projection.horizon_years,
            "expected_capital": projection.expected_capital,
            "pessimistic_capital": projection.pessimistic_capital,
            "optimistic_capital": projection.optimistic_capital,
            "mc_percentiles": projection.mc_percentiles,
            "cvar_95": projection.cvar_95,
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
    user_id: int = Depends(require_user_id),
):
    """План ребалансировки: целевое распределение vs текущих позиций.

    Если ``positions`` не переданы — берутся сохранённые позиции пользователя.
    """
    uid = user_id
    bonds = await _all_bonds()
    async with session_scope() as session:
        prefs = await get_preferences(session, uid)
        fx_rates = await _get_fx_rates(session)

    bonds_by_id = {b.internal_id: b for b in bonds}

    if req.positions:
        current = [
            type("Pos", (), {"internal_id": p["internal_id"], "amount": Decimal(str(p["amount"]))})
            for p in req.positions
        ]
        total = total_value(current, bonds_by_id, fx_rates)
    else:
        async with session_scope() as session:
            current = await list_positions(session, uid)
        total = total_value(current, bonds_by_id, fx_rates) or prefs.initial_capital

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
    user_id: int = Depends(require_user_id),
    drift_threshold: float = 0.05,
):
    """Применить ребалансировку к сохранённым позициям пользователя."""
    uid = user_id
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
# Pro: User-configurable alerts on the watchlist / any instrument
# --------------------------------------------------------------------------- #
# Metric names are asset-class aware: bonds expose price/ytm, stocks expose
# price/pbr/pe/dividend_yield. The endpoint validates the metric against the
# resolved instrument class (a stock rule on "ytm" is a 400, a bond rule on
# "pbr" likewise).
BOND_METRICS = {"price", "ytm"}
STOCK_METRICS = {"price", "pbr", "pe", "dividend_yield"}
ALL_ALERT_METRICS = BOND_METRICS | STOCK_METRICS


class AlertRuleRequest(BaseModel):
    internal_id: str
    metric: str = Field("price", pattern="^(price|ytm|pbr|pe|dividend_yield)$")
    direction: str = Field("below", pattern="^(above|below)$")
    threshold: float
    note: str | None = None


@router.post("/alerts/rules", dependencies=[Depends(RequireFeature("access_alerts"))])
async def api_create_alert_rule(
    req: AlertRuleRequest,
    user_id: int = Depends(require_user_id),
):
    uid = user_id
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == req.internal_id))
        ).scalar_one_or_none()
        stock = None
        if bond is None:
            stock = (
                await session.execute(
                    select(StockORM).where(StockORM.internal_id == req.internal_id)
                )
            ).scalar_one_or_none()
        if bond is None and stock is None:
            raise HTTPException(status_code=404, detail=f"Instrument {req.internal_id} not found")
        allowed = BOND_METRICS if bond is not None else STOCK_METRICS
        if req.metric not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Metric {req.metric!r} not supported for "
                f"{'bond' if bond is not None else 'stock'} {req.internal_id}",
            )
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
async def api_list_alert_rules(user_id: int = Depends(require_user_id)):
    uid = user_id
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


@router.delete("/alerts/rules/{rule_id}", dependencies=[Depends(RequireFeature("access_alerts"))])
async def api_delete_alert_rule(
    rule_id: int,
    user_id: int = Depends(require_user_id),
):
    uid = user_id
    async with session_scope() as session:
        removed = await delete_rule(session, uid, rule_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "ok", "id": rule_id}


@router.get("/alerts/feed", dependencies=[Depends(RequireFeature("access_alerts"))])
async def api_alert_feed(
    user_id: int = Depends(require_user_id),
    limit: int = Query(50, ge=1, le=200),
):
    """Лента сработавших пользовательских алертов (не системных)."""
    uid = user_id
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
