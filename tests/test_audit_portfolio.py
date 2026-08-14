"""Comprehensive pytest suite for the ``portfolio`` module (backtest, scenarios,
transactions, rebalance, optimizer, income, pnl, positions_repository).

Style notes:
- Pure functions are tested without a DB.
- DB-backed repository tests use ``session_scope`` (schema is created per-test
  by tests/conftest.py autouse fixtures). The root conftest compiles BigInteger
  PKs to INTEGER on sqlite, so the repo INSERT helpers autoincrement normally.
- Fixed dates everywhere (no ``date.today()``, no network, no randomness).
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from ml.models import RebalanceAction, RebalancePlan
from scraper.db import session_scope
from scraper.models import Bond
from scraper.orm import (
    BondHistoryORM,
    PortfolioPositionORM,
    RebalanceHistoryORM,
    TransactionORM,
)
from scoring.models import ScenarioName, UserPreferences

# =========================================================================== #
# Shared helpers
# =========================================================================== #


def _make_bond(
    internal_id: str,
    *,
    ytm: float | None = 10.0,
    price: float | None = 100.0,
    currency: str = "USD",
    coupon_rate: float | None = 10.0,
    coupon_frequency: int | None = 2,
    maturity_date: date | None = date(2035, 1, 1),
    status: str = "active",
) -> Bond:
    return Bond(
        internal_id=internal_id,
        name=f"Bond {internal_id}",
        issuer="Treasury",
        currency=currency,  # type: ignore[arg-type]
        coupon_rate=Decimal(str(coupon_rate)) if coupon_rate is not None else None,
        coupon_frequency=coupon_frequency,  # type: ignore[arg-type]
        maturity_date=maturity_date,
        price=Decimal(str(price)) if price is not None else None,
        yield_to_maturity=Decimal(str(ytm)) if ytm is not None else None,
        status=status,  # type: ignore[arg-type]
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _hist(
    internal_id: str,
    day: date,
    price: float,
    ytm: float = 10.0,
) -> BondHistoryORM:
    return BondHistoryORM(
        internal_id=internal_id,
        date=day,
        price=Decimal(str(price)),
        yield_=Decimal(str(ytm)),
    )


def _tx(
    tx_id: int,
    internal_id: str,
    side: str,
    amount: str,
    price: str,
    day: str,
    currency: str = "USD",
) -> TransactionORM:
    return TransactionORM(
        id=tx_id,
        user_id=1,
        internal_id=internal_id,
        side=side,
        amount=Decimal(amount),
        price=Decimal(price),
        currency=currency,
        executed_at=datetime.fromisoformat(day).replace(tzinfo=UTC),
    )


def _pos(user_id: int, internal_id: str, amount: str) -> PortfolioPositionORM:
    return PortfolioPositionORM(
        user_id=user_id,
        internal_id=internal_id,
        amount=Decimal(amount),
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _standard_history() -> dict[str, list[BondHistoryORM]]:
    """Two bonds with overlapping 3-date histories (2026-01-01 .. 03)."""
    return {
        "B1": [
            _hist("B1", date(2026, 1, 1), 100),
            _hist("B1", date(2026, 1, 2), 110),
            _hist("B1", date(2026, 1, 3), 100),
        ],
        "B2": [
            _hist("B2", date(2026, 1, 1), 100),
            _hist("B2", date(2026, 1, 2), 105),
            _hist("B2", date(2026, 1, 3), 100),
        ],
    }


# =========================================================================== #
# 1. portfolio/backtest.py
# =========================================================================== #

from portfolio.backtest import KNOWN_STRATEGIES, BacktestResult, run_backtest


def test_backtest_unknown_strategy_raises():
    with pytest.raises(ValueError, match="Unknown strategy"):
        run_backtest([], {}, strategy="NotAStrategy")


def test_backtest_initial_capital_non_positive_raises():
    for bad in (Decimal("0"), Decimal("-1")):
        with pytest.raises(ValueError, match="initial_capital must be positive"):
            run_backtest([], {}, initial_capital=bad)


def test_backtest_top_n_less_than_one_raises():
    with pytest.raises(ValueError, match="top_n must be at least 1"):
        run_backtest([], {}, top_n=0)


def test_backtest_rebalance_days_less_than_one_raises():
    with pytest.raises(ValueError, match="rebalance_days must be at least 1"):
        run_backtest([], {}, rebalance_days=0)


def test_backtest_start_after_end_raises():
    with pytest.raises(ValueError, match="start_date must not be after end_date"):
        run_backtest(
            [], {},
            start_date=date(2026, 2, 1), end_date=date(2026, 1, 1),
        )


def test_backtest_empty_history_returns_initial_capital():
    result = run_backtest(
        [], {},
        strategy="Balanced",
        initial_capital=Decimal("7777"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
    )
    assert isinstance(result, BacktestResult)
    assert result.final_value == Decimal("7777")
    assert result.start_date == date(2026, 1, 1)
    assert result.end_date == date(2026, 1, 1)
    # Single equity point; the module hardcodes date.today() for it.
    assert result.equity_curve == [
        {"date": date.today().isoformat(), "value": float(Decimal("7777"))}
    ]
    assert result.positions_history == []
    assert result.sharpe_ratio is None
    assert result.max_drawdown_pct is None


def test_backtest_happy_path_equity_and_positions():
    bonds = [_make_bond("B1"), _make_bond("B2")]
    result = run_backtest(
        bonds,
        _standard_history(),
        strategy="Balanced",
        initial_capital=Decimal("10000"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        top_n=2,
        rebalance_days=1,
    )
    # Equity curve: one point per simulated date.
    assert [pt["date"] for pt in result.equity_curve] == [
        "2026-01-01", "2026-01-02", "2026-01-03",
    ]
    # rebalance_days=1 => rebalances on every date => one entry per date.
    assert len(result.positions_history) == 3
    assert result.positions_history[0]["holdings"].keys() == {"B1", "B2"}
    # Holdings amounts are quantized to 0.01.
    for entry in result.positions_history:
        for amt in entry["holdings"].values():
            assert Decimal(str(amt)) % Decimal("0.01") == 0
    # Final value equals cash + holdings marked at the last known prices.
    last = result.positions_history[-1]
    mark = {"B1": Decimal("100"), "B2": Decimal("100")}
    expected = Decimal(str(last["capital"])) + sum(
        Decimal(str(amt)) * mark[iid] for iid, amt in last["holdings"].items()
    )
    assert result.final_value == expected.quantize(Decimal("0.01"))
    # Money conservation: final cash+holdings equals the last equity point.
    assert result.final_value == Decimal(str(result.equity_curve[-1]["value"]))
    assert result.final_value == Decimal("10005.45")


def test_backtest_bond_without_history_is_never_bought():
    """No-lookahead fix: a catalog bond with no history rows must never be
    scored with its (future) current catalog price and must never be bought."""
    bonds = [
        _make_bond("B1"),
        _make_bond("B2"),
        _make_bond("NOHIST", ytm=25.0, price=95.0),  # attractive, but no history
    ]
    history = {
        "B1": [_hist("B1", date(2026, 1, 1), 100)],
        "B2": [_hist("B2", date(2026, 1, 1), 100)],
    }
    result = run_backtest(
        bonds,
        history,
        strategy="Balanced",
        initial_capital=Decimal("10000"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        top_n=5,
        rebalance_days=1,
    )
    for entry in result.positions_history:
        assert "NOHIST" not in entry["holdings"]
        assert set(entry["holdings"]) <= {"B1", "B2"}


def test_backtest_rebalance_only_when_days_since_threshold():
    bonds = [_make_bond("B1"), _make_bond("B2")]
    # Dates 10 days apart, rebalance_days=30: only the first date rebalances.
    history = {
        "B1": [
            _hist("B1", date(2026, 1, 1), 100),
            _hist("B1", date(2026, 1, 11), 110),
            _hist("B1", date(2026, 1, 21), 100),
        ],
        "B2": [
            _hist("B2", date(2026, 1, 1), 100),
            _hist("B2", date(2026, 1, 11), 100),
            _hist("B2", date(2026, 1, 21), 100),
        ],
    }
    result = run_backtest(
        bonds, history,
        strategy="Balanced",
        initial_capital=Decimal("10000"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 21),
        top_n=2,
        rebalance_days=30,
    )
    # positions_history only records rebalance events.
    assert len(result.positions_history) == 1
    assert result.positions_history[0]["holdings"].keys() == {"B1", "B2"}

    # Dates >= 30 days apart: every date rebalances and holdings change.
    history2 = {
        "B1": [
            _hist("B1", date(2026, 1, 1), 100),
            _hist("B1", date(2026, 2, 1), 110),
            _hist("B1", date(2026, 3, 3), 100),
        ],
        "B2": [
            _hist("B2", date(2026, 1, 1), 100),
            _hist("B2", date(2026, 2, 1), 100),
            _hist("B2", date(2026, 3, 3), 100),
        ],
    }
    result2 = run_backtest(
        bonds, history2,
        strategy="Balanced",
        initial_capital=Decimal("10000"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 3),
        top_n=2,
        rebalance_days=30,
    )
    assert len(result2.positions_history) == 3
    assert result2.positions_history[1]["holdings"] != result2.positions_history[0]["holdings"]


def test_backtest_all_known_strategies_runnable():
    bonds = [_make_bond("B1"), _make_bond("B2")]
    for strategy in sorted(KNOWN_STRATEGIES):
        result = run_backtest(
            bonds,
            _standard_history(),
            strategy=strategy,
            initial_capital=Decimal("10000"),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
            top_n=2,
            rebalance_days=1,
        )
        assert result.strategy == strategy
        assert result.final_value > 0
        assert len(result.equity_curve) == 3
        assert result.max_drawdown_pct is not None


def test_backtest_metrics_on_controlled_dataset():
    """Price 100 -> 110 -> 100, initial 1000, 2 identical bonds."""
    history = {
        "B1": [
            _hist("B1", date(2026, 1, 1), 100),
            _hist("B1", date(2026, 1, 2), 110),
            _hist("B1", date(2026, 1, 3), 100),
        ],
        "B2": [
            _hist("B2", date(2026, 1, 1), 100),
            _hist("B2", date(2026, 1, 2), 110),
            _hist("B2", date(2026, 1, 3), 100),
        ],
    }
    bonds = [_make_bond("B1"), _make_bond("B2")]
    result = run_backtest(
        bonds, history,
        strategy="Balanced",
        initial_capital=Decimal("1000"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        top_n=2,
        rebalance_days=1,
    )
    assert [pt["value"] for pt in result.equity_curve] == [1000.0, 1100.0, 1000.0]
    # Drawdown from the 1100 peak to 1000: 100/1100 = 9.09%.
    assert result.max_drawdown_pct == Decimal("9.09")
    assert result.max_drawdown_pct > 0
    # Two distinct returns -> positive sharpe.
    assert result.sharpe_ratio is not None and result.sharpe_ratio > 0
    assert result.total_return_pct == Decimal("0.00")


def test_backtest_sharpe_none_when_single_point_or_flat():
    bonds = [_make_bond("B1"), _make_bond("B2")]
    single = {
        "B1": [_hist("B1", date(2026, 1, 1), 100)],
        "B2": [_hist("B2", date(2026, 1, 1), 100)],
    }
    r1 = run_backtest(
        bonds, single,
        strategy="Balanced",
        initial_capital=Decimal("1000"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 1),
        top_n=2, rebalance_days=1,
    )
    assert r1.sharpe_ratio is None
    assert r1.annual_return_pct is None

    flat = {
        "B1": [
            _hist("B1", date(2026, 1, 1), 100),
            _hist("B1", date(2026, 1, 2), 100),
        ],
        "B2": [
            _hist("B2", date(2026, 1, 1), 100),
            _hist("B2", date(2026, 1, 2), 100),
        ],
    }
    r2 = run_backtest(
        bonds, flat,
        strategy="Balanced",
        initial_capital=Decimal("1000"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        top_n=2, rebalance_days=1,
    )
    # Zero-volatility equity curve -> sharpe stays None.
    assert [pt["value"] for pt in r2.equity_curve] == [1000.0, 1000.0]
    assert r2.sharpe_ratio is None


# =========================================================================== #
# 2. portfolio/scenarios.py
# =========================================================================== #

from portfolio.scenarios import run_all_scenarios, run_scenario


def test_run_all_scenarios_shape():
    results = run_all_scenarios(
        current_usd_byn=Decimal("3.3"),
        usd_share=0.5,
        byn_share=0.3,
        metals_share=0.2,
        eur_share=0.0,
    )
    # NOTE: the task brief said 5 scenarios, but the source (SCENARIO_DELTA
    # and ScenarioName) defines exactly 4: Bull USD / Neutral / Bull BYN / Stress.
    assert len(results) == 4
    assert {r.scenario for r in results} == {"Bull USD", "Neutral", "Bull BYN", "Stress"}
    for r in results:
        # usd_byn_end is quantized to 0.0001 in the source (brief said 0.01).
        assert (r.usd_byn_end * 10000) % 1 == 0
        assert isinstance(r.fx_change_pct, float)
        assert isinstance(r.portfolio_value_change_pct, float)


def test_scenarios_fx_change_pcts():
    results = run_all_scenarios(
        current_usd_byn=Decimal("3.3"),
        usd_share=0.5,
        byn_share=0.3,
        metals_share=0.2,
    )
    by_name = {r.scenario: r for r in results}
    assert by_name["Bull USD"].fx_change_pct == 15.0
    assert by_name["Neutral"].fx_change_pct == 0.0
    assert by_name["Bull BYN"].fx_change_pct == -10.0
    assert by_name["Stress"].fx_change_pct == -30.0
    # usd_byn_end = current * (1 + delta).
    assert by_name["Bull USD"].usd_byn_end == Decimal("3.7950")
    assert by_name["Stress"].usd_byn_end == Decimal("2.3100")


def test_scenarios_zero_current_usd_byn_gives_zero_fx_change():
    for r in run_all_scenarios(
        current_usd_byn=Decimal("0"),
        usd_share=0.5,
        byn_share=0.3,
        metals_share=0.2,
    ):
        assert r.fx_change_pct == 0.0
        assert r.portfolio_value_change_pct == 0.0
        assert r.usd_byn_end == 0


def test_scenarios_zero_shares_give_zero_portfolio_change():
    for r in run_all_scenarios(
        current_usd_byn=Decimal("3.3"),
        usd_share=0.0,
        byn_share=0.0,
        metals_share=0.0,
        eur_share=0.0,
    ):
        assert r.portfolio_value_change_pct == 0.0


def test_scenarios_metals_impact_formula():
    """metals_impact = metals_share * fx_change * 0.3, asserted exactly.

    NOTE (suspected docstring inconsistency): the module docstring claims
    metals (and EUR) "не зависят от USD/BYN" (are independent of USD/BYN),
    yet the code multiplies the USD/BYN fx change into the metals impact.
    The test pins the code's actual formula.
    """
    r = run_scenario(
        "Bull USD",
        current_usd_byn=Decimal("3.3"),
        usd_share=0.0,
        byn_share=0.0,
        metals_share=0.5,
    )
    fx_change = 0.15
    assert r.portfolio_value_change_pct == round(0.5 * fx_change * 0.3 * 100, 2)
    assert r.portfolio_value_change_pct == 2.25
    # Metals are (incorrectly per the docstring) the worst position under
    # "Bull USD" when they are the only exposure.
    stress = run_scenario(
        "Stress",
        current_usd_byn=Decimal("3.3"),
        usd_share=0.0,
        byn_share=0.0,
        metals_share=0.5,
    )
    assert stress.portfolio_value_change_pct == -4.5


def test_scenarios_extreme_fx_does_not_crash():
    for extreme in (Decimal("0.01"), Decimal("1000")):
        results = run_all_scenarios(
            current_usd_byn=extreme,
            usd_share=0.5,
            byn_share=0.3,
            metals_share=0.2,
        )
        assert len(results) == 4
        assert results[0].fx_change_pct == 15.0  # delta applies at any scale


def test_scenarios_negative_shares_tolerated():
    r = run_scenario(
        "Bull USD",
        current_usd_byn=Decimal("3.3"),
        usd_share=-0.2,
        byn_share=0.1,
    )
    # usd_impact = -0.2*0.15 = -0.03; byn_impact = 0.1*(-0.15) = -0.015.
    assert r.portfolio_value_change_pct == -4.5


# =========================================================================== #
# 3. portfolio/transactions.py
# =========================================================================== #

from portfolio.transactions import (
    delete_transaction,
    get_bond_transactions,
    list_transactions,
    record_transaction,
    total_bought_sold,
)

# NOTE: insert helpers (record_transaction) work in the test environment
# because the root conftest compiles BigInteger PKs to INTEGER on SQLite,
# giving real autoincrement; production Postgres uses BIGSERIAL.
async def test_record_transaction_creates_row_with_default_executed_at():
    async with session_scope() as session:
        tx = await record_transaction(
            session,
            user_id=4201,
            internal_id="T1",
            side="buy",
            amount=Decimal("1000"),
            price=Decimal("100"),
            currency="USD",
        )
        assert tx.id is not None
        assert tx.executed_at is not None  # server_default func.now()
        assert tx.note is None
        rows = await list_transactions(session, 4201)
        assert len(rows) == 1


# Duplicate identical transactions: the repository imposes no uniqueness on
# (user_id, internal_id, side, amount, price), so each call is its own row.
async def test_record_transaction_duplicates_are_separate_rows():
    async with session_scope() as session:
        t1 = await record_transaction(
            session, user_id=4202, internal_id="T2", side="buy",
            amount=Decimal("1000"), price=Decimal("100"), currency="USD",
        )
        t2 = await record_transaction(
            session, user_id=4202, internal_id="T2", side="buy",
            amount=Decimal("1000"), price=Decimal("100"), currency="USD",
        )
        assert t1.id != t2.id
        rows = await list_transactions(session, 4202)
        assert len(rows) == 2


async def test_list_transactions_limit_and_offset():
    async with session_scope() as session:
        for i in range(1, 6):
            session.add(
                _tx(6100 + i, "TX1", "buy", "100", "100", f"2026-01-0{i}")
            )
        # rows carry user_id=1 from the helper; ordered by executed_at desc
        rows = await list_transactions(session, 1, limit=2)
        assert [r.id for r in rows] == [6105, 6104]
        rows = await list_transactions(session, 1, limit=2, offset=2)
        assert [r.id for r in rows] == [6103, 6102]


async def test_delete_transaction_own_and_other_user():
    async with session_scope() as session:
        session.add_all(
            [
                TransactionORM(
                    id=6301, user_id=4301, internal_id="D1", side="buy",
                    amount=Decimal("1000"), price=Decimal("100"), currency="USD",
                    executed_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                TransactionORM(
                    id=6302, user_id=4302, internal_id="D1", side="buy",
                    amount=Decimal("500"), price=Decimal("100"), currency="USD",
                    executed_at=datetime(2026, 1, 2, tzinfo=UTC),
                ),
            ]
        )
        await session.flush()
        assert await delete_transaction(session, 4301, 6301) is True
        # session.get does not autoflush; force the DELETE to execute first.
        await session.flush()
        assert await session.get(TransactionORM, 6301) is None
        # Deleting another user's transaction: False and row untouched.
        assert await delete_transaction(session, 4301, 6302) is False
        assert await session.get(TransactionORM, 6302) is not None
        # Missing id: False.
        assert await delete_transaction(session, 4301, 99999) is False


async def test_get_bond_transactions_filters_by_internal_id():
    async with session_scope() as session:
        session.add_all(
            [
                TransactionORM(
                    id=6401, user_id=4401, internal_id="G1", side="buy",
                    amount=Decimal("1000"), price=Decimal("100"), currency="USD",
                    executed_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                TransactionORM(
                    id=6402, user_id=4401, internal_id="G2", side="buy",
                    amount=Decimal("2000"), price=Decimal("100"), currency="USD",
                    executed_at=datetime(2026, 1, 2, tzinfo=UTC),
                ),
                TransactionORM(
                    id=6403, user_id=4402, internal_id="G1", side="buy",
                    amount=Decimal("3000"), price=Decimal("100"), currency="USD",
                    executed_at=datetime(2026, 1, 3, tzinfo=UTC),
                ),
            ]
        )
        await session.flush()
        rows = await get_bond_transactions(session, 4401, "G1")
        assert [r.id for r in rows] == [6401]
        assert [r.id for r in await get_bond_transactions(session, 4401, "G2")] == [6402]
        assert await get_bond_transactions(session, 4401, "NOPE") == []


async def test_total_bought_sold_aggregation():
    async with session_scope() as session:
        session.add_all(
            [
                TransactionORM(
                    id=6501, user_id=4501, internal_id="A1", side="buy",
                    amount=Decimal("1000"), price=Decimal("100"), currency="USD",
                    executed_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                TransactionORM(
                    id=6502, user_id=4501, internal_id="A1", side="buy",
                    amount=Decimal("2000"), price=Decimal("100"), currency="USD",
                    executed_at=datetime(2026, 1, 2, tzinfo=UTC),
                ),
                TransactionORM(
                    id=6503, user_id=4501, internal_id="A1", side="sell",
                    amount=Decimal("400"), price=Decimal("110"), currency="USD",
                    executed_at=datetime(2026, 1, 3, tzinfo=UTC),
                ),
            ]
        )
        await session.flush()
        agg = await total_bought_sold(session, 4501, "A1")
        assert agg["bought"] == Decimal("3000")
        assert agg["sold"] == Decimal("400")
        assert agg["buy_count"] == 2
        assert agg["sell_count"] == 1
        empty = await total_bought_sold(session, 4501, "NOPE")
        assert empty["bought"] == Decimal("0")
        assert empty["sold"] == Decimal("0")
        assert empty["buy_count"] == 0 and empty["sell_count"] == 0


# =========================================================================== #
# 4. portfolio/rebalance.py
# =========================================================================== #

from portfolio.rebalance import (
    MIN_TRADE_AMOUNT,
    DEFAULT_DRIFT_THRESHOLD,
    _compute_weights,
    build_plan,
    maybe_auto_rebalance,
)


def test_build_plan_actions_buy_sell_and_amounts():
    bonds = [_make_bond("B1"), _make_bond("B2")]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Balanced")
    plan = build_plan(
        bonds=bonds,
        prefs=prefs,
        current_positions=[_pos(1, "B1", "9000"), _pos(1, "B2", "1000")],
        current_total=Decimal("10000"),
    )
    assert plan is not None
    assert plan.drift_threshold == DEFAULT_DRIFT_THRESHOLD
    sides = {a.side for a in plan.actions}
    assert {"buy", "sell"} <= sides
    buy_total = sum(a.amount for a in plan.actions if a.side == "buy")
    sell_total = sum(a.amount for a in plan.actions if a.side == "sell")
    assert buy_total == sell_total == Decimal("4000.00")
    for a in plan.actions:
        assert a.amount > 0
        assert a.internal_id in {"B1", "B2"}


def test_build_plan_returns_none_below_drift_threshold():
    bonds = [_make_bond("B1"), _make_bond("B2")]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Balanced")
    # Positions already at the target 50/50 -> zero drift.
    plan = build_plan(
        bonds=bonds,
        prefs=prefs,
        current_positions=[_pos(1, "B1", "5000"), _pos(1, "B2", "5000")],
        current_total=Decimal("10000"),
    )
    assert plan is None


def test_build_plan_min_trade_amount_50_blocks_small_deltas():
    assert MIN_TRADE_AMOUNT == Decimal("50")
    bonds = [_make_bond("B1")]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("100"), strategy="Balanced")
    # delta = 100 - 70 = 30 < 50 -> drift 0.3 >= threshold 0.3, but no action.
    plan = build_plan(
        bonds=bonds,
        prefs=prefs,
        current_positions=[_pos(1, "B1", "70")],
        current_total=Decimal("100"),
        drift_threshold=0.3,
    )
    assert plan is not None
    assert plan.actions == []
    # delta = 60 >= 50 -> a buy action is produced.
    plan2 = build_plan(
        bonds=bonds,
        prefs=prefs,
        current_positions=[_pos(1, "B1", "40")],
        current_total=Decimal("100"),
        drift_threshold=0.3,
    )
    assert plan2 is not None
    assert len(plan2.actions) == 1
    action = plan2.actions[0]
    assert action.side == "buy"
    assert action.amount == Decimal("60.00")
    assert action.weight_before == 0.4
    assert action.weight_after == 1.0


def test_compute_weights_ignores_currency_fx():
    """_compute_weights takes no fx_rates parameter: weights are raw
    amount ratios (fx conversion is expected upstream, e.g. in total_value)."""
    positions = [_pos(1, "B1", "7000"), _pos(1, "B2", "3000")]
    target = {"B1": Decimal("5000"), "B2": Decimal("5000")}
    deltas = _compute_weights(positions, target, Decimal("10000"),
                              initial_capital=Decimal("10000"))
    assert deltas["B1"] == (Decimal("-2000"), 0.7, 0.5)
    assert deltas["B2"] == (Decimal("2000"), 0.3, 0.5)
    # Mixed currencies: ratios still raw amounts.
    mixed = [_pos(1, "B1", "6000"), _pos(1, "B2", "4000")]
    deltas2 = _compute_weights(mixed, target, Decimal("10000"))
    assert deltas2["B1"][1] == 0.6
    assert deltas2["B2"][1] == 0.4


# End-to-end: plan built from the user's positions/prefs, persisted, positions
# updated and the plan marked applied.
async def test_maybe_auto_rebalance_with_real_db():
    async with session_scope() as session:
        bonds = [_make_bond("M1", ytm=12.0, price=98.0), _make_bond("M2", ytm=10.0, price=100.0)]
        prefs = UserPreferences(user_id=4601, initial_capital=Decimal("10000"), strategy="Balanced")
        plan = await maybe_auto_rebalance(user_id=4601, prefs=prefs, bonds=bonds)
        assert plan is not None
        assert all(a.side == "buy" for a in plan.actions)
        positions = await list_positions(session, 4601)
        assert {p.internal_id for p in positions} == {"M1", "M2"}
        history = await list_rebalance_history(session, 4601)
        assert len(history) == 1
        assert history[0].applied is True


# =========================================================================== #
# 5. portfolio/optimizer.py
# =========================================================================== #

from portfolio.optimizer import (
    STRATEGY_WEIGHTS,
    _apply_strategy_bonuses,
    allocate,
    rank_bonds,
)


def test_allocate_sum_matches_capital_and_positive():
    bonds = [
        _make_bond("B1", ytm=12.0, price=98.0, coupon_rate=11.0),
        _make_bond("B2", ytm=10.0, price=100.0),
        _make_bond("B3", ytm=8.0, price=102.0),
    ]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Balanced")
    alloc = allocate(bonds, prefs, top_n=10)
    assert sum(alloc.items.values()) == Decimal("10000")
    assert len(alloc.items) == 3
    assert all(v >= 0 for v in alloc.items.values())
    for v in alloc.items.values():
        assert v % Decimal("0.01") == 0


def test_allocate_all_seven_strategies_runnable():
    bonds = [
        _make_bond("B1", ytm=12.0, price=98.0, coupon_rate=11.0),
        _make_bond("B2", ytm=10.0, price=100.0),
        _make_bond("B3", ytm=8.0, price=102.0),
    ]
    assert len(STRATEGY_WEIGHTS) == 7
    assert set(STRATEGY_WEIGHTS) == {
        "Conservative", "Balanced", "Aggressive", "Carry Trade",
        "Dollarization", "Maximum Reward/Risk", "Metals++",
    }
    for strategy in STRATEGY_WEIGHTS:
        prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy=strategy)
        alloc = allocate(bonds, prefs, top_n=10)
        assert alloc.strategy == strategy
        assert sum(alloc.items.values()) == Decimal("10000")
        assert all(v >= 0 for v in alloc.items.values())


def test_allocate_empty_bonds_no_crash():
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Balanced")
    alloc = allocate([], prefs)
    assert alloc.items == {}
    assert alloc.expected_return == 0.0
    assert alloc.volatility == 0.0


def test_allocate_top_n_larger_than_bond_count():
    bonds = [_make_bond("B1"), _make_bond("B2")]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Balanced")
    alloc = allocate(bonds, prefs, top_n=99)
    assert len(alloc.items) == 2
    assert sum(alloc.items.values()) == Decimal("10000")


def test_allocate_zero_capital_no_crash():
    bonds = [_make_bond("B1"), _make_bond("B2")]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("0"), strategy="Balanced")
    alloc = allocate(bonds, prefs)
    assert sum(alloc.items.values()) == Decimal("0")


def test_carry_trade_price_under_70_penalty():
    """Exact source formula: in _apply_strategy_bonuses, Carry Trade with
    price < 70 applies ``weighted -= 40.0`` (plus coupon/duration overlays)."""
    low = _make_bond("LOW", price=65.0, coupon_rate=None, maturity_date=None)
    healthy = _make_bond("HI", price=100.0, coupon_rate=None, maturity_date=None)
    assert _apply_strategy_bonuses(low, "Carry Trade", 100.0) == 60.0
    assert _apply_strategy_bonuses(healthy, "Carry Trade", 100.0) == 100.0
    # Effect on ranking: the distressed bond is penalized out of contention.
    ranked = rank_bonds([low, healthy], "Carry Trade")
    by_id = {s.internal_id: s.score for s in ranked}
    assert by_id["HI"] > by_id["LOW"]


# =========================================================================== #
# 6. portfolio/income.py
# =========================================================================== #

from portfolio.income import bond_cashflows, portfolio_income


def _holding(iid: str = "B1", **kw) -> dict:
    base = {
        "internal_id": iid,
        "name": iid,
        "currency": "USD",
        "amount": Decimal("1000"),
        "coupon_rate": Decimal("10"),
        "coupon_frequency": 2,
        "maturity_date": date(2027, 7, 1),
        "price": Decimal("100"),
    }
    base.update(kw)
    return base


def test_portfolio_income_structure():
    result = portfolio_income([_holding()], from_date=date(2026, 7, 1))
    assert set(result) >= {
        "total_invested", "annual_income", "yield_on_cost", "next_payment",
        "monthly_calendar", "per_bond", "horizon_months", "income_next_horizon",
    }
    assert result["total_invested"] == 1000.0
    assert result["annual_income"] == 100.0
    assert result["yield_on_cost"] == 10.0
    assert result["next_payment"]["date"] == "2027-01-01"
    assert result["next_payment"]["amount"] == 50.0
    assert result["next_payment"]["kind"] == "coupon"
    assert result["monthly_calendar"] == [
        {"month": "2027-01", "amount": 50.0},
        {"month": "2027-07", "amount": 50.0},
    ]
    pb = result["per_bond"][0]
    assert pb["internal_id"] == "B1"
    assert pb["annual_income"] == 100.0
    assert pb["yield_on_cost"] == 10.0


def test_portfolio_income_empty_holdings():
    result = portfolio_income([], from_date=date(2026, 7, 1))
    assert result["total_invested"] == 0.0
    assert result["annual_income"] == 0.0
    assert result["yield_on_cost"] == 0.0
    assert result["next_payment"] is None
    assert result["monthly_calendar"] == []
    assert result["per_bond"] == []
    assert result["income_next_horizon"] == 0.0


def test_portfolio_income_coupon_frequency_none():
    result = portfolio_income(
        [_holding(coupon_frequency=None)], from_date=date(2026, 7, 1)
    )
    pb = result["per_bond"][0]
    # No schedule -> no payments, but annual income is still computed.
    assert pb["next_payment"] is None
    assert pb["annual_income"] == 100.0
    assert result["next_payment"] is None
    assert result["monthly_calendar"] == []
    assert result["income_next_horizon"] == 0.0


def test_portfolio_income_price_none_or_zero_falls_back_to_par():
    for price in (None, Decimal("0")):
        result = portfolio_income(
            [_holding(price=price)], from_date=date(2026, 7, 1)
        )
        assert result["per_bond"][0]["annual_income"] == 100.0
        assert result["total_invested"] == 1000.0


def test_portfolio_income_fx_rate_missing_currency_is_1():
    result = portfolio_income(
        [_holding()], from_date=date(2026, 7, 1), fx_rates={"BYN": 3.3}
    )
    assert result["total_invested"] == 1000.0
    assert result["annual_income"] == 100.0
    with_fx = portfolio_income(
        [_holding()], from_date=date(2026, 7, 1), fx_rates={"USD": 3.3}
    )
    assert with_fx["total_invested"] == 3300.0
    assert with_fx["annual_income"] == 330.0
    assert with_fx["monthly_calendar"][0]["amount"] == 165.0


def test_portfolio_income_horizon_months_bounds():
    short = portfolio_income([_holding()], from_date=date(2026, 7, 1), horizon_months=1)
    assert short["horizon_months"] == 1
    assert short["income_next_horizon"] == 0.0
    assert short["monthly_calendar"] == []
    long = portfolio_income([_holding()], from_date=date(2026, 7, 1), horizon_months=120)
    assert long["horizon_months"] == 120
    assert long["income_next_horizon"] == 100.0
    assert {m["month"] for m in long["monthly_calendar"]} == {"2027-01", "2027-07"}


def test_bond_cashflows_from_date_is_exclusive():
    kw = dict(
        internal_id="B1",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("10"),
        coupon_frequency=2,
        maturity_date=date(2027, 7, 1),
        price=Decimal("100"),
    )
    # A coupon falls exactly on 2026-07-01. With from_date == that date the
    # coupon is excluded; one day earlier it is included.
    at = bond_cashflows(from_date=date(2026, 7, 1), **kw)
    assert [f.date for f in at if f.kind == "coupon"] == [
        date(2027, 1, 1), date(2027, 7, 1),
    ]
    before = bond_cashflows(from_date=date(2026, 6, 30), **kw)
    coupon_dates = [f.date for f in before if f.kind == "coupon"]
    assert date(2026, 7, 1) in coupon_dates
    assert coupon_dates[0] == date(2026, 7, 1)
    # Redemption always included by default.
    assert any(f.kind == "redemption" and f.date == date(2027, 7, 1) for f in at)


# =========================================================================== #
# 7. portfolio/pnl.py
# =========================================================================== #

from portfolio.pnl import (
    PositionPnL,
    compute_daily_returns,
    compute_max_drawdown,
    compute_pnl,
    compute_sharpe,
)


def test_pnl_fifo_realized_unrealized():
    """1000 money @ 100 buys 1000 face; selling 400 money @ 110 sells
    400*100/110 = 363.64 face. Realized = 363.64*(110-100)/100 = 36.36.
    Remaining 636.36 face @ 110 -> value 700.00, unrealized 63.64.
    (The task brief's 40/60 numbers assumed amount==face; the source
    converts money->face with the /100 factor — see the module docstring.)"""
    txs = [
        _tx(1, "B1", "buy", "1000", "100", "2026-01-01"),
        _tx(2, "B1", "sell", "400", "110", "2026-02-01"),
    ]
    positions = [_pos(1, "B1", "600")]
    bonds = {"B1": _make_bond("B1", price=110.0)}
    pnl = compute_pnl(transactions=txs, positions=positions, bonds_by_id=bonds)
    assert pnl.total_realized == pytest.approx(Decimal("36.36363636363636363636363636"))
    assert pnl.total_unrealized == pytest.approx(Decimal("63.63636363636363636363636360"))
    assert pnl.total_value == pytest.approx(Decimal("700"))
    assert pnl.total_invested == pytest.approx(Decimal("636.3636363636363636363636364"))
    # PositionPnL quantizes every field to 0.01.
    per_bond = pnl.per_bond[0]
    assert isinstance(per_bond, PositionPnL)
    assert per_bond.realized_pnl == Decimal("36.36")
    assert per_bond.unrealized_pnl == Decimal("63.64")
    assert per_bond.current_value == Decimal("700.00")
    assert per_bond.total_pnl() == per_bond.realized_pnl + per_bond.unrealized_pnl


def test_pnl_coupon_data_float_does_not_crash():
    """Regression: coupon_data values may arrive as floats (typed as Decimal
    but the API layer passes JSON floats); Decimal(str(raw)) must handle them."""
    txs = [_tx(1, "B1", "buy", "1000", "100", "2026-01-01")]
    positions = [_pos(1, "B1", "1000")]
    bonds = {"B1": _make_bond("B1", price=100.0)}
    pnl = compute_pnl(
        transactions=txs, positions=positions, bonds_by_id=bonds,
        coupon_data={"B1": 15.5},
    )
    assert pnl.total_coupon_income == Decimal("15.5")
    assert pnl.per_bond[0].coupon_income == Decimal("15.50")


def test_pnl_coupon_none_value_is_zero():
    txs = [_tx(1, "B1", "buy", "1000", "100", "2026-01-01")]
    positions = [_pos(1, "B1", "1000")]
    bonds = {"B1": _make_bond("B1", price=100.0)}
    pnl = compute_pnl(
        transactions=txs, positions=positions, bonds_by_id=bonds,
        coupon_data={"B1": None, "OTHER": 5.0},
    )
    assert pnl.total_coupon_income == Decimal("0")
    assert pnl.per_bond[0].coupon_income == Decimal("0.00")


def test_pnl_position_without_transactions_par_assumption():
    positions = [_pos(1, "B2", "1000")]
    bonds = {"B2": _make_bond("B2", price=110.0)}
    pnl = compute_pnl(transactions=[], positions=positions, bonds_by_id=bonds)
    # Documented par-entry assumption: 1000 invested at par -> 1100 at 110.
    assert pnl.total_value == Decimal("1100")
    assert pnl.total_unrealized == Decimal("100")


def test_pnl_defaulted_delisted_bond_zero_value():
    """pnl.py zeroes the value when status in {'defaulted','delisted'}.

    NOTE: 'defaulted' is not a valid BondStatus literal in scraper/models.py —
    the validator normalizes it to 'unknown', so the 'defaulted' branch is
    unreachable through the pydantic model; 'delisted' exercises the branch.
    """
    positions = [_pos(1, "B1", "1000")]
    bonds = {"B1": _make_bond("B1", price=110.0, status="delisted")}
    pnl = compute_pnl(transactions=[], positions=positions, bonds_by_id=bonds)
    assert pnl.total_value == Decimal("0")
    assert pnl.total_unrealized == Decimal("-1000")


def test_pnl_price_zero_current_value_zero():
    positions = [_pos(1, "B1", "1000")]
    bonds = {"B1": _make_bond("B1", price=0.0)}
    pnl = compute_pnl(transactions=[], positions=positions, bonds_by_id=bonds)
    assert pnl.total_value == Decimal("0")
    txs = [_tx(1, "B1", "buy", "1000", "100", "2026-01-01")]
    pnl2 = compute_pnl(transactions=txs, positions=positions, bonds_by_id=bonds)
    assert pnl2.total_value == Decimal("0")


def test_pnl_oversell_realized_only_on_matched_lots():
    """Selling more than bought: realized is computed only for the face
    matched by FIFO lots; the unmatched oversell portion is ignored."""
    txs = [
        _tx(1, "B1", "buy", "1000", "100", "2026-01-01"),
        _tx(2, "B1", "sell", "2000", "105", "2026-02-01"),
    ]
    positions = [_pos(1, "B1", "1000")]
    bonds = {"B1": _make_bond("B1", price=105.0)}
    pnl = compute_pnl(transactions=txs, positions=positions, bonds_by_id=bonds)
    # matched face = 1000 (all of the buy lot) -> realized = 1000*5/100 = 50.
    assert pnl.total_realized == Decimal("50")
    assert pnl.total_value == Decimal("0")
    assert pnl.total_invested == Decimal("0")


def test_pnl_fx_rates_multiply_totals_and_weights():
    txs = [
        _tx(1, "U1", "buy", "1000", "100", "2026-01-01"),
        _tx(2, "N1", "buy", "1000", "100", "2026-01-02", currency="BYN"),
    ]
    positions = [_pos(1, "U1", "1000"), _pos(1, "N1", "1000")]
    bonds = {
        "U1": _make_bond("U1", price=110.0),
        "N1": _make_bond("N1", price=105.0, currency="BYN"),
    }
    pnl = compute_pnl(
        transactions=txs, positions=positions, bonds_by_id=bonds,
        fx_rates={"USD": 3.3},  # BYN missing -> rate 1.0
        coupon_data={"U1": 10.5, "N1": None},
    )
    assert pnl.total_value == Decimal("4680")  # 1100*3.3 + 1050*1.0
    assert pnl.total_invested == Decimal("4300")
    assert pnl.total_unrealized == Decimal("380")
    assert pnl.total_coupon_income == Decimal("34.65")
    weights = {p.internal_id: p.weight for p in pnl.per_bond}
    assert weights["U1"] == pytest.approx(Decimal("0.7756410256410256410256410256"))
    assert sum(weights.values()) == pytest.approx(Decimal("1"), abs=1e-9)


def test_compute_daily_returns():
    assert compute_daily_returns([]) == []
    assert compute_daily_returns([{"date": "2026-01-01", "value": 100.0}]) == []
    curve = [
        {"date": "2026-01-01", "value": 1000.0},
        {"date": "2026-01-02", "value": 1100.0},
        {"date": "2026-01-03", "value": 990.0},
    ]
    rets = compute_daily_returns(curve)
    assert rets == [
        {"date": "2026-01-02", "return_pct": 10.0},
        {"date": "2026-01-03", "return_pct": -10.0},
    ]


def test_compute_max_drawdown():
    assert compute_max_drawdown([]) == 0.0
    assert compute_max_drawdown([{"date": "d", "value": 100.0}]) == 0.0
    curve = [
        {"date": "d1", "value": 100.0},
        {"date": "d2", "value": 120.0},
        {"date": "d3", "value": 90.0},
    ]
    assert compute_max_drawdown(curve) == 25.0
    rising = [{"date": f"d{i}", "value": v} for i, v in enumerate([10, 20, 30])]
    assert compute_max_drawdown(rising) == 0.0


def test_compute_sharpe():
    assert compute_sharpe([]) == 0.0
    assert compute_sharpe([{"date": "d1", "return_pct": 5.0}]) == 0.0
    flat = [{"date": f"d{i}", "return_pct": 5.0} for i in range(3)]
    assert compute_sharpe(flat) == 0.0  # zero vol
    rets = [{"date": f"d{i}", "return_pct": r} for i, r in enumerate([10.0, 20.0, 30.0])]
    assert compute_sharpe(rets) > 0.0
    assert isinstance(compute_sharpe(rets), float)


# =========================================================================== #
# 8. portfolio/positions_repository.py
# =========================================================================== #

from portfolio.positions_repository import (
    get_position,
    list_positions,
    list_rebalance_history,
    mark_rebalance_applied,
    remove_position,
    save_rebalance_plan,
    total_value,
    upsert_position,
)

async def test_upsert_position_twice_updates_single_row():
    async with session_scope() as session:
        await upsert_position(session, 4701, "UP1", Decimal("1000"))
        await upsert_position(session, 4701, "UP1", Decimal("2500"))
        rows = await list_positions(session, 4701)
        assert len(rows) == 1
        assert rows[0].amount == Decimal("2500.0000")


async def test_get_position_and_missing():
    async with session_scope() as session:
        session.add(_pos(4801, "GP1", "1000"))
        await session.flush()
        found = await get_position(session, 4801, "GP1")
        assert found is not None and found.internal_id == "GP1"
        assert await get_position(session, 4801, "MISSING") is None
        assert await get_position(session, 99999, "GP1") is None


async def test_remove_position_existing_and_missing():
    async with session_scope() as session:
        session.add(_pos(4901, "RP1", "1000"))
        await session.flush()
        await remove_position(session, 4901, "RP1")
        assert await get_position(session, 4901, "RP1") is None
        await remove_position(session, 4901, "NEVER-EXISTED")  # must not raise


async def test_list_positions_per_user():
    async with session_scope() as session:
        session.add_all(
            [
                _pos(5001, "L1", "1000"),
                _pos(5001, "L2", "2000"),
                _pos(5002, "L9", "3000"),
            ]
        )
        await session.flush()
        ids = {p.internal_id for p in await list_positions(session, 5001)}
        assert ids == {"L1", "L2"}
        assert [p.internal_id for p in await list_positions(session, 5002)] == ["L9"]
        assert await list_positions(session, 99999) == []


def test_total_value_without_and_with_fx():
    positions = [
        _pos(1, "B1", "1000"),
        _pos(1, "B2", "2000"),
        _pos(1, "B3", "500"),
    ]
    # Without bonds/fx: plain sum of amounts (1000 + 2000 + 500).
    assert total_value(positions) == Decimal("3500")
    # With fx: per-currency conversion; unknown currency -> 1.0.
    bonds_map = {
        "B1": _make_bond("B1", currency="USD"),
        "B2": _make_bond("B2", currency="BYN"),
        "B3": _make_bond("B3", currency="XAU"),
    }
    converted = total_value(positions, bonds_by_id=bonds_map, fx_rates={"USD": 3.3, "BYN": 2.0})
    assert converted == Decimal("7800")  # 1000*3.3 + 2000*2.0 + 500*1.0
    # Missing bond in the map -> rate 1.0 too.
    partial = total_value(positions, bonds_by_id={"B1": bonds_map["B1"]}, fx_rates={"USD": 3.3})
    assert partial == Decimal("5800")  # 1000*3.3 + 2000*1.0 + 500*1.0
    # No bonds but fx_rates given: plain sum again (both must be present).
    assert total_value(positions, fx_rates={"USD": 3.3}) == Decimal("3500")


async def _seed_rebalance_history(session, user_id: int) -> None:
    plan = RebalancePlan(
        strategy="Balanced",
        drift_threshold=0.05,
        max_drift_observed=0.2,
        actions=[RebalanceAction(
            internal_id="B1", side="buy", amount=Decimal("100"),
            weight_before=0.5, weight_after=0.6, reason="drift",
        )],
        expected_return=10.0,
        estimated_cost=100.0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    for i, day in enumerate((1, 3, 2)):
        session.add(RebalanceHistoryORM(
            id=user_id * 10 + i,
            user_id=user_id,
            strategy=plan.strategy,
            drift_threshold=Decimal("0.05"),
            max_drift_observed=Decimal(str(0.1 + i / 10)),
            expected_return=Decimal("10"),
            estimated_cost=Decimal("100"),
            actions=[a.model_dump(mode="json") for a in plan.actions],
            created_at=datetime(2026, 1, day, tzinfo=UTC),
            applied=False,
        ))
    await session.flush()


# save_rebalance_plan persists a plan (root conftest makes BigInteger PKs
# autoincrement on SQLite).
async def test_save_rebalance_plan_returns_id():
    plan = RebalancePlan(
        strategy="Balanced",
        drift_threshold=0.05,
        max_drift_observed=0.2,
        actions=[RebalanceAction(
            internal_id="B1", side="buy", amount=Decimal("100"),
            weight_before=0.5, weight_after=0.6, reason="drift",
        )],
        expected_return=10.0,
        estimated_cost=100.0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    async with session_scope() as session:
        plan_id = await save_rebalance_plan(session, 5101, plan)
        assert isinstance(plan_id, int) and plan_id > 0
        rows = await list_rebalance_history(session, 5101)
        assert len(rows) == 1
        assert rows[0].applied is False
        assert rows[0].strategy == "Balanced"


async def test_list_rebalance_history_newest_first():
    async with session_scope() as session:
        await _seed_rebalance_history(session, 5201)
        history = await list_rebalance_history(session, 5201)
        # SQLite stores DateTime(timezone=True) without tzinfo; normalize back.
        created = [h.created_at.replace(tzinfo=UTC) for h in history]
        assert created == [
            datetime(2026, 1, 3, tzinfo=UTC),
            datetime(2026, 1, 2, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        ]
        limited = await list_rebalance_history(session, 5201, limit=2)
        assert len(limited) == 2
        assert await list_rebalance_history(session, 99999) == []


async def test_mark_rebalance_applied_flips_flag():
    async with session_scope() as session:
        await _seed_rebalance_history(session, 5301)
        await mark_rebalance_applied(session, 53010)
        await session.flush()
        row = await session.get(RebalanceHistoryORM, 53010)
        assert row is not None and row.applied is True
        untouched = await session.get(RebalanceHistoryORM, 53012)
        assert untouched is not None and untouched.applied is False