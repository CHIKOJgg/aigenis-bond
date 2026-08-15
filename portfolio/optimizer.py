"""Portfolio Optimizer: распределение капитала по стратегиям."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from scoring.eligibility import filter_eligible
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
    "Metals++": {"score": 0.3, "yield": 0.1, "safety": 0.6},
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
        nominal=bond.nominal,
        coupon_rate=bond.coupon_rate,
    )


def _apply_strategy_bonuses(b: Bond, strategy: StrategyName, weighted: float) -> float:
    """Specialized overlay weights for Carry Trade, Dollarization and Metals++."""
    # Carry Trade: купонный доход, отсечение дистресса (<70% цены) и дюрация 1-5 лет
    if strategy == "Carry Trade":
        if b.price is not None and float(b.price) < 70.0:
            weighted -= 40.0
        if b.coupon_rate is not None and float(b.coupon_rate) > 0:
            weighted += min(float(b.coupon_rate) * 0.5, 15.0)
        if b.maturity_date:
            days_to_mat = (b.maturity_date - date.today()).days
            if 365 <= days_to_mat <= 1825:
                weighted += 10.0
            elif days_to_mat < 180:
                weighted -= 15.0

    # Dollarization: отбирает облигации в USD или индексированные к USD (ОП-49, ОП-50, Минфин USD)
    elif strategy == "Dollarization":
        name_l = (b.name or "").lower()
        id_l = (b.internal_id or "").lower()
        is_usd = (
            str(b.currency).upper() == "USD"
            or (b.indexation_currency and str(b.indexation_currency).upper() == "USD")
            or any(
                t in name_l
                for t in [
                    "usd",
                    "$",
                    "долл",
                    "op49",
                    "оп49",
                    "op-49",
                    "оп-49",
                    "op50",
                    "оп50",
                    "валют",
                ]
            )
            or any(t in id_l for t in ["usd", "op49", "op50"])
        )
        weighted += 60.0 if is_usd else -50.0

    # Metals++: умная институциональная аллокация в драгметаллы (Gold-Anchor Risk-Parity):
    # Золото 58% (монетарный защитный якорь), Серебро 27% (драйвер роста), Платина 15% (промышленный диверсификатор)
    elif strategy == "Metals++":
        name_l = (b.name or "").lower()
        id_l = (b.internal_id or "").lower()
        issuer_l = (b.issuer or "").lower()
        idx = str(b.indexation_currency).upper() if b.indexation_currency else ""
        is_aig = "айгенис" in issuer_l or "aigenis" in issuer_l or "aigenis" in id_l

        is_gold = (
            idx in ["XAU", "GOLD"]
            or (
                is_aig
                and any(t in name_l for t in ["золот", "gold", "xau", "op35", "оп35", "оп-35"])
            )
            or any(t in id_l for t in ["op35-gold", "aigenis-op35"])
            or ("южуралзолото" in name_l or "селигдар" in name_l)
        )
        is_silver = (
            idx in ["XAG", "SILVER"]
            or (
                is_aig
                and any(t in name_l for t in ["серебр", "silver", "xag", "op43", "оп43", "оп-43"])
            )
            or any(t in id_l for t in ["op43-silver", "aigenis-op43"])
        )
        is_platinum = (
            idx in ["XPT", "PLATINUM"]
            or (
                is_aig
                and any(t in name_l for t in ["платин", "platinum", "xpt", "op42", "оп42", "оп-42"])
            )
            or any(t in id_l for t in ["op42-platinum", "aigenis-op42"])
        )

        if is_gold:
            weighted = 58.0  # Якорный вес 58%
        elif is_silver:
            weighted = 27.0  # Вес 27%
        elif is_platinum:
            weighted = 15.0  # Вес 15%
        else:
            weighted = -50.0  # Штраф для обычных корпоративных и суверенных облигаций

    return weighted


def rank_bonds(bonds: Iterable[Bond], strategy: StrategyName = "Balanced") -> list[BondScore]:
    weights = STRATEGY_WEIGHTS[strategy]
    bond_list = list(bonds)
    # Eligibility gate: дистрибуция, сверхвысокорисковые и аномалии в портфель
    # не попадают ни при какой стратегии (см. scoring/eligibility.py).
    eligible_bonds, _excluded = filter_eligible(bond_list)
    scored: list[BondScore] = []
    for b in eligible_bonds:
        # Пропускаем явно неликвидные или просроченные бумаги
        if b.maturity_date and b.maturity_date <= date.today():
            continue

        s = _bond_to_score(b)
        bd = s.breakdown
        safety_score = max(bd.credit_risk_component + bd.duration_component / 4.0, 0)

        weighted = (
            weights["score"] * s.score
            + weights["yield"] * bd.yield_component
            + weights["safety"] * safety_score
        )

        weighted = _apply_strategy_bonuses(b, strategy, weighted)

        scored.append(
            BondScore(
                internal_id=s.internal_id,
                score=round(max(weighted, 0.0), 2),
                risk_adjusted_score=s.risk_adjusted_score,
                breakdown=s.breakdown,
                computed_at=s.computed_at,
            )
        )
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
    return sum(2.0 + s.breakdown.risk_subtotal * 0.2 for s in scores) / len(scores)


def _sharpe(return_pct: float, vol: float, rf: float = 4.0) -> float:
    if vol <= 0:
        return 0.0
    return (return_pct - rf) / vol


def _sortino(return_pct: float, downside: float, rf: float = 4.0) -> float:
    if downside <= 0:
        return 0.0
    return (return_pct - rf) / downside


def _calmar(return_pct: float, max_drawdown_pct: float) -> float:
    if max_drawdown_pct <= 0:
        return 0.0
    return return_pct / max_drawdown_pct


def _max_drawdown(scores: list[BondScore]) -> float:
    if not scores:
        return 0.0
    return _volatility(scores) * 1.5


def _var_95(scores: list[BondScore]) -> float:
    if len(scores) < 2:
        return 0.0
    return _volatility(scores) * 1.645


def _weighted_stats(
    selected: list[BondScore],
    weights: dict[str, float],
    bonds_by_id: dict[str, Bond],
) -> tuple[float, float, float, float, float]:
    """Realized/expected portfolio stats from actual yields-to-maturity.

    ``expected_return`` is the allocation-weighted mean YTM of the selected
    bonds (a genuine annual-return estimate); ``volatility`` is the weighted
    dispersion of those YTMs; ``max_drawdown_pct`` is the deepest markdown
    among the selected bonds; ``var_95`` is the 5th-percentile YTM shortfall.
    Falls back to score components when YTM data is missing.
    """
    from datetime import date

    ytm_weights: list[tuple[float, float]] = []
    proxy_vols: list[float] = []
    wsum = 0.0
    for s in selected:
        bond = bonds_by_id.get(s.internal_id)
        ytm = float(bond.yield_to_maturity) if bond and bond.yield_to_maturity is not None else None
        w = max(weights.get(s.internal_id, 0.0), 0.0)
        if ytm is not None and ytm > 0:
            ytm_weights.append((ytm, w))
            dur = 3.0
            if bond and bond.maturity_date:
                dur = max((bond.maturity_date - date.today()).days / 365.25, 0.5)
            proxy_vols.append(dur * 1.5 + s.breakdown.risk_subtotal * 0.2)
            wsum += w

    if not ytm_weights or wsum <= 0:
        exp = _expected_return(selected)
        vol = _volatility(selected)
        mdd = _max_drawdown(selected)
        return exp, vol, exp, mdd, _var_95(selected)

    norm_weights = [w / wsum for _, w in ytm_weights]
    avg = sum(y * nw for (y, _), nw in zip(ytm_weights, norm_weights, strict=True))
    vol = sum(v * nw for v, nw in zip(proxy_vols, norm_weights, strict=True))
    mdd = vol * 1.5
    var95 = round(vol * 1.645, 2)
    return avg, vol, avg, mdd, var95


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
            calmar=0.0,
            strategy=prefs.strategy,
        )

    positive_selected = [s for s in selected if s.score > 0]
    if positive_selected:
        selected = positive_selected

    bonds_by_id = {b.internal_id: b for b in bonds}
    total = prefs.initial_capital
    weights = [s.score for s in selected]
    w_sum = sum(w for w in weights) or 1.0
    share_by_id: dict[str, float] = {}
    items: dict[str, Decimal] = {}
    for s, w in zip(selected, weights, strict=True):
        share = w / w_sum
        share_by_id[s.internal_id] = share
        items[s.internal_id] = (total * Decimal(str(share))).quantize(Decimal("0.01"))

    allocated_sum = sum(items.values())
    diff = total - allocated_sum
    if diff != Decimal("0") and selected:
        items[selected[0].internal_id] += diff

    exp_ret, vol, _ret2, mdd, var95 = _weighted_stats(selected, share_by_id, bonds_by_id)
    sharpe = _sharpe(exp_ret, vol)
    downside = max(vol * 0.7, 0.1)
    sortino = _sortino(exp_ret, downside)
    calmar = _calmar(exp_ret, mdd)

    return PortfolioAllocation(
        items=items,
        expected_return=round(exp_ret, 2),
        volatility=round(vol, 2),
        sharpe=round(sharpe, 2),
        sortino=round(sortino, 2),
        max_drawdown=round(mdd, 2),
        var_95=round(var95, 2),
        calmar=round(calmar, 2),
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
