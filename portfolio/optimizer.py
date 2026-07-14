"""Portfolio Optimizer: распределение капитала по стратегиям."""

from __future__ import annotations

import math
from collections.abc import Iterable
from decimal import Decimal

from scoring.engine import score_bond
from scoring.models import (
    BondScore,
    PortfolioAllocation,
    StrategyName,
    UserPreferences,
)
from scraper.models import Bond

STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "Conservative": {"score": 0.2, "yield": 0.1, "safety": 0.7},
    "Balanced": {"score": 0.4, "yield": 0.3, "safety": 0.3},
    "Aggressive": {"score": 0.5, "yield": 0.5, "safety": 0.0},
    "Carry Trade": {"score": 0.3, "yield": 0.6, "safety": 0.1},
    "Dollarization": {"score": 0.3, "yield": 0.2, "safety": 0.5},
    "Maximum Reward/Risk": {"score": 1.0, "yield": 0.0, "safety": 0.0},
}


def _bond_to_score(bond: Bond) -> BondScore:
    return score_bond(
        internal_id=bond.internal_id,
        yield_to_maturity=bond.yield_to_maturity,
        currency=str(bond.currency),
        maturity_date=bond.maturity_date,
        status=str(bond.status),
        issuer=bond.issuer,
        price=bond.price,
    )


def rank_bonds(bonds: Iterable[Bond], strategy: StrategyName = "Balanced") -> list[BondScore]:
    weights = STRATEGY_WEIGHTS[strategy]
    scored: list[BondScore] = []
    for b in bonds:
        s = _bond_to_score(b)
        bd = s.breakdown
        safety_score = max(bd.credit_risk_component + bd.duration_component / 4.0, 0)
        weighted = (
            weights["score"] * s.score
            + weights["yield"] * bd.yield_component
            + weights["safety"] * safety_score
        )
        s.score = round(weighted, 2)
        scored.append(s)
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored


def _expected_return(scores: list[BondScore]) -> float:
    """Грубая оценка ожидаемой годовой доходности через yield_component."""
    if not scores:
        return 0.0
    total = sum(max(s.breakdown.yield_component, 0) for s in scores)
    return total / len(scores)


def _volatility(scores: list[BondScore]) -> float:
    if not scores:
        return 0.0
    avg = _expected_return(scores)
    var = sum((max(s.breakdown.yield_component, 0) - avg) ** 2 for s in scores) / len(scores)
    return math.sqrt(var)


def _sharpe(return_pct: float, vol: float, rf: float = 4.0) -> float:
    if vol <= 0:
        return 0.0
    return (return_pct - rf) / vol


def _sortino(return_pct: float, downside: float, rf: float = 4.0) -> float:
    if downside <= 0:
        return 0.0
    return (return_pct - rf) / downside


def _max_drawdown(scores: list[BondScore]) -> float:
    if not scores:
        return 0.0
    worst = min(s.breakdown.yield_component for s in scores)
    return max(-worst, 0.0)


def _var_95(scores: list[BondScore]) -> float:
    if len(scores) < 2:
        return 0.0
    sorted_ytm = sorted(s.breakdown.yield_component for s in scores)
    idx = max(int(len(sorted_ytm) * 0.05), 0)
    return abs(sorted_ytm[idx])


def allocate(
    bonds: list[Bond],
    prefs: UserPreferences,
    *,
    top_n: int = 10,
) -> PortfolioAllocation:
    """Распределение капитала по топ-N облигациям под стратегию пользователя."""
    ranked = rank_bonds(bonds, strategy=prefs.strategy)
    selected = ranked[:top_n]
    if not selected:
        return PortfolioAllocation(
            items={},
            expected_return=0.0,
            volatility=0.0,
            sharpe=0.0,
            sortino=0.0,
            max_drawdown=0.0,
            var_95=0.0,
            strategy=prefs.strategy,
        )

    total = prefs.initial_capital
    weights = [s.score for s in selected]
    w_sum = sum(max(w, 0.01) for w in weights)
    items: dict[str, Decimal] = {}
    for s, w in zip(selected, weights, strict=True):
        share = Decimal(str(max(w, 0.01) / w_sum))
        items[s.internal_id] = (total * share).quantize(Decimal("0.01"))

    exp_ret = _expected_return(selected)
    vol = _volatility(selected)
    sharpe = _sharpe(exp_ret, vol)
    downside = max(vol * 0.7, 0.1)
    sortino = _sortino(exp_ret, downside)
    mdd = _max_drawdown(selected)
    var95 = _var_95(selected)

    return PortfolioAllocation(
        items=items,
        expected_return=round(exp_ret, 2),
        volatility=round(vol, 2),
        sharpe=round(sharpe, 2),
        sortino=round(sortino, 2),
        max_drawdown=round(mdd, 2),
        var_95=round(var95, 2),
        strategy=prefs.strategy,
    )


def rebalance(
    current: dict[str, Decimal],
    bonds: list[Bond],
    prefs: UserPreferences,
    *,
    top_n: int = 10,
) -> tuple[PortfolioAllocation, dict[str, Decimal]]:
    """Сравнить текущее распределение с целевым; вернуть дельты."""
    target = allocate(bonds, prefs, top_n=top_n)
    deltas: dict[str, Decimal] = {}
    all_ids = set(target.items) | set(current)
    for iid in all_ids:
        new = target.items.get(iid, Decimal("0"))
        old = current.get(iid, Decimal("0"))
        if new != old:
            deltas[iid] = new - old
    return target, deltas
