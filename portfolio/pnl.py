"""P&L calculation engine — realized, unrealized, coupon income, equity curve.

Pure computation functions (no I/O) that take position + transaction data and
return structured P&L metrics. The API layer calls these and persists snapshots.
"""

from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal

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

    def as_dict(self) -> dict:
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
        self.daily_returns: list[dict] = []
        self.max_drawdown = Decimal("0")
        self.sharpe = Decimal("0")

    def total_pnl(self) -> Decimal:
        return self.total_realized + self.total_unrealized + self.total_coupon_income

    def total_return_pct(self) -> float:
        if self.total_invested <= 0:
            return 0.0
        return round(float(self.total_pnl() / self.total_invested * 100), 2)

    def as_dict(self) -> dict:
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
    transactions: list,
    positions: list,
    bonds_by_id: dict[str, Bond],
    *,
    coupon_data: dict[str, Decimal] | None = None,
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
    txs_by_bond: dict[str, list] = defaultdict(list)
    for tx in transactions:
        txs_by_bond[tx.internal_id].append(tx)

    # Positions that have no transaction history still hold money: show them
    # with the current price as their mark, cost basis = invested money.
    pos_by_id: dict[str, object] = {p.internal_id: p for p in positions}
    for iid in pos_by_id:
        txs_by_bond.setdefault(iid, [])

    # Compute per-bond realized P&L using FIFO (lots tracked in face units)
    for iid, txs in txs_by_bond.items():
        buys: list[tuple[Decimal, Decimal]] = []  # (face_amount, price)
        realized = Decimal("0")
        total_invested = Decimal("0")

        for tx in sorted(txs, key=lambda t: t.executed_at):
            price = tx.price or Decimal("100")
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
        current_price_val = bond.price if bond and bond.price and bond.price > 0 else Decimal("0")
        unrealized = Decimal("0")
        current_value = Decimal("0")

        if pos is not None:
            if txs:
                # Mark the remaining FIFO lots at market: face is tracked in
                # the lots, money value = face * price / 100. (The /100 factor
                # is required — amount is money, price is % of face.)
                remaining_face = sum(lot_face for lot_face, _ in buys)
                current_value = (
                    remaining_face * current_price_val / Decimal("100")
                    if current_price_val > 0
                    else Decimal("0")
                )
                cost_basis = total_invested
            else:
                # No transaction history: only the invested money is known.
                # Mark it at market with a par entry assumption (documented).
                if current_price_val > 0:
                    current_value = pos.amount * current_price_val / Decimal("100")
                cost_basis = pos.amount
                total_invested = pos.amount
            unrealized = current_value - cost_basis

        coupon_inc = coupon_data.get(iid, Decimal("0")) if coupon_data else Decimal("0")

        result.total_invested += total_invested
        result.total_realized += realized
        result.total_unrealized += unrealized
        result.total_coupon_income += coupon_inc
        result.total_value += current_value

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
            p.weight = p.current_value / result.total_value

    return result


def compute_daily_returns(equity_curve: list[dict]) -> list[dict]:
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


def compute_max_drawdown(equity_curve: list[dict]) -> float:
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


def compute_sharpe(daily_returns: list[dict], rf_annual: float = 4.0) -> float:
    """Annualized Sharpe ratio from daily returns."""
    if len(daily_returns) < 2:
        return 0.0
    rets = [r["return_pct"] for r in daily_returns]
    avg = sum(rets) / len(rets)
    var = sum((r - avg) ** 2 for r in rets) / len(rets)
    vol = math.sqrt(var)
    if vol <= 0:
        return 0.0
    rf_daily = rf_annual / 252
    return round((avg - rf_daily) / vol * math.sqrt(252), 3)
