"""Тесты portfolio: оптимизатор + сценарии."""

from __future__ import annotations

from datetime import UTC, date
from decimal import Decimal

from portfolio.optimizer import allocate, rank_bonds, rebalance
from portfolio.scenarios import run_all_scenarios, run_scenario
from scoring.models import UserPreferences
from scraper.models import Bond


def _bond(iid: str, ytm: float, cur: str, maturity: date, status: str = "active") -> Bond:
    return Bond(
        internal_id=iid,
        name=iid,
        currency=cur,  # type: ignore[arg-type]
        yield_to_maturity=Decimal(str(ytm)),
        maturity_date=maturity,
        status=status,  # type: ignore[arg-type]
        issuer="Министерство финансов",
        fetched_at=datetime_now(),
    )


def datetime_now():
    from datetime import datetime

    return datetime.now(UTC)


def test_allocate_basic() -> None:
    bonds = [
        _bond("A", 5, "USD", date(2028, 1, 1)),
        _bond("B", 7, "BYN", date(2030, 1, 1)),
        _bond("C", 3, "XAU", date(2026, 1, 1)),
        _bond("D", 6, "USD", date(2032, 1, 1)),
    ]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Balanced")
    alloc = allocate(bonds, prefs, top_n=3)
    assert len(alloc.items) == 3
    assert alloc.strategy == "Balanced"
    assert sum(alloc.items.values()) <= Decimal("10000") + Decimal("0.05")


def test_rank_bonds_aggressive_vs_conservative() -> None:
    bonds = [
        _bond("LOW", 2, "USD", date(2027, 1, 1)),
        _bond("HIGH", 12, "BYN", date(2030, 1, 1)),
    ]
    aggressive = rank_bonds(bonds, "Aggressive")
    conservative = rank_bonds(bonds, "Conservative")
    assert aggressive[0].internal_id in {"HIGH", "LOW"}
    assert conservative[0].internal_id in {"HIGH", "LOW"}


def test_rebalance_returns_deltas() -> None:
    bonds = [
        _bond("A", 5, "USD", date(2028, 1, 1)),
        _bond("B", 6, "USD", date(2029, 1, 1)),
        _bond("C", 7, "USD", date(2030, 1, 1)),
    ]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("3000"), strategy="Balanced")
    current = {"A": Decimal("1000"), "B": Decimal("1000"), "C": Decimal("1000")}
    target, deltas = rebalance(current, bonds, prefs)
    assert target.items
    assert isinstance(deltas, dict)


def test_scenario_bull_usd() -> None:
    res = run_scenario(
        "Bull USD",
        current_usd_byn=Decimal("3.30"),
        usd_share=0.5,
        byn_share=0.5,
    )
    assert res.fx_change_pct > 0
    assert res.usd_byn_end > res.usd_byn_start
    assert res.worst_position == "BYN"


def test_scenario_bull_byn() -> None:
    res = run_scenario(
        "Bull BYN",
        current_usd_byn=Decimal("3.30"),
        usd_share=0.5,
        byn_share=0.5,
    )
    assert res.fx_change_pct < 0
    assert res.worst_position == "USD"


def test_scenario_stress() -> None:
    res = run_scenario(
        "Stress",
        current_usd_byn=Decimal("3.30"),
        usd_share=0.5,
        byn_share=0.5,
    )
    assert res.fx_change_pct < -20


def test_run_all_scenarios() -> None:
    results = run_all_scenarios(
        current_usd_byn=Decimal("3.30"),
        usd_share=0.5,
        byn_share=0.5,
    )
    assert len(results) == 4
    names = [r.scenario for r in results]
    assert set(names) == {"Bull USD", "Neutral", "Bull BYN", "Stress"}
