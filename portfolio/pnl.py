"""P&L calculation engine — realized, unrealized, coupon income, equity curve.

Pure computation functions (no I/O) that take position + transaction data and
return structured P&L metrics. The API layer calls these and persists snapshots.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from desk.cashflow import DEFAULT_DAY_COUNT, accrued_interest
from scraper.models import Bond

_Q = Decimal("0.01")


class PositionPnL:
    """Per-bond P&L breakdown."""

    __slots__ = (
        "cost_basis",
        "coupon_income",
        "current_value",
        "internal_id",
        "realized_pnl",
        "unrealized_pnl",
        "weight",
    )

    def __init__(
        self,
        internal_id: str,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal,
        coupon_income: Decimal,
        current_value: Decimal,
        cost_basis: Decimal,
        weight: Decimal,
    ) -> None:
        self.internal_id = internal_id
        self.realized_pnl = realized_pnl.quantize(_Q)
        self.unrealized_pnl = unrealized_pnl.quantize(_Q)
        self.coupon_income = coupon_income.quantize(_Q)
        self.current_value = current_value.quantize(_Q)
        self.cost_basis = cost_basis.quantize(_Q)
        self.weight = weight

    def total_pnl(self) -> Decimal:
        return self.realized_pnl + self.unrealized_pnl + self.coupon_income

    def as_dict(self) -> dict[str, Any]:
        return {
            "internal_id": self.internal_id,
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "coupon_income": float(self.coupon_income),
            "total_pnl": float(self.total_pnl()),
            "current_value": float(self.current_value),
            "cost_basis": float(self.cost_basis),
            "weight": round(float(self.weight), 4),
        }


class PortfolioPnL:
    """Aggregate portfolio P&L."""

    __slots__ = (
        "daily_returns",
        "max_drawdown",
        "per_bond",
        "sharpe",
        "total_coupon_income",
        "total_invested",
        "total_realized",
        "total_unrealized",
        "total_value",
    )

    def __init__(self) -> None:
        self.total_invested = Decimal("0")
        self.total_realized = Decimal("0")
        self.total_unrealized = Decimal("0")
        self.total_coupon_income = Decimal("0")
        self.total_value = Decimal("0")
        self.per_bond: list[PositionPnL] = []
        self.daily_returns: list[dict[str, Any]] = []
        self.max_drawdown = Decimal("0")
        self.sharpe = Decimal("0")

    def total_pnl(self) -> Decimal:
        return self.total_realized + self.total_unrealized + self.total_coupon_income

    def total_return_pct(self) -> float:
        if self.total_invested <= 0:
            return 0.0
        return round(float(self.total_pnl() / self.total_invested * 100), 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_invested": float(self.total_invested),
            "total_value": float(self.total_value),
            "total_realized_pnl": float(self.total_realized),
            "total_unrealized_pnl": float(self.total_unrealized),
            "total_coupon_income": float(self.total_coupon_income),
            "total_pnl": float(self.total_pnl()),
            "total_return_pct": self.total_return_pct(),
            "max_drawdown_pct": round(float(self.max_drawdown), 2),
            "sharpe_ratio": round(float(self.sharpe), 3),
            "per_bond": [p.as_dict() for p in self.per_bond],
            "daily_returns": self.daily_returns,
        }


def compute_pnl(
    transactions: list[Any],
    positions: list[Any],
    bonds_by_id: dict[str, Bond],
    *,
    coupon_data: dict[str, Decimal] | None = None,
    fx_rates: dict[str, float] | None = None,
) -> PortfolioPnL:
    """Compute full P&L from transaction history and current positions.

    Unit conventions (must match the API and Telegram bot): ``amount`` is
    money invested (e.g. 1000 BYN), ``price`` is the bond price as a
    percentage of face (e.g. 98.5). Converting between the two requires the
    ``/100`` factor — a position of 1000 at price 98 buys ~1020 of face.

    Args:
        transactions: list of TransactionORM objects, ordered by executed_at
        positions: list of PortfolioPositionORM objects
        bonds_by_id: dict mapping internal_id -> Bond (for current prices)
        coupon_data: optional dict mapping internal_id -> total coupons received
    """
    result = PortfolioPnL()

    # Group transactions by bond
    txs_by_bond: dict[str, list[Any]] = defaultdict(list)
    for tx in transactions:
        txs_by_bond[tx.internal_id].append(tx)

    # Positions that have no transaction history still hold money: show them
    # with the current price as their mark, cost basis = invested money.
    pos_by_id: dict[str, Any] = {p.internal_id: p for p in positions}
    for iid in pos_by_id:
        txs_by_bond.setdefault(iid, [])

    # Compute per-bond realized P&L using FIFO (lots tracked in face units)
    for iid, txs in txs_by_bond.items():
        buys: list[tuple[Decimal, Decimal]] = []  # (face_amount, price)
        realized = Decimal("0")
        total_invested = Decimal("0")

        for tx in sorted(txs, key=lambda t: t.executed_at):
            price = tx.price if tx.price is not None else Decimal("100")
            if tx.side == "buy":
                face = tx.amount * Decimal("100") / price
                buys.append((face, price))
                total_invested += tx.amount
            elif tx.side == "sell" and buys:
                sell_amount = tx.amount
                sell_price = price
                face_sold = sell_amount * Decimal("100") / sell_price
                remaining = face_sold
                cost_of_sold = Decimal("0")
                while remaining > 0 and buys:
                    buy_face, buy_price = buys[0]
                    matched = min(remaining, buy_face)
                    # P&L in money: matched face * price diff / 100.
                    realized += matched * (sell_price - buy_price) / Decimal("100")
                    cost_of_sold += matched * buy_price / Decimal("100")
                    remaining -= matched
                    if matched >= buy_face:
                        buys.pop(0)
                    else:
                        buys[0] = (buy_face - matched, buy_price)
                total_invested -= cost_of_sold

        # Unrealized P&L for the remaining position (money at market price).
        pos = pos_by_id.get(iid)
        bond = bonds_by_id.get(iid)

        has_price = False
        is_defaulted = False
        current_price_val = Decimal("0")
        if bond:
            is_defaulted = getattr(bond, "status", None) in {"defaulted", "delisted"}
            if getattr(bond, "price", None) is not None:
                has_price = True
                current_price_val = Decimal(str(bond.price))
                if current_price_val < 0:
                    current_price_val = Decimal("0")

        # Accrued interest per 100 of face as of today. Market value is the
        # DIRTY price (clean + accrued): a buyer pays clean plus accrued, so the
        # position is worth face * (clean + accrued)/100, not face*clean/100.
        accrued_pct = Decimal("0")
        if (
            bond is not None
            and getattr(bond, "coupon_rate", None)
            and getattr(bond, "coupon_rate", 0) > 0
            and getattr(bond, "start_date", None) is not None
            and getattr(bond, "maturity_date", None) is not None
        ):
            accrued_pct = Decimal(
                str(
                    accrued_interest(
                        coupon_rate_pct=float(bond.coupon_rate),
                        coupon_frequency=int(bond.coupon_frequency) if bond.coupon_frequency else 2,
                        issue_date=bond.start_date,
                        maturity_date=bond.maturity_date,
                        asof=date.today(),
                        convention=DEFAULT_DAY_COUNT,
                        face=100.0,
                    )
                )
            )

        unrealized = Decimal("0")
        current_value = Decimal("0")

        if pos is not None:
            if txs:
                # Mark the remaining FIFO lots at market: face is tracked in
                # the lots, money value = face * dirty_price / 100. (The /100
                # factor is required — amount is money, price is % of face.)
                remaining_face = sum(lot_face for lot_face, _ in buys)
                cost_basis = total_invested
                if is_defaulted or (has_price and current_price_val == 0):
                    current_value = Decimal("0")
                elif has_price and current_price_val > 0:
                    dirty_price = current_price_val + accrued_pct
                    current_value = remaining_face * dirty_price / Decimal("100")
                else:
                    current_value = cost_basis
            else:
                # No transaction history: only the invested money is known.
                # Mark it at market with a par entry assumption (documented).
                cost_basis = pos.amount
                total_invested = pos.amount
                if is_defaulted or (has_price and current_price_val == 0):
                    current_value = Decimal("0")
                elif has_price and current_price_val > 0:
                    dirty_price = current_price_val + accrued_pct
                    current_value = pos.amount * dirty_price / Decimal("100")
                else:
                    current_value = cost_basis
            unrealized = current_value - cost_basis

        coupon_inc = Decimal("0")
        if coupon_data:
            raw = coupon_data.get(iid)
            if raw is not None:
                coupon_inc = Decimal(str(raw))

        rate = Decimal("1.0")
        if fx_rates and bond and getattr(bond, "currency", None):
            curr = bond.currency.upper()
            rate = Decimal(str(fx_rates.get(curr, 1.0)))

        result.total_invested += total_invested * rate
        result.total_realized += realized * rate
        result.total_unrealized += unrealized * rate
        result.total_coupon_income += coupon_inc * rate
        result.total_value += current_value * rate

        result.per_bond.append(
            PositionPnL(
                internal_id=iid,
                realized_pnl=realized,
                unrealized_pnl=unrealized,
                coupon_income=coupon_inc,
                current_value=current_value,
                cost_basis=total_invested,
                weight=Decimal("0"),
            )
        )

    # Compute weights
    for p in result.per_bond:
        if result.total_value > 0:
            bond = bonds_by_id.get(p.internal_id)
            rate = Decimal("1.0")
            if fx_rates and bond and getattr(bond, "currency", None):
                curr = bond.currency.upper()
                rate = Decimal(str(fx_rates.get(curr, 1.0)))
            p.weight = (p.current_value * rate) / result.total_value

    return result


def compute_daily_returns(equity_curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute daily return % from a list of {date, value} dicts."""
    if len(equity_curve) < 2:
        return []
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]["value"]
        curr = equity_curve[i]["value"]
        ret = (curr - prev) / prev * 100 if prev > 0 else 0.0
        returns.append(
            {
                "date": equity_curve[i]["date"],
                "return_pct": round(ret, 4),
            }
        )
    return returns


def compute_max_drawdown(equity_curve: list[dict[str, Any]]) -> float:
    """Compute maximum drawdown from equity curve."""
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]["value"]
    max_dd = 0.0
    for point in equity_curve:
        val = point["value"]
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
    return round(max_dd * 100, 2)


def compute_sharpe(daily_returns: list[dict[str, Any]], rf_annual: float = 4.0) -> float:
    """Annualized Sharpe ratio from daily returns."""
    if len(daily_returns) < 2:
        return 0.0
    rets = [float(r["return_pct"]) for r in daily_returns]
    avg = sum(rets) / len(rets)
    var = sum((r - avg) ** 2 for r in rets) / len(rets)
    vol = math.sqrt(var)
    if vol <= 0:
        return 0.0
    rf_daily = rf_annual / 252
    return round((avg - rf_daily) / vol * math.sqrt(252), 3)
