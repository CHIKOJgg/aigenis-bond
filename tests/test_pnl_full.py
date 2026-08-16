"""Comprehensive tests for portfolio.pnl (realized/unrealized, drawdown, sharpe)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from portfolio.pnl import (
    PortfolioPnL,
    PositionPnL,
    compute_daily_returns,
    compute_max_drawdown,
    compute_pnl,
    compute_sharpe,
)


def _tx(internal_id, side, amount, price, executed_at):
    return SimpleNamespace(
        internal_id=internal_id,
        side=side,
        amount=Decimal(str(amount)),
        price=Decimal(str(price)),
        executed_at=executed_at,
    )


def _pos(internal_id, amount):
    return SimpleNamespace(internal_id=internal_id, amount=Decimal(str(amount)))


def _bond(price=100.0, coupon_rate=10.0, currency="BYN", status="active", start=date(2024, 1, 1), maturity=date(2029, 1, 1), coupon_frequency=2):
    return SimpleNamespace(
        price=price,
        coupon_rate=coupon_rate,
        currency=currency,
        status=status,
        start_date=start,
        maturity_date=maturity,
        coupon_frequency=coupon_frequency,
    )


# --------------------------------------------------------------------------- #
# PositionPnL / PortfolioPnL aggregates
# --------------------------------------------------------------------------- #
def test_position_pnl_total():
    p = PositionPnL("B", Decimal("10"), Decimal("5"), Decimal("3"), Decimal("100"), Decimal("90"), Decimal("0.5"))
    assert p.total_pnl() == Decimal("18")


def test_portfolio_pnl_total():
    pf = PortfolioPnL()
    pf.total_realized = Decimal("10")
    pf.total_unrealized = Decimal("5")
    pf.total_coupon_income = Decimal("3")
    assert pf.total_pnl() == Decimal("18")


def test_portfolio_total_return_pct_zero_invested():
    pf = PortfolioPnL()
    assert pf.total_return_pct() == 0.0


# --------------------------------------------------------------------------- #
# FIFO realized P&L
# --------------------------------------------------------------------------- #
def test_realized_pnl_single_buy_sell():
    txs = [
        _tx("B", "buy", 1000, 100, datetime(2024, 1, 1)),
        _tx("B", "sell", 500, 110, datetime(2024, 2, 1)),
    ]
    bonds = {"B": _bond(price=105)}
    res = compute_pnl(txs, [], bonds)
    pos = next(p for p in res.per_bond if p.internal_id == "B")
    # face bought = 1000*100/100 = 1000; face sold = 500*100/110 = 454.545...
    # realized = matched * (110-100)/100 = 454.545 * 0.10 = 45.4545
    assert pos.realized_pnl == pytest.approx(Decimal("45.45"), abs=Decimal("0.01"))


def test_realized_pnl_loss_when_sold_lower():
    txs = [
        _tx("B", "buy", 1000, 100, datetime(2024, 1, 1)),
        _tx("B", "sell", 1000, 90, datetime(2024, 2, 1)),
    ]
    res = compute_pnl(txs, [], {"B": _bond()})
    pos = next(p for p in res.per_bond if p.internal_id == "B")
    # face bought = 1000*100/100 = 1000; face sold = 1000*100/90 = 1111.111...
    # only owned face (1000) matched -> realized = 1000*(90-100)/100 = -100
    assert pos.realized_pnl == pytest.approx(Decimal("-100"), abs=Decimal("0.01"))


def test_fifo_multiple_buys_ordered():
    txs = [
        _tx("B", "buy", 1000, 100, datetime(2024, 1, 1)),
        _tx("B", "buy", 1000, 120, datetime(2024, 1, 2)),
        _tx("B", "sell", 1500, 130, datetime(2024, 2, 1)),
    ]
    res = compute_pnl(txs, [], {"B": _bond(price=130)})
    pos = next(p for p in res.per_bond if p.internal_id == "B")
    # FIFO: sell 1500 money -> face 1500*100/130 = 1153.846
    # matches first buy face 1000 @100: pnl 1000*(130-100)/100 = 300
    # remaining 153.846 from second buy @120: pnl 153.846*(130-120)/100 = 15.385
    # total ~ 315.385
    assert pos.realized_pnl == pytest.approx(Decimal("315.38"), abs=Decimal("0.01"))


def test_sell_without_buys_no_realized():
    txs = [_tx("B", "sell", 500, 110, datetime(2024, 2, 1))]
    res = compute_pnl(txs, [], {"B": _bond()})
    pos = next(p for p in res.per_bond if p.internal_id == "B")
    assert pos.realized_pnl == Decimal("0")


# --------------------------------------------------------------------------- #
# Unrealized / current value
# --------------------------------------------------------------------------- #
def test_unrealized_mark_to_market_dirty_price():
    txs = [_tx("B", "buy", 1000, 100, datetime(2024, 1, 1))]
    bonds = {"B": _bond(price=110, coupon_rate=10, start=date(2024, 1, 1), maturity=date(2029, 1, 1))}
    res = compute_pnl(txs, [_pos("B", 1000)], bonds)
    pos = next(p for p in res.per_bond if p.internal_id == "B")
    # mark at dirty price (110 + accrued) must exceed clean cost basis of 1000
    assert pos.unrealized_pnl > 0
    assert pos.current_value > pos.cost_basis


def test_defaulted_bond_zero_value():
    txs = [_tx("B", "buy", 1000, 100, datetime(2024, 1, 1))]
    bonds = {"B": _bond(price=90, status="defaulted")}
    res = compute_pnl(txs, [], bonds)
    pos = next(p for p in res.per_bond if p.internal_id == "B")
    assert pos.current_value == Decimal("0")


def test_position_without_transactions_marked_at_market():
    pos = _pos("B", 1000)
    bonds = {"B": _bond(price=100, coupon_rate=0)}
    res = compute_pnl([], [pos], bonds)
    p = next(x for x in res.per_bond if x.internal_id == "B")
    # no accrued (coupon 0) -> current_value = 1000 * 100/100 = 1000 == cost
    assert p.current_value == Decimal("1000")
    assert p.unrealized_pnl == Decimal("0")


# --------------------------------------------------------------------------- #
# Coupon income
# --------------------------------------------------------------------------- #
def test_coupon_income_added():
    txs = [_tx("B", "buy", 1000, 100, datetime(2024, 1, 1))]
    res = compute_pnl(txs, [], {"B": _bond()}, coupon_data={"B": Decimal("25")})
    pos = next(p for p in res.per_bond if p.internal_id == "B")
    assert pos.coupon_income == Decimal("25")
    assert res.total_coupon_income == Decimal("25")


# --------------------------------------------------------------------------- #
# FX scaling
# --------------------------------------------------------------------------- #
def test_fx_rates_scale_totals():
    txs = [_tx("B", "buy", 1000, 100, datetime(2024, 1, 1))]
    res_byb = compute_pnl(txs, [], {"B": _bond(currency="BYN")})
    res_usd = compute_pnl(txs, [], {"B": _bond(currency="USD")}, fx_rates={"USD": 3.0})
    byb = next(p for p in res_byb.per_bond if p.internal_id == "B")
    usd = next(p for p in res_usd.per_bond if p.internal_id == "B")
    # value in base of USD bond is 3x the BYN one
    assert usd.current_value == pytest.approx(byb.current_value * 3, abs=Decimal("0.5"))


# --------------------------------------------------------------------------- #
# Daily returns / drawdown / sharpe
# --------------------------------------------------------------------------- #
def test_daily_returns_empty_for_short_curve():
    assert compute_daily_returns([{"date": "2024-01-01", "value": 100}]) == []


def test_daily_returns_computes_pct():
    curve = [
        {"date": "2024-01-01", "value": 100},
        {"date": "2024-01-02", "value": 110},
    ]
    rets = compute_daily_returns(curve)
    assert rets[0]["return_pct"] == pytest.approx(10.0)


def test_max_drawdown_zero_for_rising():
    curve = [
        {"date": "d1", "value": 100},
        {"date": "d2", "value": 120},
        {"date": "d3", "value": 150},
    ]
    assert compute_max_drawdown(curve) == 0.0


def test_max_drawdown_detects_loss():
    curve = [
        {"date": "d1", "value": 100},
        {"date": "d2", "value": 80},
        {"date": "d3", "value": 90},
    ]
    assert compute_max_drawdown(curve) == pytest.approx(20.0)


def test_sharpe_zero_for_flat_returns():
    rets = [{"date": "d1", "return_pct": 1.0}, {"date": "d2", "return_pct": 1.0}]
    assert compute_sharpe(rets) == 0.0


def test_sharpe_positive_for_uptrend():
    rets = [{"date": f"d{i}", "return_pct": 0.5 + i * 0.1} for i in range(10)]
    assert compute_sharpe(rets) > 0
