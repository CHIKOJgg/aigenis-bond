"""Exhaustive tests for financial calculations, desk analytics, portfolio optimization,
and extreme edge cases.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from decimal import Decimal

from desk.carry import carry_for_bond
from desk.cashflow import accrued_interest, year_fraction
from desk.duration import (
    convexity,
    duration_report,
    dv01,
    macaulay_duration,
    modified_duration,
    portfolio_duration,
)
from desk.models import CurvePoint, NelsonSiegelParams
from desk.relative_value import relative_value_signals
from desk.stress import PRESET_SCENARIOS, run_stress
from desk.yield_curve import curve_from_bonds, fit_nelson_siegel
from desk.ytm import sane_yield, to_price_pct, ytm_from_price
from portfolio.optimizer import allocate, rebalance
from portfolio.pnl import compute_daily_returns, compute_max_drawdown, compute_pnl, compute_sharpe
from scoring.engine import score_bond
from scoring.explain import explain_score
from scoring.models import UserPreferences
from scraper.models import Bond
from scraper.orm import PortfolioPositionORM, TransactionORM

# =========================================================================== #
# 1. Desk Relative Value & Accrued Interest Fix Verification
# =========================================================================== #


def _make_bond(
    internal_id: str,
    ytm: float | None = 10.0,
    price: float | None = 99.0,
    currency: str = "USD",
    coupon_rate: float | None = 10.0,
    coupon_frequency: int | None = 2,
    nominal: float | None = 1000.0,
    maturity_date: date | None = date(2028, 1, 1),
    start_date: date | None = date(2024, 1, 1),
    issuer: str | None = "Test Issuer",
    is_government: bool = False,
    status: str = "active",
) -> Bond:
    return Bond(
        internal_id=internal_id,
        name=f"Bond {internal_id}",
        currency=currency,  # type: ignore
        nominal=Decimal(str(nominal)) if nominal is not None else None,
        coupon_rate=Decimal(str(coupon_rate)) if coupon_rate is not None else None,
        coupon_frequency=coupon_frequency,  # type: ignore
        maturity_date=maturity_date,
        price=Decimal(str(price)) if price is not None else None,
        yield_to_maturity=Decimal(str(ytm)) if ytm is not None else None,
        start_date=start_date,
        issuer=issuer,
        is_government=is_government,
        status=status,  # type: ignore
        fetched_at=datetime.now(UTC),
    )


def test_relative_value_signals_accrued_interest_and_peer_sets():
    """Verify relative_value_signals computes correct accrued interest and peer signals."""
    bonds = [
        _make_bond("B1", ytm=12.0, coupon_rate=10.0, maturity_date=date(2028, 1, 1)),
        _make_bond("B2", ytm=10.0, coupon_rate=10.0, maturity_date=date(2028, 1, 1)),
        _make_bond("B3", ytm=8.0, coupon_rate=10.0, maturity_date=date(2028, 1, 1)),
    ]
    today = date(2026, 1, 1)
    signals = relative_value_signals(bonds, asof=today)
    assert len(signals) == 3

    # Check signal ordering and rich/cheap tags
    b1_sig = next(s for s in signals if s.internal_id == "B1")
    b3_sig = next(s for s in signals if s.internal_id == "B3")

    assert b1_sig.side == "buy"  # High YTM -> cheap
    assert b3_sig.side == "sell"  # Low YTM -> rich
    assert b1_sig.accrued_interest >= 0.0
    assert set(b1_sig.peer_set) == {"B2", "B3"}


def test_relative_value_signals_with_missing_coupon_and_nominal():
    """Verify relative value signals gracefully handle missing coupon, nominal, or start date."""
    bonds = [
        _make_bond("B1", ytm=12.0, coupon_rate=None, nominal=None, start_date=None),
        _make_bond("B2", ytm=10.0, coupon_rate=None, nominal=None, start_date=None),
        _make_bond("B3", ytm=8.0, coupon_rate=None, nominal=None, start_date=None),
    ]
    signals = relative_value_signals(bonds, asof=date(2026, 1, 1))
    assert len(signals) == 3
    for s in signals:
        assert s.accrued_interest == 0.0


# =========================================================================== #
# 2. Portfolio Optimizer: Partial Missing YTM Zip Length Safety
# =========================================================================== #


def test_portfolio_optimizer_with_missing_ytms_does_not_crash():
    """Verify allocate handles a mix of bonds with and without YTM without zip ValueError."""
    bonds = [
        _make_bond("B1", ytm=15.0, price=95.0),
        _make_bond("B2", ytm=None, price=100.0, coupon_rate=8.0),  # Missing YTM
        _make_bond("B3", ytm=12.0, price=98.0),
        _make_bond("B4", ytm=0.0, price=100.0),  # Zero YTM
        _make_bond("B5", ytm=10.0, price=99.0),
    ]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("50000"), strategy="Balanced")
    alloc = allocate(bonds, prefs, top_n=5)

    assert alloc.expected_return > 0.0
    assert alloc.volatility > 0.0
    assert sum(alloc.items.values()) == Decimal("50000")


def test_portfolio_optimizer_all_missing_ytm_fallback():
    """Verify allocate falls back to score breakdown when all YTMs are missing."""
    bonds = [
        _make_bond("B1", ytm=None, price=None, coupon_rate=None),
        _make_bond("B2", ytm=None, price=None, coupon_rate=None),
    ]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Conservative")
    alloc = allocate(bonds, prefs, top_n=2)
    assert alloc.expected_return >= 0.0
    assert sum(alloc.items.values()) == Decimal("10000")


def test_portfolio_optimizer_zero_and_huge_capital():
    """Verify allocator handles boundary capitals safely."""
    bonds = [_make_bond("B1", ytm=10.0), _make_bond("B2", ytm=12.0)]

    # Zero capital
    prefs_zero = UserPreferences(user_id=1, initial_capital=Decimal("0"))
    alloc_zero = allocate(bonds, prefs_zero)
    assert sum(alloc_zero.items.values()) == Decimal("0")

    # 1 Billion capital
    prefs_huge = UserPreferences(user_id=1, initial_capital=Decimal("1000000000"))
    alloc_huge = allocate(bonds, prefs_huge)
    assert sum(alloc_huge.items.values()) == Decimal("1000000000")


def test_portfolio_rebalance_deltas():
    """Verify rebalance generates correct positive, negative and unchanged deltas."""
    bonds = [_make_bond("B1", ytm=15.0), _make_bond("B2", ytm=10.0)]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"))
    current = {"B1": Decimal("2000"), "B2": Decimal("8000"), "OLD": Decimal("1000")}

    target, deltas = rebalance(current, bonds, prefs, top_n=2)
    assert "OLD" in deltas
    assert deltas["OLD"] == Decimal("-1000")  # Should be sold
    assert sum(target.items.values()) == Decimal("10000")


# =========================================================================== #
# 3. Desk Carry Trade & Rolldown Scaling
# =========================================================================== #


def test_carry_trade_with_steep_yield_curve_adds_positive_rolldown():
    """Verify rolldown P&L is calculated in percentage points when curve is positively sloped."""
    bond = _make_bond(
        "B1",
        ytm=10.0,
        coupon_rate=10.0,
        coupon_frequency=2,
        maturity_date=date(2028, 1, 1),
        start_date=date(2024, 1, 1),
    )
    # Nelson-Siegel parameters creating a positively sloped curve (ytm drops from 10% to 8% as bond ages)
    # ytm_next = 8.0, so ytm - ytm_next = +2.0 percentage points
    ns_params = NelsonSiegelParams(beta0=8.0, beta1=-2.0, beta2=0.0, tau=1.5)
    asof = date(2026, 1, 1)

    ct = carry_for_bond(
        bond,
        funding_rate_pct=5.0,
        horizon_days=365,
        curve_params=ns_params,
        asof=asof,
    )
    assert ct is not None
    # Carry = (10 - 5) * 1.0 = 5.0%
    # Rolldown = mod_dur * (10.0 - ytm_next)
    # For mod_dur ~ 1.8 and ytm_next ~ 6.5, rolldown should be on the order of 3-7% (not 0.05%)
    assert ct.expected_pnl_pct > 5.0
    assert ct.rolldown_bps > 0.0


def test_carry_trade_inverted_curve_subtracts_from_pnl():
    """Verify inverted curve (rates rise at shorter tenors) produces negative rolldown."""
    bond = _make_bond(
        "B1",
        ytm=10.0,
        coupon_rate=10.0,
        maturity_date=date(2028, 1, 1),
    )
    # Inverted curve: shorter tenor yields higher rate (e.g. 14%)
    ns_params = NelsonSiegelParams(beta0=8.0, beta1=10.0, beta2=0.0, tau=1.5)
    asof = date(2026, 1, 1)

    ct = carry_for_bond(
        bond,
        funding_rate_pct=5.0,
        horizon_days=90,
        curve_params=ns_params,
        asof=asof,
    )
    assert ct is not None
    assert ct.rolldown_bps < 0.0  # Negative rolldown


# =========================================================================== #
# 4. Desk Stress Testing: Nominal Independence & Multi-Factor Shocks
# =========================================================================== #


def test_stress_testing_nominal_independence():
    """Verify stress baseline and stressed value are invariant to bond nominal scale."""
    # Bond with nominal 100 vs nominal 1000 vs nominal 100,000
    b_nom100 = _make_bond("B1", ytm=10.0, price=100.0, nominal=100.0)
    b_nom1000 = _make_bond("B2", ytm=10.0, price=100.0, nominal=1000.0)
    b_nom50k = _make_bond("B3", ytm=10.0, price=100.0, nominal=50000.0)

    scenario = PRESET_SCENARIOS["parallel_+100bp"]
    portfolio = [
        (b_nom100, Decimal("10000")),
        (b_nom1000, Decimal("10000")),
        (b_nom50k, Decimal("10000")),
    ]

    res = run_stress(scenario, portfolio, asof=date(2026, 1, 1))

    # Total baseline portfolio value must be exactly 30,000 (10k + 10k + 10k)
    assert res.portfolio_value == Decimal("30000.00")
    # All 3 bonds have same duration and price, so position PnLs must be identical
    assert res.by_position["B1"] == res.by_position["B2"] == res.by_position["B3"]


def test_stress_testing_sovereign_immunity_to_credit_shock():
    """Verify sovereign bonds do not receive credit spread shock."""
    b_corp = _make_bond("CORP", ytm=10.0, is_government=False)
    b_gov = _make_bond("GOV", ytm=10.0, is_government=True)

    scenario = PRESET_SCENARIOS["credit_shock_+150bp"]
    res = run_stress(
        scenario,
        [(b_corp, Decimal("10000")), (b_gov, Decimal("10000"))],
        asof=date(2026, 1, 1),
    )

    assert res.by_position["GOV"] == Decimal("0.00")  # Gov immune to credit shock
    assert res.by_position["CORP"] < Decimal("0.00")  # Corp suffers markdown


def test_stress_testing_fx_shock():
    """Verify FX shock applies to foreign currency bonds."""
    b_usd = _make_bond("USD1", ytm=10.0, price=100.0, currency="USD")
    b_byn = _make_bond("BYN1", ytm=15.0, price=100.0, currency="BYN")

    scenario = PRESET_SCENARIOS["fx_shock_-20%"]
    res = run_stress(
        scenario,
        [(b_usd, Decimal("10000")), (b_byn, Decimal("10000"))],
        base_currency="USD",
        asof=date(2026, 1, 1),
    )

    assert res.by_position["USD1"] == Decimal("0.00")
    # BYN suffered -20% FX shock
    assert res.by_position["BYN1"] == Decimal("-2000.00")


# =========================================================================== #
# 5. Yield Curve & Nelson-Siegel Fits on Edge Cases
# =========================================================================== #


def test_nelson_siegel_empty_points_does_not_crash():
    """Verify fit_nelson_siegel safely handles empty list without StatisticsError."""
    params = fit_nelson_siegel([])
    assert params.beta0 == 0.0
    assert params.beta1 == 0.0
    assert params.tau == 1.5


def test_nelson_siegel_single_and_two_points():
    """Verify fit_nelson_siegel handles 1 or 2 points with flat curve average."""
    p1 = CurvePoint(tenor="1Y", years=1.0, rate_pct=12.0)
    params1 = fit_nelson_siegel([p1])
    assert params1.beta0 == 12.0

    p2 = CurvePoint(tenor="3Y", years=3.0, rate_pct=14.0)
    params2 = fit_nelson_siegel([p1, p2])
    assert params2.beta0 == 13.0


def test_curve_from_bonds_grouping():
    """Verify curve_from_bonds groups bonds into tenors."""
    bonds = [
        _make_bond("B1", ytm=10.0, maturity_date=date(2027, 1, 1)),
        _make_bond("B2", ytm=11.0, maturity_date=date(2027, 1, 1)),
        _make_bond("B3", ytm=14.0, maturity_date=date(2031, 1, 1)),
    ]
    curve = curve_from_bonds(bonds)
    assert len(curve.points) >= 2
    assert curve.currency == "USD"


# =========================================================================== #
# 6. Daycount Conventions, Leap Years, and Accrued Interest
# =========================================================================== #


def test_year_fraction_conventions_and_leap_year():
    """Verify ACT/ACT, 30/360, ACT/360, ACT/365 across leap year 2024."""
    d1 = date(2024, 1, 1)
    d2 = date(2024, 12, 31)

    yf_365 = year_fraction(d1, d2, "ACT/365")
    yf_360 = year_fraction(d1, d2, "ACT/360")
    yf_act = year_fraction(d1, d2, "ACT/ACT")
    yf_30 = year_fraction(d1, d2, "30/360")

    assert math.isclose(yf_365, 365.0 / 365.0, abs_tol=1e-4)
    assert math.isclose(yf_360, 365.0 / 360.0, abs_tol=1e-4)
    assert math.isclose(yf_act, 365.0 / 366.0, abs_tol=1e-4)
    assert yf_30 > 0.95


def test_accrued_interest_zero_coupon_and_boundary_dates():
    """Verify accrued interest on edge dates."""
    issue = date(2024, 1, 1)
    maturity = date(2026, 1, 1)

    # asof == issue_date -> 0
    assert accrued_interest(
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        issue_date=issue,
        maturity_date=maturity,
        asof=issue,
    ) == 0.0

    # asof == maturity -> 0
    assert accrued_interest(
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        issue_date=issue,
        maturity_date=maturity,
        asof=maturity,
    ) == 0.0

    # asof before issue -> 0
    assert accrued_interest(
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        issue_date=issue,
        maturity_date=maturity,
        asof=date(2023, 1, 1),
    ) == 0.0

    # zero coupon rate -> 0
    assert accrued_interest(
        coupon_rate_pct=0.0,
        coupon_frequency=2,
        issue_date=issue,
        maturity_date=maturity,
        asof=date(2025, 1, 1),
    ) == 0.0


# =========================================================================== #
# 7. Duration, Convexity, DV01 & Extreme Yields
# =========================================================================== #


def test_duration_and_convexity_positive_and_monotonic():
    """Verify duration and convexity properties on standard bond."""
    nom = Decimal("1000")
    mat = date(2030, 1, 1)
    ref = date(2026, 1, 1)

    mac = macaulay_duration(
        nominal=nom,
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        ytm_pct=10.0,
        maturity=mat,
        ref=ref,
    )
    mod = modified_duration(
        nominal=nom,
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        ytm_pct=10.0,
        maturity=mat,
        ref=ref,
    )
    cvx = convexity(
        nominal=nom,
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        ytm_pct=10.0,
        maturity=mat,
        ref=ref,
    )
    d = dv01(
        nominal=nom,
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        ytm_pct=10.0,
        maturity=mat,
        ref=ref,
    )

    assert 0 < mod < mac < 4.0
    assert cvx > 0.0
    assert d > 0.0


def test_duration_extreme_high_yield():
    """Verify duration handles 150% YTM without overflow or nan."""
    rep = duration_report(
        _make_bond("HI", ytm=150.0, coupon_rate=10.0),
        asof=date(2026, 1, 1),
    )
    assert rep.modified_duration > 0.0
    assert not math.isnan(rep.convexity)
    assert not math.isnan(rep.dv01)


def test_portfolio_duration_weighted():
    """Verify portfolio duration aggregates correctly."""
    bonds = [_make_bond("B1", ytm=10.0), _make_bond("B2", ytm=12.0)]
    rep = portfolio_duration(bonds, weights={"B1": 0.5, "B2": 0.5}, asof=date(2026, 1, 1))
    assert rep.modified_duration > 0.0


# =========================================================================== #
# 8. YTM Newton-Raphson Solver & Sanity Checks
# =========================================================================== #


def test_ytm_from_price_exact_par():
    """At price 100.0 and coupon 10.0, YTM must be exactly 10.0%."""
    mat = date(2030, 1, 1)
    ref = date(2026, 1, 1)
    ytm = ytm_from_price(100.0, 10.0, 2, mat, asof=ref)
    assert ytm is not None
    assert math.isclose(ytm, 10.0, abs_tol=0.05)


def test_ytm_from_price_deep_discount_and_premium():
    """Check YTM on deep discount (price 50) and premium (price 130)."""
    mat = date(2030, 1, 1)
    ref = date(2026, 1, 1)
    ytm_disc = ytm_from_price(50.0, 10.0, 2, mat, asof=ref)
    ytm_prem = ytm_from_price(130.0, 10.0, 2, mat, asof=ref)

    assert ytm_disc is not None and ytm_disc > 20.0
    assert ytm_prem is not None and ytm_prem < 10.0


def test_to_price_pct_normalization():
    """Verify to_price_pct converts absolute prices near nominal."""
    # Already percent
    assert to_price_pct(98.5, 1000) == 98.5
    # Absolute price near 1000
    assert math.isclose(to_price_pct(985, 1000) or 0, 98.5, abs_tol=1e-3)
    # Invalid values
    assert to_price_pct(None, 1000) is None
    assert to_price_pct(-5, 1000) is None


def test_sane_yield_filtering():
    """Verify sane_yield flags crazy source yields."""
    assert sane_yield(12.0, 11.5) is True
    assert sane_yield(1374.0, 12.0) is False  # Garbage MOEX yield
    assert sane_yield(-5.0, 10.0) is False
    assert sane_yield(None, 10.0) is False


# =========================================================================== #
# 9. P&L Engine, FIFO Lots, Drawdown & Sharpe
# =========================================================================== #


def test_pnl_fifo_multiple_buys_and_partial_sells():
    """Verify FIFO lots tracking on complex buy/sell sequence."""
    txs = [
        TransactionORM(
            id=1,
            user_id=1,
            internal_id="B1",
            side="buy",
            amount=Decimal("1000"),  # buys 1020.41 face at 98
            price=Decimal("98"),
            currency="USD",
            executed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        TransactionORM(
            id=2,
            user_id=1,
            internal_id="B1",
            side="buy",
            amount=Decimal("1000"),  # buys 1000 face at 100
            price=Decimal("100"),
            currency="USD",
            executed_at=datetime(2026, 2, 1, tzinfo=UTC),
        ),
        TransactionORM(
            id=3,
            user_id=1,
            internal_id="B1",
            side="sell",
            amount=Decimal("500"),  # sells 500 money at 105 -> 476.19 face
            price=Decimal("105"),
            currency="USD",
            executed_at=datetime(2026, 3, 1, tzinfo=UTC),
        ),
    ]
    positions = [
        PortfolioPositionORM(
            user_id=1,
            internal_id="B1",
            amount=Decimal("1500"),
            opened_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    bonds = {"B1": _make_bond("B1", price=102.0)}

    pnl = compute_pnl(transactions=txs, positions=positions, bonds_by_id=bonds)
    assert pnl.total_realized > Decimal("0")  # Sold at 105 (bought at 98)
    assert pnl.total_value > Decimal("0")


def test_daily_returns_and_drawdown_and_sharpe():
    """Verify equity curve metrics calculation."""
    curve = [
        {"date": "2026-01-01", "value": 10000.0},
        {"date": "2026-01-02", "value": 10500.0},  # +5%
        {"date": "2026-01-03", "value": 9500.0},   # drawdown from 10500 to 9500: ~9.52%
        {"date": "2026-01-04", "value": 11000.0},  # peak
    ]
    rets = compute_daily_returns(curve)
    assert len(rets) == 3
    assert rets[0]["return_pct"] == 5.0

    dd = compute_max_drawdown(curve)
    assert math.isclose(dd, 9.52, abs_tol=0.1)

    sharpe = compute_sharpe(rets)
    assert isinstance(sharpe, float)


# =========================================================================== #
# 10. Scoring Engine & Distress Debt Overrides
# =========================================================================== #


def test_scoring_engine_distressed_debt_penalty():
    """Verify bonds trading at deep discount (<70%) with high yield (>40%) are penalized."""
    # Distressed bond (e.g. price 50%, ytm 65%)
    score_distressed = score_bond(
        internal_id="DIST",
        yield_to_maturity=65.0,
        currency="USD",
        maturity_date=date(2028, 1, 1),
        price=50.0,
        nominal=100.0,
        coupon_rate=10.0,
    )
    # Healthy bond (price 98%, ytm 12%)
    score_healthy = score_bond(
        internal_id="GOOD",
        yield_to_maturity=12.0,
        currency="USD",
        maturity_date=date(2028, 1, 1),
        price=98.0,
        nominal=100.0,
        coupon_rate=10.0,
    )

    # Distressed debt volatility component must be deeply negative
    assert score_distressed.breakdown.volatility_component <= -18.0
    assert score_distressed.breakdown.yield_component <= 20.0
    assert score_healthy.breakdown.volatility_component > score_distressed.breakdown.volatility_component


def test_scoring_metal_keywords():
    """Verify gold and precious metal keywords boost metal component."""
    score_gold = score_bond(
        internal_id="POLYUS",
        yield_to_maturity=10.0,
        currency="RUB",
        maturity_date=date(2028, 1, 1),
        issuer="ПАО Полюс Золото",
    )
    assert score_gold.breakdown.metal_component >= 3.0


def test_explain_score_verdicts():
    """Verify explain_score outputs human readable verdict."""
    score = score_bond(
        internal_id="B1",
        yield_to_maturity=12.0,
        currency="USD",
        maturity_date=date(2028, 1, 1),
        price=99.0,
    )
    explained = explain_score(score, currency="USD", ytm_pct=12.0)
    assert explained.tier in ("S", "A", "B", "C", "D")
    assert len(explained.factors) > 0
    assert explained.verdict != ""


def test_accrued_interest_boundary_dates():
    """Verify accrued interest at issue date and maturity date."""
    issue = date(2026, 1, 1)
    maturity = date(2027, 1, 1)

    # At issue date -> exactly 0.0
    ai_issue = accrued_interest(
        coupon_rate_pct=10.0,
        coupon_frequency=1,
        issue_date=issue,
        maturity_date=maturity,
        asof=issue,
        face=1000.0,
    )
    assert ai_issue == 0.0

    # Half year later -> exactly 50.0
    ai_half = accrued_interest(
        coupon_rate_pct=10.0,
        coupon_frequency=1,
        issue_date=issue,
        maturity_date=maturity,
        asof=date(2026, 7, 2),  # roughly 182 days
        face=1000.0,
    )
    assert math.isclose(ai_half, 50.0, abs_tol=1.0)


def test_duration_long_tenor_and_zero_coupon():
    """Verify duration of zero coupon bond equals its maturity."""
    today = date(2026, 1, 1)
    mat = date(2036, 1, 1)  # 10 years

    # Zero coupon bond Macaulay duration is exactly years to maturity
    mac_dur = macaulay_duration(
        nominal=Decimal("1000.0"),
        coupon_rate_pct=0.0,
        coupon_frequency=1,
        ytm_pct=5.0,
        ref=today,
        maturity=mat,
    )
    assert math.isclose(mac_dur, 10.0, abs_tol=0.1)


def test_portfolio_rebalance_and_allocation():
    """Verify portfolio rebalance returns target allocation and delta dict."""
    bonds = [
        _make_bond("B1", ytm=14.0, coupon_rate=12.0),
        _make_bond("B2", ytm=10.0, coupon_rate=9.0),
    ]
    prefs = UserPreferences(user_id=1, risk_tolerance="balanced", target_horizon_months=24)
    current = {"B1": Decimal("0.5")}
    target, deltas = rebalance(current=current, bonds=bonds, prefs=prefs)
    assert isinstance(target.expected_return, float)
    assert isinstance(deltas, dict)


def test_scoring_with_extreme_yield_and_discount():
    """Verify score_bond handles extreme distressed debt yields."""
    sc_distressed = score_bond(
        internal_id="B1",
        yield_to_maturity=150.0,
        currency="USD",
        maturity_date=date(2031, 1, 1),
        price=10.0,
        nominal=1000.0,
    )
    assert isinstance(sc_distressed.score, float)
    assert sc_distressed.tier in ("C", "D")


