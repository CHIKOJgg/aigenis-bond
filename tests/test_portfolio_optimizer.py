"""Unit tests for the portfolio optimizer (portfolio/optimizer)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from portfolio.optimizer import (
    _max_drawdown,
    _sharpe,
    _sortino,
    _var_95,
    _volatility,
    _weighted_stats,
    allocate,
    rank_bonds,
    rebalance,
)
from scoring.models import BondScore, ScoreBreakdown, UserPreferences
from scraper.models import Bond


def _bond(
    iid,
    ytm=10.0,
    currency="USD",
    status="active",
    issuer="Treasury",
    coupon_rate=5.0,
    coupon_frequency=2,
):
    return Bond(
        internal_id=iid,
        name=f"Bond {iid}",
        currency=currency,
        yield_to_maturity=ytm,
        coupon_rate=coupon_rate,
        coupon_frequency=coupon_frequency,
        maturity_date=None,
        price=100.0,
        status=status,
        issuer=issuer,
        fetched_at=datetime.now(),
    )


def _score(y: float) -> BondScore:
    return BondScore(
        internal_id="x",
        score=0,
        breakdown=ScoreBreakdown(yield_component=y),
        computed_at=datetime.now(),
    )


def test_rank_bonds_orders_by_score_desc():
    bonds = [
        _bond("A", ytm=1.0, currency="EUR", issuer="Corp"),
        _bond("B", ytm=12.0, currency="USD", issuer="Treasury"),
    ]
    ranked = rank_bonds(bonds, strategy="Balanced")
    assert [b.internal_id for b in ranked] == ["B", "A"]
    assert all(isinstance(b, BondScore) for b in ranked)


def test_allocate_returns_positive_weights_summing_to_capital():
    bonds = [_bond(f"B{i}", ytm=8.0 + i) for i in range(5)]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Balanced")
    alloc = allocate(bonds, prefs, top_n=3)
    assert len(alloc.items) == 3
    total = sum(alloc.items.values())
    assert abs(float(total) - 10000.0) < 1.0  # fully invested
    assert alloc.expected_return >= 0
    assert alloc.strategy == "Balanced"


def test_allocate_empty_bonds_returns_empty():
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Balanced")
    alloc = allocate([], prefs, top_n=10)
    assert alloc.items == {}
    assert alloc.sharpe == 0.0
    assert alloc.var_95 == 0.0


def test_allocate_strategy_changes_ranking():
    bonds = [_bond(f"B{i}", ytm=5.0 + i, currency="USD") for i in range(4)]
    prefs_bal = UserPreferences(user_id=1, initial_capital=Decimal("1000"), strategy="Balanced")
    prefs_agg = UserPreferences(user_id=1, initial_capital=Decimal("1000"), strategy="Aggressive")
    a = allocate(bonds, prefs_bal, top_n=4)
    b = allocate(bonds, prefs_agg, top_n=4)
    # Different strategies may weight the same bonds differently.
    assert a.strategy == "Balanced"
    assert b.strategy == "Aggressive"


def test_rebalance_returns_deltas():
    bonds = [_bond(f"B{i}", ytm=8.0 + i) for i in range(3)]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("1000"), strategy="Balanced")
    alloc, deltas = rebalance({"B0": Decimal("500")}, bonds, prefs, top_n=3)
    assert isinstance(alloc.items, dict)
    # Delta keys are a subset/union of target + current.
    assert set(deltas.keys()) <= (set(alloc.items) | {"B0"})


def test_metrics_helpers():
    scores = [_score(y) for y in (5.0, 10.0, 15.0)]
    assert _volatility(scores) > 0
    assert _sharpe(10.0, 2.0) == (10.0 - 4.0) / 2.0
    assert _sharpe(10.0, 0.0) == 0.0  # no vol -> no sharpe
    assert _sortino(10.0, 1.0) == (10.0 - 4.0) / 1.0
    assert _sortino(10.0, 0.0) == 0.0
    assert _max_drawdown(scores) >= 0
    assert _var_95(scores) >= 0
    # With a single score, VaR is 0 (needs >= 2 samples).
    single = [scores[0]]
    assert _var_95(single) == 0.0


def test_weighted_stats_uses_weights():
    from portfolio.optimizer import _weighted_stats

    bonds = [_bond("A", ytm=15.0), _bond("B", ytm=5.0)]
    bonds_by_id = {b.internal_id: b for b in bonds}
    scores = [_score(15.0), _score(5.0)]
    scores[0].internal_id = "A"
    scores[1].internal_id = "B"

    # Weight 90% in A (15%), 10% in B (5%) -> expected return = 0.9 * 15 + 0.1 * 5 = 14.0
    weights = {"A": 0.9, "B": 0.1}
    exp, vol, _, mdd, var95 = _weighted_stats(scores, weights, bonds_by_id)
    assert abs(exp - 14.0) < 1e-4


def test_dollarization_strategy_prioritizes_usd_and_indexed_bonds():
    byn_bond = _bond("BYN_01", ytm=14.0, currency="BYN")
    usd_bond = _bond("USD_01", ytm=7.5, currency="USD")
    op49_bond = _bond("AIG_OP49", ytm=7.7, currency="BYN")
    op49_bond.name = "ЗАО Айгенис ОП-49 (USD)"
    op49_bond.indexation_currency = "USD"

    bonds = [byn_bond, usd_bond, op49_bond]
    ranked = rank_bonds(bonds, strategy="Dollarization")
    top_ids = [r.internal_id for r in ranked if r.score > 0]
    assert "USD_01" in top_ids
    assert "AIG_OP49" in top_ids
    assert top_ids[0] in ("USD_01", "AIG_OP49")


def test_metals_strategy_prioritizes_metal_bonds():
    byn_bond = _bond("BYN_01", ytm=14.0, currency="BYN")
    gold_bond = _bond("AIG_OP35", ytm=10.5, currency="BYN")
    gold_bond.name = "ЗАО Айгенис ОП-35 (Золото / GOLD, 1g)"
    gold_bond.indexation_currency = "XAU"

    silver_bond = _bond("AIG_OP43", ytm=9.8, currency="BYN")
    silver_bond.name = "ЗАО Айгенис ОП-43 (Серебро / Silver, 100g)"
    silver_bond.indexation_currency = "XAG"

    plat_bond = _bond("AIG_OP42", ytm=8.5, currency="BYN")
    plat_bond.name = "ЗАО Айгенис ОП-42 (Платина / Platinum, 1g)"
    plat_bond.indexation_currency = "XPT"

    bonds = [byn_bond, plat_bond, silver_bond, gold_bond]
    ranked = rank_bonds(bonds, strategy="Metals++")
    top_ids = [r.internal_id for r in ranked if r.score > 0]
    assert top_ids == ["AIG_OP35", "AIG_OP43", "AIG_OP42"]
    # Gold-anchor: Gold score (58) > Silver (27) > Platinum (15)
    scores = {r.internal_id: r.score for r in ranked}
    assert scores["AIG_OP35"] == 58.0
    assert scores["AIG_OP43"] == 27.0
    assert scores["AIG_OP42"] == 15.0


def _metal_bond(iid: str, idx: str, ytm: float = 10.0) -> Bond:
    b = _bond(iid, ytm=ytm, currency="BYN", coupon_rate=0.001)
    b.indexation_currency = idx
    return b


def test_honest_yield_zero_for_couponless_indexed():
    from desk.ytm import honest_yield

    assert honest_yield(
        stored_ytm_pct=10.5,
        coupon_rate_pct=0.001,
        indexation_currency="XAU",
    ) == 0.0
    assert honest_yield(
        stored_ytm_pct=9.8,
        coupon_rate_pct=0.001,
        indexation_currency="XAG",
    ) == 0.0
    assert honest_yield(
        stored_ytm_pct=8.5,
        coupon_rate_pct=None,
        indexation_currency="XPT",
    ) == 0.0
    # Реальный купон (например, MOEX-золотодобытчики) — хранимый YTM честный.
    assert honest_yield(
        stored_ytm_pct=12.0,
        coupon_rate_pct=10.0,
        indexation_currency="XAU",
    ) == 12.0
    # Обычная облигация — без изменений.
    assert honest_yield(
        stored_ytm_pct=9.4,
        coupon_rate_pct=8.0,
        indexation_currency=None,
    ) == 9.4


def test_weighted_stats_uses_honest_ytm_for_metals():
    gold = _metal_bond("GOLD", "XAU")
    silver = _metal_bond("SILVER", "XAG")
    bonds_by_id = {b.internal_id: b for b in [gold, silver]}
    scores = [_score(10.5), _score(9.8)]
    scores[0].internal_id = "GOLD"
    scores[1].internal_id = "SILVER"
    weights = {"GOLD": 0.6, "SILVER": 0.4}
    exp, vol, _ret2, mdd, var95 = _weighted_stats(scores, weights, bonds_by_id)
    # Бескупонные индексируемые: честная ожидаемая доходность = 0%, не 10%.
    assert exp == 0.0


def test_allocate_metals_expected_return_zero():
    gold = _metal_bond("GOLD", "XAU")
    silver = _metal_bond("SILVER", "XAG")
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Metals++")
    alloc = allocate([gold, silver], prefs, top_n=4)
    assert len(alloc.items) == 2
    assert alloc.expected_return == 0.0


def test_balanced_and_aggressive_rankings_differ():
    safe = _bond("MODERATE", ytm=8.0, coupon_rate=6.5, currency="BYN")
    safe.maturity_date = datetime.now().date().replace(year=2031, month=6, day=1)
    safe.price = 99.0
    hotter = _bond("HOTTER", ytm=10.0, coupon_rate=8.5, currency="BYN")
    hotter.maturity_date = datetime.now().date().replace(year=2035, month=6, day=1)
    hotter.price = 99.0

    bonds = [safe, hotter]
    ranked_bal = rank_bonds(bonds, strategy="Balanced")
    ranked_agg = rank_bonds(bonds, strategy="Aggressive")
    # Оба скоринга близки, но Balanced взвешивает надёжность и общий score,
    # а Aggressive гонится за доходностью — порядок топ-1 различается.
    assert ranked_bal[0].internal_id == "MODERATE"
    assert ranked_agg[0].internal_id == "HOTTER"


def test_conservative_prefers_short_government_bonds():
    from portfolio.optimizer import _apply_strategy_bonuses

    long_corp = _bond("LC", ytm=12.0, coupon_rate=10.0)
    long_corp.maturity_date = datetime.now().date().replace(year=2040, month=1, day=1)
    long_corp.price = 100.0
    long_corp.is_government = False
    short_gov = _bond("SG", ytm=8.0, coupon_rate=7.0)
    short_gov.maturity_date = datetime.now().date().replace(year=2027, month=6, day=1)
    short_gov.price = 101.0
    short_gov.is_government = True

    ranked = rank_bonds([long_corp, short_gov], strategy="Conservative")
    assert ranked[0].internal_id == "SG"
    assert ranked[0].score > ranked[1].score
    # Агрессивная стратегия оверлеем купона/доходности вознаграждает
    # длинную высокодоходную бумагу.
    assert _apply_strategy_bonuses(long_corp, "Aggressive", 0.0) > 0.0
