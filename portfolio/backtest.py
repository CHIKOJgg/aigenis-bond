"""Backtesting engine — simulate strategy performance over historical data.

Simulates buy/sell decisions based on strategy rules applied to historical
bond data, tracks equity curve, and computes performance metrics.

All decisions are made on information available at the decision date:
prices/yields come from the history rows on or before that date, never from
the bond's current (future) state, to avoid lookahead bias.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from scraper.models import Bond
from scraper.orm import BondHistoryORM

_Q = Decimal("0.01")

KNOWN_STRATEGIES = {"Balanced", "Conservative", "Aggressive", "Carry Trade", "Dollarization"}


class BacktestResult:
    __slots__ = (
        "annual_return_pct",
        "end_date",
        "equity_curve",
        "final_value",
        "initial_capital",
        "max_drawdown_pct",
        "positions_history",
        "sharpe_ratio",
        "start_date",
        "strategy",
        "total_return_pct",
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
        self.equity_curve: list[dict[str, Any]] = []
        self.positions_history: list[dict[str, Any]] = []

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": float(self.initial_capital),
            "final_value": float(self.final_value),
            "total_return_pct": round(float(self.total_return_pct), 2),
            "annual_return_pct": round(float(self.annual_return_pct), 2)
            if self.annual_return_pct is not None
            else None,
            "sharpe_ratio": round(float(self.sharpe_ratio), 3)
            if self.sharpe_ratio is not None
            else None,
            "max_drawdown_pct": round(float(self.max_drawdown_pct), 2)
            if self.max_drawdown_pct is not None
            else None,
            "equity_curve": self.equity_curve,
            "positions_history": self.positions_history,
        }


def _score_bond_for_strategy(
    bond: Bond,
    strategy: str,
    price: Decimal | None = None,
    ytm: Decimal | None = None,
) -> float:
    """Score a bond for a given strategy. Higher = better.

    Uses the historical ``price``/``ytm`` observed at the decision date when
    available; otherwise falls back to the bond's current catalog values.
    """
    ytm_f = (
        float(ytm) if ytm else (float(bond.yield_to_maturity) if bond.yield_to_maturity else 0.0)
    )
    price_f = float(price) if price else (float(bond.price) if bond.price else 100.0)

    if strategy == "Conservative":
        return ytm_f * 0.3 + (100.0 - price_f) * 0.01
    elif strategy == "Aggressive":
        return ytm_f * 0.8 + (100.0 - price_f) * 0.005
    elif strategy == "Carry Trade":
        coupon = float(bond.coupon_rate) if bond.coupon_rate else 0.0
        return coupon * 0.6 + ytm_f * 0.4
    elif strategy == "Dollarization":
        currency_bonus = 5.0 if str(bond.currency).upper() == "USD" else 0.0
        return ytm_f * 0.5 + currency_bonus
    else:
        return ytm_f * 0.5 + (100.0 - price_f) * 0.005


def _build_price_rows(
    history_by_bond: dict[str, list[BondHistoryORM]],
) -> dict[str, list[tuple[date, Decimal, Decimal]]]:
    """Per-bond chronologically sorted ``[(date, price, ytm)]`` rows."""
    rows: dict[str, list[tuple[date, Decimal, Decimal]]] = {}
    for iid, history in history_by_bond.items():
        cleaned = []
        for h in history:
            if h.price is not None:
                cleaned.append((h.date, h.price, h.yield_ or Decimal("0")))
        cleaned.sort(key=lambda r: r[0])
        if cleaned:
            rows[iid] = cleaned
    return rows


def _snapshot_on_or_before(
    rows: dict[str, list[tuple[date, Decimal, Decimal]]],
    iid: str,
    day: date,
) -> tuple[Decimal, Decimal] | None:
    """Last known (price, ytm) for the bond at or before ``day``."""
    series = rows.get(iid)
    if not series:
        return None
    idx = bisect_right(series, day, key=lambda r: r[0])
    if idx == 0:
        return None
    return series[idx - 1][1], series[idx - 1][2]


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

    Raises:
        ValueError: if ``strategy`` is unknown, or ``start_date`` > ``end_date``.
    """
    if strategy not in KNOWN_STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy}")
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    if rebalance_days < 1:
        raise ValueError("rebalance_days must be at least 1")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must not be after end_date")

    result = BacktestResult()
    result.strategy = strategy
    result.initial_capital = initial_capital

    # Collect all available dates
    all_dates: set[date] = set()
    for history in history_by_bond.values():
        for h in history:
            all_dates.add(h.date)

    if not all_dates:
        result.start_date = start_date or date.today()
        result.end_date = end_date or date.today()
        result.final_value = initial_capital
        result.equity_curve = [{"date": date.today().isoformat(), "value": float(initial_capital)}]
        return result

    sorted_dates = sorted(all_dates)
    result.start_date = start_date if start_date else sorted_dates[0]
    result.end_date = end_date if end_date else sorted_dates[-1]

    price_rows = _build_price_rows(history_by_bond)

    def mark_price(iid: str, day: date) -> Decimal | None:
        """Price strictly at-or-before ``day``; None if unknown.

        Never falls back to the bond's *current* catalog price — that would
        leak future information into a historical simulation (lookahead bias).
        A None price simply means the position cannot be marked on this date.
        """
        snap = _snapshot_on_or_before(price_rows, iid, day)
        if snap:
            return snap[0]
        return None

    # Simulate
    capital = initial_capital
    holdings: dict[str, Decimal] = {}  # internal_id -> amount held
    equity_curve: list[dict[str, Any]] = []
    positions_history: list[dict[str, Any]] = []
    last_rebalance = result.start_date - timedelta(days=rebalance_days)

    for current_date in sorted_dates:
        if current_date < result.start_date:
            continue
        if current_date > result.end_date:
            break

        # Update portfolio value (last known prices only — no future data).
        total_value = capital
        for iid, amount in holdings.items():
            px = mark_price(iid, current_date)
            if px and px > 0:
                total_value += amount * px

        equity_curve.append(
            {
                "date": current_date.isoformat(),
                "value": round(float(total_value), 2),
            }
        )

        # Check if it's time to rebalance
        days_since = (current_date - last_rebalance).days
        if days_since >= rebalance_days:
            last_rebalance = current_date

            # Score available bonds using data known at this date. A bond with
            # no historical price at the decision date is never scored with its
            # current catalog price — that would leak future information.
            scored = []
            for b in bonds:
                snap = _snapshot_on_or_before(price_rows, b.internal_id, current_date)
                if snap is not None:
                    score = _score_bond_for_strategy(b, strategy, price=snap[0], ytm=snap[1])
                else:
                    continue
                scored.append((b.internal_id, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            selected = scored[:top_n]

            # Sell everything at the last known price (money must not vanish).
            capital_after_sell = capital
            for iid, amount in holdings.items():
                px = mark_price(iid, current_date)
                if px and px > 0:
                    capital_after_sell += amount * px
            holdings = {}
            capital = capital_after_sell

            # Buy new portfolio
            if selected and capital > 0:
                per_bond = capital / Decimal(len(selected))
                for iid, _score in selected:
                    px = mark_price(iid, current_date)
                    if px and px > 0:
                        amount = (per_bond / px).quantize(_Q)
                        holdings[iid] = amount
                        capital -= amount * px

            positions_history.append(
                {
                    "date": current_date.isoformat(),
                    "holdings": {iid: float(amt) for iid, amt in holdings.items()},
                    "capital": round(float(capital), 2),
                }
            )

    # Final value at last known prices on/before end_date.
    final_value = capital
    for iid, amount in holdings.items():
        px = mark_price(iid, result.end_date)
        if px and px > 0:
            final_value += amount * px

    result.final_value = final_value.quantize(_Q)
    if initial_capital > 0:
        result.total_return_pct = (
            (final_value - initial_capital) / initial_capital * 100
        ).quantize(_Q)

    # Annualized return
    years = (result.end_date - result.start_date).days / 365.25
    if years > 0 and initial_capital > 0 and final_value > 0:
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
