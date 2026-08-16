"""User-defined portfolio optimizer & calculator.

Generalizes the fixed-strategy engine (``portfolio.optimizer``) so a user can
supply *their own* basket of bonds and obtain real YTM-based portfolio metrics
plus an allocation chosen by an objective (equal weight / min variance /
risk parity / max Sharpe). No strategy enum, no hardcoded bond universe.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

from desk.ytm import honest_yield, to_price_pct

RISK_FREE_PCT = 4.0

VALID_OBJECTIVES = (
    "equal_weight",
    "min_variance",
    "risk_parity",
    "max_sharpe",
)


def _as_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def bond_ytm(bond: Any) -> float:
    """Real (honest) YTM for a bond row, falling back to 0% when unknown."""
    raw = _as_float(getattr(bond, "yield_to_maturity", None), default=float("nan"))
    ytm = honest_yield(
        stored_ytm_pct=None if raw != raw else raw,  # keep None when NaN
        coupon_rate_pct=_as_float(getattr(bond, "coupon_rate", None), None),
        indexation_currency=getattr(bond, "indexation_currency", None),
    )
    return ytm if ytm is not None else 0.0


def bond_duration(bond: Any) -> float:
    """Rate-risk duration: cashflow-based modified duration, else time-to-maturity."""
    try:
        from desk.duration import bond_modified_duration

        d = bond_modified_duration(bond)
        if d is not None and d > 0:
            return d
    except Exception:
        pass
    md = getattr(bond, "maturity_date", None)
    if md:
        return max((md - date.today()).days / 365.25, 0.5)
    return 3.0


def bond_current_yield(bond: Any) -> float:
    cy = getattr(bond, "current_yield", None)
    if cy is not None:
        return _as_float(cy)
    coupon = _as_float(getattr(bond, "coupon_rate", None), None)
    price = _as_float(getattr(bond, "price", None), None)
    if coupon is not None and price:
        try:
            return coupon / (price / 100.0)
        except (ZeroDivisionError, TypeError):
            return 0.0
    return 0.0


def bond_volatility(bond: Any) -> float:
    """Rate-risk proxy: duration-driven annualized volatility (no history needed)."""
    return max(bond_duration(bond) * 1.5, 0.5)


def optimize_weights(
    bonds: Iterable[Any],
    objective: str = "equal_weight",
    risk_free: float = RISK_FREE_PCT,
) -> dict[str, float]:
    """Return ``{internal_id: weight}`` (weights sum to 1) for a chosen objective."""
    scored = [(b, bond_ytm(b)) for b in bonds if bond_ytm(b) >= 0]
    if not scored:
        return {}
    if objective not in VALID_OBJECTIVES:
        objective = "equal_weight"

    if objective == "equal_weight":
        n = len(scored)
        return {b.internal_id: 1.0 / n for b, _ in scored}

    if objective == "min_variance":
        raw = {b.internal_id: 1.0 / (bond_volatility(b) ** 2) for b, _ in scored}
    elif objective == "risk_parity":
        raw = {b.internal_id: 1.0 / bond_volatility(b) for b, _ in scored}
    else:  # max_sharpe
        raw = {
            b.internal_id: max(bond_ytm(b) - risk_free, 0.0) / (bond_volatility(b) ** 2)
            for b, _ in scored
        }

    total = sum(raw.values()) or 1.0
    return {iid: w / total for iid, w in raw.items()}


def compute_portfolio_metrics(
    bonds: Sequence[Any],
    weights: Mapping[str, float],
) -> dict[str, Any]:
    """Aggregate metrics for a basket given fractional ``weights`` per internal_id."""
    total_w = sum(weights.get(getattr(b, "internal_id", ""), 0.0) for b in bonds) or 1.0
    norm: dict[str, float] = {}
    for b in bonds:
        iid = b.internal_id
        w = weights.get(iid, 0.0) / total_w
        norm[iid] = w

    ytms: list[tuple[float, float]] = []
    vols: list[tuple[float, float]] = []
    for b in bonds:
        w = norm[b.internal_id]
        if w <= 0:
            continue
        ytms.append((bond_ytm(b), w))
        vols.append((bond_volatility(b), w))

    exp = sum(y * w for y, w in ytms)
    vol = sum(v * w for v, w in vols)
    sharpe = (exp - RISK_FREE_PCT) / vol if vol > 0 else 0.0
    downside = max(vol * 0.7, 0.1)
    sortino = (exp - RISK_FREE_PCT) / downside if downside > 0 else 0.0
    mdd = vol * 1.5
    var95 = vol * 1.645
    calmar = exp / mdd if mdd > 0 else 0.0
    wdur = sum(bond_duration(b) * norm[b.internal_id] for b in bonds)
    wcy = sum(bond_current_yield(b) * norm[b.internal_id] for b in bonds)

    conc: dict[str, float] = {}
    for b in bonds:
        iss = getattr(b, "issuer", None) or "Unknown"
        conc[iss] = conc.get(iss, 0.0) + norm[b.internal_id]
    concentration = {k: round(v * 100, 2) for k, v in sorted(conc.items(), key=lambda x: -x[1])}

    return {
        "expected_return": round(exp, 2),
        "volatility": round(vol, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "var_95": round(var95, 2),
        "max_drawdown": round(mdd, 2),
        "calmar": round(calmar, 2),
        "weighted_duration": round(wdur, 2),
        "weighted_current_yield": round(wcy, 2),
        "concentration_by_issuer": concentration,
    }


def calculate_fixed(
    bonds: Sequence[Any],
    holdings: Sequence[tuple[str, float]],
) -> dict[str, Any]:
    """Calculator: metrics for a basket with user-supplied ``(internal_id, amount)``."""
    amount_by_id = dict(holdings)
    total = sum(amount_by_id.get(b.internal_id, 0.0) for b in bonds) or 1.0
    weights = {b.internal_id: amount_by_id.get(b.internal_id, 0.0) / total for b in bonds}
    metrics = compute_portfolio_metrics(bonds, weights)
    breakdown = []
    for b in bonds:
        amt = amount_by_id.get(b.internal_id, 0.0)
        if amt <= 0:
            continue
        breakdown.append(
            {
                "internal_id": b.internal_id,
                "name": getattr(b, "name", None) or b.internal_id,
                "issuer": getattr(b, "issuer", None),
                "currency": getattr(b, "currency", None),
                "amount": round(amt, 2),
                "weight_pct": round((amt / total) * 100, 2),
                "ytm": bond_ytm(b),
                "duration_years": bond_duration(b),
                "current_yield": bond_current_yield(b),
            }
        )
    metrics["holdings"] = breakdown
    return metrics


def discrete_allocate(  # noqa: C901
    bonds: Sequence[Any],
    weights: Mapping[str, float],
    capital: float,
    currency: str = "BYN",
    label: str = "Пользовательский портфель",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Greedy lot allocation + exchange order tickets for a chosen basket."""
    candidates: list[dict[str, Any]] = []
    for b in bonds:
        w = weights.get(b.internal_id, 0.0)
        if w <= 0:
            continue
        raw_price = getattr(b, "price", None)
        nominal = _as_float(getattr(b, "nominal", None), 1000.0) or 1000.0
        price_pct = to_price_pct(raw_price, nominal) if raw_price is not None else 100.0
        price_pct = price_pct if price_pct and price_pct > 0 else 100.0
        price_money = (price_pct / 100.0) * nominal if nominal > 0 else price_pct

        accrued = 0.0
        md = getattr(b, "maturity_date", None)
        cr = getattr(b, "coupon_rate", None)
        cf = getattr(b, "coupon_frequency", None) or 2
        sd = getattr(b, "start_date", None)
        if cr is not None and md is not None:
            try:
                from desk.cashflow import accrued_interest

                accrued = accrued_interest(
                    coupon_rate_pct=_as_float(cr),
                    coupon_frequency=int(cf),
                    issue_date=sd,
                    maturity_date=md,
                    asof=date.today(),
                    face=nominal,
                )
            except Exception:
                accrued = 0.0

        dirty = price_money + accrued
        if dirty <= 0:
            continue
        candidates.append(
            {
                "internal_id": b.internal_id,
                "bond": b,
                "dirty_price": dirty,
                "weight": w,
                "lots": 0,
            }
        )

    if not candidates:
        return [], []

    total_w = sum(c["weight"] for c in candidates) or 1.0
    for c in candidates:
        ideal_amt = capital * (c["weight"] / total_w)
        c["lots"] = int(ideal_amt // c["dirty_price"])

    remaining = capital - sum(c["lots"] * c["dirty_price"] for c in candidates)
    ranked = sorted(candidates, key=lambda x: x["weight"], reverse=True)
    if sum(c["lots"] for c in candidates) == 0:
        for c in ranked:
            if remaining >= c["dirty_price"]:
                c["lots"] = 1
                remaining -= c["dirty_price"]
    else:
        for c in ranked:
            while remaining >= c["dirty_price"]:
                c["lots"] += 1
                remaining -= c["dirty_price"]

    allocated = [c for c in candidates if c["lots"] > 0]
    actual_cost = sum(c["lots"] * c["dirty_price"] for c in allocated) or capital

    items: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    for c in allocated:
        bond = c["bond"]
        pos_cost = round(c["lots"] * c["dirty_price"], 2)
        real_weight = round((pos_cost / actual_cost) * 100.0, 1)
        name = getattr(bond, "name", None) or c["internal_id"]
        ytm = bond_ytm(bond)
        items.append(
            {
                "internal_id": c["internal_id"],
                "name": name,
                "issuer": getattr(bond, "issuer", None) or "Aigenis",
                "isin": getattr(bond, "isin", None) or c["internal_id"],
                "amount": pos_cost,
                "currency": getattr(bond, "currency", None) or currency,
                "weight_pct": real_weight,
                "lots": c["lots"],
                "ytm": ytm,
                "duration_years": bond_duration(bond),
                "current_yield": bond_current_yield(bond),
            }
        )
        orders.append(
            {
                "action": "BUY",
                "internal_id": c["internal_id"],
                "name": name,
                "lots": c["lots"],
                "est_cost": pos_cost,
                "currency": getattr(bond, "currency", None) or currency,
                "rationale": f"Целевой вес {real_weight}% в рамках цели '{label}'",
            }
        )
    return items, orders
