"""Comprehensive tests for portfolio.backtest (pure strategy-scoring helpers + engine)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from portfolio.backtest import (
    KNOWN_STRATEGIES,
    BacktestResult,
    _build_price_rows,
    _score_bond_for_strategy,
    _snapshot_on_or_before,
    run_backtest,
)


def _bond(internal_id, ytm=10.0, price=100.0, currency="BYN", coupon=10.0):
    return SimpleNamespace(
        internal_id=internal_id,
        name=internal_id,
        issuer=None,
        yield_to_maturity=ytm,
        price=price,
        currency=currency,
        coupon_rate=coupon,
        nominal=1000,
        start_date=date(2024, 1, 1),
        maturity_date=date(2028, 1, 1),
        status="active",
        is_government=False,
    )


def _hist(internal_id, rows):
    out = []
    for d, price, ytm in rows:
        out.append(SimpleNamespace(
            internal_id=internal_id,
            date=d,
            price=Decimal(str(price)) if price is not None else None,
            yield_=Decimal(str(ytm)),
        ))
    return out


def test_known_strategies_set():
    assert {"Balanced", "Conservative", "Aggressive", "Carry Trade", "Dollarization"} == KNOWN_STRATEGIES


def test_score_conservative_formula():
    b = _bond("A", ytm=10, price=100)
    # ytm*0.3 + (100-price)*0.01 = 3.0 + 0
    assert _score_bond_for_strategy(b, "Conservative", price=Decimal("100"), ytm=Decimal("10")) == 3.0


def test_score_conservative_discount_bonus():
    b = _bond("A", ytm=10, price=90)
    # 3.0 + (100-90)*0.01 = 3.1
    assert _score_bond_for_strategy(b, "Conservative", price=Decimal("90"), ytm=Decimal("10")) == 3.1


def test_score_aggressive_formula():
    b = _bond("A", ytm=10, price=100)
    assert _score_bond_for_strategy(b, "Aggressive", price=Decimal("100"), ytm=Decimal("10")) == 8.0


def test_score_carry_trade_uses_coupon():
    b = _bond("A", ytm=10, coupon=12)
    # coupon*0.6 + ytm*0.4 = 7.2 + 4.0 = 11.2
    assert _score_bond_for_strategy(b, "Carry Trade", price=Decimal("100"), ytm=Decimal("10")) == 11.2


def test_score_dollarization_usd_bonus():
    usd = _bond("A", ytm=10, currency="USD")
    byn = _bond("B", ytm=10, currency="BYN")
    usd_score = _score_bond_for_strategy(usd, "Dollarization", price=Decimal("100"), ytm=Decimal("10"))
    byn_score = _score_bond_for_strategy(byn, "Dollarization", price=Decimal("100"), ytm=Decimal("10"))
    assert usd_score - byn_score == 5.0


def test_score_balanced_default_formula():
    b = _bond("A", ytm=10, price=100)
    assert _score_bond_for_strategy(b, "Balanced", price=Decimal("100"), ytm=Decimal("10")) == 5.0


def test_build_price_rows_sorts_and_filters_none():
    hist = {
        "A": _hist("A", [(date(2024, 1, 2), 101, 9),
                         (date(2024, 1, 1), 100, 10),
                         (date(2024, 1, 3), None, 8)]),
    }
    rows = _build_price_rows(hist)
    # none price dropped, remaining sorted by date
    assert [r[0] for r in rows["A"]] == [date(2024, 1, 1), date(2024, 1, 2)]
    assert rows["A"][0][1] == Decimal("100")


def test_snapshot_on_or_before_returns_last_known():
    hist = {"A": _hist("A", [(date(2024, 1, 1), 100, 10),
                             (date(2024, 1, 5), 102, 9)])}
    rows = _build_price_rows(hist)
    assert _snapshot_on_or_before(rows, "A", date(2024, 1, 3)) == (Decimal("100"), Decimal("10"))
    assert _snapshot_on_or_before(rows, "A", date(2024, 1, 5)) == (Decimal("102"), Decimal("9"))
    assert _snapshot_on_or_before(rows, "A", date(2023, 1, 1)) is None
    assert _snapshot_on_or_before(rows, "Z", date(2024, 1, 5)) is None


def test_run_backtest_unknown_strategy_raises():
    import pytest
    with pytest.raises(ValueError):
        run_backtest([_bond("A")], {}, strategy="Nonsense")


def test_run_backtest_nonpositive_capital_raises():
    import pytest
    with pytest.raises(ValueError):
        run_backtest([_bond("A")], {}, initial_capital=Decimal("0"))


def test_run_backtest_top_n_lt_1_raises():
    import pytest
    with pytest.raises(ValueError):
        run_backtest([_bond("A")], {}, top_n=0)


def test_run_backtest_start_after_end_raises():
    import pytest
    with pytest.raises(ValueError):
        run_backtest([_bond("A")], {}, start_date=date(2024, 6, 1), end_date=date(2024, 1, 1))


def test_run_backtest_no_history_returns_initial():
    res = run_backtest([_bond("A")], {}, initial_capital=Decimal("5000"),
                       start_date=date(2024, 1, 1), end_date=date(2024, 3, 1))
    assert res.final_value == Decimal("5000")
    assert res.total_return_pct == Decimal("0")


def test_run_backtest_simulates_and_marks():
    bonds = [_bond("A", ytm=10, price=100), _bond("B", ytm=12, price=100)]
    history = {
        "A": _hist("A", [(date(2024, 1, 1), 100, 10), (date(2024, 2, 1), 101, 10)]),
        "B": _hist("B", [(date(2024, 1, 1), 100, 12), (date(2024, 2, 1), 102, 12)]),
    }
    res = run_backtest(bonds, history, strategy="Balanced",
                       initial_capital=Decimal("10000"),
                       start_date=date(2024, 1, 1), end_date=date(2024, 3, 1),
                       top_n=2, rebalance_days=30)
    assert res.strategy == "Balanced"
    assert len(res.equity_curve) > 0
    assert res.final_value > 0
    assert isinstance(res.as_dict(), dict)
    assert res.as_dict()["initial_capital"] == 10000.0


def test_backtest_result_as_dict_serializes():
    r = BacktestResult()
    r.strategy = "Balanced"
    r.start_date = date(2024, 1, 1)
    r.end_date = date(2024, 1, 2)
    r.initial_capital = Decimal("1000")
    r.final_value = Decimal("1100")
    r.total_return_pct = Decimal("10")
    d = r.as_dict()
    assert d["strategy"] == "Balanced"
    assert d["start_date"] == "2024-01-01"
    assert d["total_return_pct"] == 10.0
