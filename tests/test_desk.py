"""Pure-math tests for the Fixed Income Desk analytics.

These verify numerical correctness of the core calculations without any DB or
network access, so they run fast and are a good safety net for refactors.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from desk.carry import carry_for_bond, rank_carry
from desk.duration import duration_report
from desk.models import CurvePoint, NelsonSiegelParams, RepoDeal, StressResult, YieldCurve
from desk.relative_value import relative_value_signals, signals_from_curve
from desk.repo import haircut_by_issuer, repo_deal
from desk.stress import PRESET_SCENARIOS, run_all_presets, run_stress
from desk.yield_curve import _ns_rate, fit_nelson_siegel
from scraper.models import Bond


def _bond(
    *,
    ytm: float = 8.0,
    coupon: float = 8.0,
    freq: int = 2,
    maturity: str = "2030-01-01",
    nominal: float = 1000.0,
) -> Bond:
    return Bond(
        internal_id="TEST-1",
        name="Test Bond",
        currency="BYN",
        yield_to_maturity=Decimal(str(ytm)),
        coupon_rate=Decimal(str(coupon)),
        coupon_frequency=freq,
        maturity_date=maturity,
        price=Decimal("100.0"),
        issuer="Test Issuer",
        status="active",
        nominal=Decimal(str(nominal)),
        fetched_at=datetime(2026, 1, 1),
    )


def test_duration_report_positive_for_valid_bond():
    rep = duration_report(_bond())
    assert rep.macaulay_duration > 0
    assert rep.modified_duration > 0
    # Modified duration must be lower than Macaulay for positive yield.
    assert rep.modified_duration < rep.macaulay_duration
    assert rep.dv01 >= 0


def test_duration_report_handles_missing_inputs():
    empty = Bond(
        internal_id="X",
        name="n",
        currency="BYN",
        status="active",
        fetched_at=datetime(2026, 1, 1),
    )
    rep = duration_report(empty)
    assert rep.macaulay_duration == 0.0
    assert rep.modified_duration == 0.0


def test_duration_zero_coupon_is_less_than_par_coupon():
    zero = duration_report(_bond(coupon=0.0))
    par = duration_report(_bond(coupon=10.0))
    # Higher coupon → lower duration (all else equal).
    assert zero.macaulay_duration > par.macaulay_duration


def test_nelson_siegel_fit_reproduces_curve():
    true = NelsonSiegelParams(beta0=5.0, beta1=-1.5, beta2=1.0, tau=2.5)
    tenor_vals = {"1Y": 1.0, "2Y": 2.0, "3Y": 3.0, "5Y": 5.0, "7Y": 7.0, "10Y": 10.0}
    points = [
        CurvePoint(tenor=t, years=v, rate_pct=_ns_rate(v, **true.model_dump()))
        for t, v in tenor_vals.items()
    ]
    fitted = fit_nelson_siegel(points)
    # NS is not parameter-identifiable, but the fitted curve must reproduce
    # the original rates closely.
    for v in tenor_vals.values():
        expected = _ns_rate(v, **true.model_dump())
        got = _ns_rate(v, fitted.beta0, fitted.beta1, fitted.beta2, fitted.tau)
        assert abs(expected - got) < 1e-2


# --------------------------------------------------------------------------- #
# Relative Value
# --------------------------------------------------------------------------- #
def _rv_bond(
    internal_id: str,
    ytm: float,
    currency: str = "USD",
    maturity: str = "2030-01-01",
    coupon_rate: Decimal | None = None,
    coupon_frequency: int | None = None,
) -> Bond:
    return Bond(
        internal_id=internal_id,
        name=internal_id,
        currency=currency,
        yield_to_maturity=Decimal(str(ytm)),
        coupon_rate=coupon_rate,
        coupon_frequency=coupon_frequency,
        maturity_date=maturity,
        status="active",
        fetched_at=datetime(2026, 1, 1),
    )


def test_relative_value_signals_mark_rich_and_cheap():
    bonds = [
        _rv_bond("A", 8.0),
        _rv_bond("B", 12.0),  # rich
        _rv_bond("C", 4.0),  # cheap
        _rv_bond("D", 8.5),
    ]
    signals = relative_value_signals(bonds, asof=date(2026, 1, 1))
    by_id = {s.internal_id: s for s in signals}
    assert by_id["B"].side == "sell"
    assert by_id["C"].side == "buy"
    # Sorted by |z| descending: the extreme bond is first.
    assert signals[0].internal_id in {"B", "C"}


def test_relative_value_signals_need_at_least_three():
    bonds = [_rv_bond("A", 8.0), _rv_bond("B", 9.0)]
    assert relative_value_signals(bonds, asof=date(2026, 1, 1)) == []


def test_signals_from_curve_requires_three_points():
    params = NelsonSiegelParams(beta0=5.0, beta1=-1.0, beta2=0.5, tau=2.5)
    # Fewer than 3 points → no signals.
    sparse = _make_curve("USD", params)
    sparse.points = sparse.points[:2]
    assert signals_from_curve(sparse) == []


def _make_curve(currency: str, params: NelsonSiegelParams):

    tenors = {"1Y": 1.0, "3Y": 3.0, "5Y": 5.0, "10Y": 10.0}
    points = [CurvePoint(tenor=t, years=y, rate_pct=_ns_rate(y, **params.model_dump())) for t, y in tenors.items()]
    return YieldCurve(currency=currency, observed_at=datetime(2026, 1, 1), points=points, ns_params=params)


def test_signals_from_curve_full():
    curve = _make_curve("USD", NelsonSiegelParams(beta0=5.0, beta1=-1.0, beta2=0.5, tau=2.5))
    signals = signals_from_curve(curve)
    assert len(signals) == 4
    assert all(s.peer_currency == "USD" for s in signals)


# --------------------------------------------------------------------------- #
# Carry
# --------------------------------------------------------------------------- #
def test_carry_for_bond_positive_coupon_minus_funding():
    bond = _rv_bond("A", 9.0, coupon_rate=Decimal("10"), coupon_frequency=2)
    ct = carry_for_bond(bond, funding_rate_pct=5.0, asof=date(2026, 1, 1))
    assert ct is not None
    assert ct.coupon_pct == 10.0
    assert ct.expected_pnl_pct > 0  # coupon > funding


def test_carry_for_bond_returns_none_without_inputs():
    bond = Bond(internal_id="X", name="x", currency="USD", status="active", fetched_at=datetime(2026, 1, 1))
    assert carry_for_bond(bond, funding_rate_pct=5.0) is None


def test_rank_carry_sorts_descending():
    bonds = [
        _rv_bond("A", 6.0, coupon_rate=Decimal("5")),
        _rv_bond("B", 12.0, coupon_rate=Decimal("14")),
    ]
    ranked = rank_carry(bonds, funding_rate_pct=5.0)
    assert ranked[0].internal_id == "B"


# --------------------------------------------------------------------------- #
# Repo
# --------------------------------------------------------------------------- #
def test_repo_deal_haircut_reduces_collateral():
    bond = _rv_bond("A", 8.0)
    deal: RepoDeal = repo_deal(bond, notional=Decimal("1000"), haircut_pct=5.0, repo_rate_pct=10.0, tenor_days=30)
    assert deal.collateral_value == Decimal("1000.00")
    assert deal.cash_lent == Decimal("950.00")  # 1000 - 5%
    assert deal.accrued_interest > 0


def test_haircut_by_issuer_tiers():
    assert haircut_by_issuer("Министерство финансов") == 1.0
    assert haircut_by_issuer("Some Bank") == 3.0
    assert haircut_by_issuer("Some Corp") == 5.0
    assert haircut_by_issuer(None) == 5.0


# --------------------------------------------------------------------------- #
# Stress
# --------------------------------------------------------------------------- #
def test_run_stress_parallel_up_shock_lowers_value():
    bond = _rv_bond("A", 8.0, maturity="2030-01-01")
    bonds = [(bond, Decimal("1000"))]
    up = run_stress(PRESET_SCENARIOS["parallel_+100bp"], bonds, base_currency="USD")
    down = run_stress(PRESET_SCENARIOS["parallel_-100bp"], bonds, base_currency="USD")
    assert isinstance(up, StressResult)
    assert up.pnl_pct < 0  # rates up → price down
    assert down.pnl_pct > 0  # rates down → price up


def test_run_stress_fx_shock_hits_non_base_currency():
    usd_bond = _rv_bond("A", 8.0, currency="USD", maturity="2030-01-01")
    byn_bond = _rv_bond("B", 8.0, currency="BYN", maturity="2030-01-01")
    bonds = [(usd_bond, Decimal("1000")), (byn_bond, Decimal("1000"))]
    fx = run_stress(PRESET_SCENARIOS["fx_shock_-20%"], bonds, base_currency="USD")
    # BYN position takes the FX hit; USD does not.
    assert fx.by_position["B"] < fx.by_position["A"]


def test_run_all_presets_returns_seven_scenarios():
    bond = _rv_bond("A", 8.0, maturity="2030-01-01")
    results = run_all_presets([(bond, Decimal("1000"))], base_currency="USD")
    assert len(results) == 7
    assert set(results) == set(PRESET_SCENARIOS)
