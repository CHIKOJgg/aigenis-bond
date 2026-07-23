"""Backtesting engine — simulate strategy performance over historical data.

Simulates buy/sell decisions based on strategy rules applied to historical
bond data, tracks equity curve, and computes performance metrics.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from scraper.models import Bond
from scraper.orm import BondHistoryORM

_Q = Decimal("0.01")


class BacktestResult:
    __slots__ = (
        "strategy",
        "start_date",
        "end_date",
        "initial_capital",
        "final_value",
        "total_return_pct",
        "annual_return_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "equity_curve",
        "positions_history",
    )

    def __init__(self) -> None:
        self.strategy = ""
        self.start_date = date.min
        self.end_date = date.min
        self.initial_capital = Decimal("0")
        self.final_value = Decimal("0")
        self.total_return_pct = Decimal("0")
        self.annual_return_pct: Decimal | None = None
        self.sharpe_ratio: Decimal | None = None
        self.max_drawdown_pct: Decimal | None = None
        self.equity_curve: list[dict] = []
        self.positions_history: list[dict] = []

    def as_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": float(self.initial_capital),
            "final_value": float(self.final_value),
            "total_return_pct": round(float(self.total_return_pct), 2),
            "annual_return_pct": round(float(self.annual_return_pct), 2) if self.annual_return_pct is not None else None,
            "sharpe_ratio": round(float(self.sharpe_ratio), 3) if self.sharpe_ratio is not None else None,
            "max_drawdown_pct": round(float(self.max_drawdown_pct), 2) if self.max_drawdown_pct is not None else None,
            "equity_curve": self.equity_curve,
            "positions_history": self.positions_history,
        }


def _score_bond_for_strategy(
    bond: Bond,
    strategy: str,
    price_history: list[tuple[date, Decimal, Decimal]] | None = None,
) -> float:
    """Score a bond for a given strategy. Higher = better."""
    ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity else 0.0
    price = float(bond.price) if bond.price else 100.0

    if strategy == "Conservative":
        return ytm * 0.3 + (100.0 - price) * 0.01
    elif strategy == "Aggressive":
        return ytm * 0.8 + (100.0 - price) * 0.005
    elif strategy == "Carry Trade":
        coupon = float(bond.coupon_rate) if bond.coupon_rate else 0.0
        return coupon * 0.6 + ytm * 0.4
    elif strategy == "Dollarization":
        currency_bonus = 5.0 if str(bond.currency).upper() == "USD" else 0.0
        return ytm * 0.5 + currency_bonus
    else:
        return ytm * 0.5 + (100.0 - price) * 0.005


def run_backtest(
    bonds: list[Bond],
    history_by_bond: dict[str, list[BondHistoryORM]],
    *,
    strategy: str = "Balanced",
    initial_capital: Decimal = Decimal("10000"),
    start_date: date | None = None,
    end_date: date | None = None,
    top_n: int = 5,
    rebalance_days: int = 30,
) -> BacktestResult:
    """Run a historical backtest simulation.

    Args:
        bonds: current bond catalog
        history_by_bond: dict internal_id -> list of BondHistoryORM (historical prices)
        strategy: allocation strategy name
        initial_capital: starting capital
        start_date: backtest start (defaults to earliest history)
        end_date: backtest end (defaults to latest history)
        top_n: number of bonds to hold
        rebalance_days: how often to rebalance (in calendar days)
    """
    result = BacktestResult()
    result.strategy = strategy
    result.initial_capital = initial_capital

    # Collect all available dates
    all_dates: set[date] = set()
    for iid, history in history_by_bond.items():
        for h in history:
            all_dates.add(h.date)

    if not all_dates:
        result.end_date = result.start_date
        result.final_value = initial_capital
        result.equity_curve = [{"date": date.today().isoformat(), "value": float(initial_capital)}]
        return result

    sorted_dates = sorted(all_dates)
    if start_date:
        result.start_date = start_date
    else:
        result.start_date = sorted_dates[0]
    if end_date:
        result.end_date = end_date
    else:
        result.end_date = sorted_dates[-1]

    # Build price lookup: (internal_id, date) -> (price, ytm)
    price_lookup: dict[tuple[str, date], tuple[Decimal, Decimal]] = {}
    for iid, history in history_by_bond.items():
        for h in history:
            if h.price is not None:
                price_lookup[(iid, h.date)] = (h.price, h.yield_ or Decimal("0"))

    # Build bonds by id
    bonds_by_id = {b.internal_id: b for b in bonds}

    # Simulate
    capital = initial_capital
    holdings: dict[str, Decimal] = {}  # internal_id -> amount held
    equity_curve: list[dict] = []
    positions_history: list[dict] = []
    last_rebalance = result.start_date - timedelta(days=rebalance_days)
    peak = capital

    for current_date in sorted_dates:
        if current_date < result.start_date:
            continue
        if current_date > result.end_date:
            break

        # Update portfolio value
        total_value = capital
        for iid, amount in holdings.items():
            price_data = price_lookup.get((iid, current_date))
            if price_data and price_data[0] > 0:
                total_value += amount * price_data[0]
            elif iid in bonds_by_id and bonds_by_id[iid].price:
                total_value += amount * bonds_by_id[iid].price

        equity_curve.append({
            "date": current_date.isoformat(),
            "value": round(float(total_value), 2),
        })

        # Check if it's time to rebalance
        days_since = (current_date - last_rebalance).days
        if days_since >= rebalance_days:
            last_rebalance = current_date

            # Score available bonds
            scored = []
            for b in bonds:
                if b.price and b.price > 0:
                    s = _score_bond_for_strategy(b, strategy)
                    scored.append((b.internal_id, s))
            scored.sort(key=lambda x: x[1], reverse=True)
            selected = scored[:top_n]

            # Sell everything
            capital_after_sell = capital
            for iid, amount in holdings.items():
                price_data = price_lookup.get((iid, current_date))
                if price_data:
                    capital_after_sell += amount * price_data[0]
            holdings = {}
            capital = capital_after_sell

            # Buy new portfolio
            if selected and capital > 0:
                per_bond = capital / Decimal(len(selected))
                for iid, _score in selected:
                    price_data = price_lookup.get((iid, current_date))
                    if price_data and price_data[0] > 0:
                        amount = (per_bond / price_data[0]).quantize(_Q)
                        holdings[iid] = amount
                        capital -= amount * price_data[0]

            positions_history.append({
                "date": current_date.isoformat(),
                "holdings": {iid: float(amt) for iid, amt in holdings.items()},
                "capital": round(float(capital), 2),
            })

    # Final value
    final_value = capital
    for iid, amount in holdings.items():
        price_data = price_lookup.get((iid, result.end_date))
        if price_data and price_data[0] > 0:
            final_value += amount * price_data[0]

    result.final_value = final_value.quantize(_Q)
    if initial_capital > 0:
        result.total_return_pct = ((final_value - initial_capital) / initial_capital * 100).quantize(_Q)

    # Annualized return
    years = (result.end_date - result.start_date).days / 365.25
    if years > 0 and initial_capital > 0:
        ann = ((float(final_value) / float(initial_capital)) ** (1 / years) - 1) * 100
        result.annual_return_pct = Decimal(str(round(ann, 2)))

    # Max drawdown
    if equity_curve:
        peak_val = equity_curve[0]["value"]
        max_dd = 0.0
        for pt in equity_curve:
            if pt["value"] > peak_val:
                peak_val = pt["value"]
            dd = (peak_val - pt["value"]) / peak_val if peak_val > 0 else 0
            max_dd = max(max_dd, dd)
        result.max_drawdown_pct = Decimal(str(round(max_dd * 100, 2)))

    # Sharpe
    if len(equity_curve) > 1:
        daily_rets = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]["value"]
            curr = equity_curve[i]["value"]
            if prev > 0:
                daily_rets.append((curr - prev) / prev)
        if daily_rets:
            avg = sum(daily_rets) / len(daily_rets)
            var = sum((r - avg) ** 2 for r in daily_rets) / len(daily_rets)
            vol = math.sqrt(var)
            if vol > 0:
                sharpe = (avg - 0.04 / 252) / vol * math.sqrt(252)
                result.sharpe_ratio = Decimal(str(round(sharpe, 3)))

    result.equity_curve = equity_curve
    result.positions_history = positions_history
    return result
