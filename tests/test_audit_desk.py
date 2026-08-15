"""Audit test suite for the Fixed Income Desk modules (desk/*).

Every numerical expectation is computed by hand from first principles and then
checked against the source formula; iterative solvers get small tolerances.

Note on SQLite/BIGINT: the root conftest.py recompiles ``BigInteger`` to plain
``INTEGER`` on the sqlite dialect (rowid alias), so the desk ORM tables can be
exercised against the in-memory test DB.  Without that shim, every desk INSERT
fails with ``NOT NULL constraint failed: <table>.id`` — a real deployment
hazard for any sqlite usage of scraper/orm/desk.py.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, update

from desk.carry import carry_for_bond
from desk.cashflow import accrued_interest, pricing_cashflows, year_fraction
from desk.duration import (
    _price_from_yield,
    convexity,
    duration_report,
    dv01,
    macaulay_duration,
    modified_duration,
)
from desk.models import (
    CarryTrade,
    CurvePoint,
    NelsonSiegelParams,
    RepoDeal,
    RVSignal,
    SpreadReport,
    StressResult,
    StressScenario,
    YieldCurve,
)
from desk.relative_value import relative_value_signals, signals_from_curve
from desk.repo import haircut_by_issuer, repo_deal
from desk.repository import (
    latest_rv_signals,
    latest_spread_reports,
    latest_stress_runs,
    save_carry_trades,
    save_curve_points,
    save_repo_deal,
    save_rv_signals,
    save_spread_reports,
    save_stress_run,
)
from desk.spreads import compute_spreads, solve_flat_yield
from desk.stress import PRESET_SCENARIOS, run_stress
from desk.yield_curve import (
    _ns_rate,
    curve_curvature,
    curve_from_bonds,
    curve_slope,
    fit_nelson_siegel,
    interpolate,
)
from desk.ytm import sane_yield, sanity_tolerance_pp, to_price_pct, ytm_from_price
from scraper.db import session_scope
from scraper.models import Bond
from scraper.orm import (
    CarryTradeORM,
    CurvePointORM,
    RepoDealORM,
    RVSignalORM,
    SpreadReportORM,
    StressRunORM,
)

ASOF = date(2026, 1, 1)


def _bond(
    *,
    internal_id: str = "BOND-1",
    name: str = "Test Bond",
    currency: str = "USD",
    ytm: float | None = 8.0,
    coupon: float | None = 8.0,
    freq: int = 2,
    maturity: str | date | None = "2030-01-01",
    price: float | None = 100.0,
    nominal: Decimal | float = Decimal("1000"),
    start_date: date | None = None,
    is_government: bool = False,
) -> Bond:
    return Bond(
        internal_id=internal_id,
        name=name,
        currency=currency,
        yield_to_maturity=Decimal(str(ytm)) if ytm is not None else None,
        coupon_rate=Decimal(str(coupon)) if coupon is not None else None,
        coupon_frequency=freq,
        maturity_date=maturity
        if isinstance(maturity, date)
        else (date.fromisoformat(maturity) if maturity else None),
        price=Decimal(str(price)) if price is not None else None,
        nominal=Decimal(str(nominal)),
        start_date=start_date,
        is_government=is_government,
        status="active",
        fetched_at=datetime(2026, 1, 1),
    )


class FakeBond:
    """Attribute-only stand-in for compute_spreads (as documented in desk/spreads.py)."""

    def __init__(
        self,
        internal_id: str,
        *,
        currency: str = "USD",
        maturity_date: date,
        yield_to_maturity: float | None = None,
        price: float | None = None,
        coupon_rate: float = 0.0,
        coupon_frequency: int = 1,
        start_date: date | None = None,
        nominal: float | None = None,
    ):
        self.internal_id = internal_id
        self.currency = currency
        self.maturity_date = maturity_date
        self.yield_to_maturity = yield_to_maturity
        self.price = price
        self.coupon_rate = coupon_rate
        self.coupon_frequency = coupon_frequency
        self.start_date = start_date
        self.nominal = nominal


# ══════════════════════════════════════════════════════════════════════════ #
# desk/spreads.py
# ══════════════════════════════════════════════════════════════════════════ #


def test_solve_flat_yield_empty_flows_returns_none():
    assert solve_flat_yield([], 100.0) is None


def test_solve_flat_yield_nonpositive_dirty_price_returns_none():
    assert solve_flat_yield([(1.0, 110.0)], 0.0) is None
    assert solve_flat_yield([(1.0, 110.0)], -5.0) is None


def test_solve_flat_yield_no_root_returns_none():
    # PV at any rate in [0.001, 0.60] is below dirty 150 → no bracket.
    assert solve_flat_yield([(1.0, 110.0)], 150.0) is None


def test_solve_flat_yield_single_flow_recovers_rate():
    # 110/(1+r) = 100 → r = 0.10 exactly.
    r = solve_flat_yield([(1.0, 110.0)], 100.0)
    assert r is not None
    assert abs(r - 0.10) < 1e-6


def test_solve_flat_yield_multi_flow_and_tolerance():
    # 60/(1+r) + 60/(1+r)^2 = 100 → 100x^2 - 60x - 60 = 0, x = 1+r.
    x = (60.0 + math.sqrt(60.0**2 + 4 * 100.0 * 60.0)) / (2 * 100.0)
    r = solve_flat_yield([(1.0, 60.0), (2.0, 60.0)], 100.0)
    assert r is not None
    assert abs(r - (x - 1.0)) < 1e-6
    # Coarse tolerance still lands near the root.
    r_coarse = solve_flat_yield([(1.0, 110.0)], 100.0, tol=1e-3)
    assert r_coarse is not None
    assert abs(r_coarse - 0.10) < 0.01


def test_compute_spreads_one_year_zero_coupon_hand_numbers():
    """1Y zero-coupon vs a flat 10% curve.

    Hand check: flows=[(1.0, 100.0)] (ACT/365, 365 days → t=1.0, not /365.25),
    curve beta0=10 → curve_rate = 10%. model_price = 100/1.10 = 90.9091.
    Market clean 95 + 0 accrued → dirty 95 → flat yield = 100/95 - 1 = 5.2632%.
    z_spread = 5.2632 - 10 = -4.7368; mispricing = (90.9091-95)/95*100 = -4.3062
    → side "rich".
    """
    curve = NelsonSiegelParams(beta0=10.0, beta1=0.0, beta2=0.0, tau=1.5)
    bonds = [
        FakeBond(
            "ZC-1",
            currency="USD",
            maturity_date=date(2027, 1, 1),
            yield_to_maturity=5.2632,
            price=95.0,
            coupon_rate=0.0,
            coupon_frequency=1,
        )
    ]
    reports = compute_spreads(bonds, {"USD": curve}, asof=ASOF)
    assert len(reports) == 1
    r = reports[0]
    assert r.internal_id == "ZC-1"
    assert r.currency == "USD"
    assert abs(r.tenor_years - 0.9993) < 1e-6  # 365/365.25 = 0.99932
    assert r.curve_rate_pct == 10.0
    assert abs(r.market_price - 95.0) < 1e-9
    assert abs(r.model_price - 90.9091) < 1e-3
    assert abs(r.flat_yield_pct - 5.2632) < 1e-3
    assert abs(r.z_spread_pct - (-4.7368)) < 1e-3
    assert abs(r.g_spread_pct - (-4.7368)) < 1e-3  # ytm 5.2632 - curve 10
    assert abs(r.mispricing_pct - (-4.3062)) < 1e-3
    assert r.side == "rich"


def test_compute_spreads_z_and_g_spread_identity():
    # With beta1=beta2=0 the curve rate is exactly beta0=10, so
    # z_spread == flat_yield - curve_rate and g_spread == ytm - curve_rate
    # hold to floating point (both rounded to 4 dp the same way).
    curve = NelsonSiegelParams(beta0=10.0, beta1=0.0, beta2=0.0, tau=1.5)
    bonds = [
        FakeBond(
            "ID-1",
            currency="USD",
            maturity_date=date(2027, 1, 1),
            yield_to_maturity=5.2632,
            price=95.0,
            coupon_rate=0.0,
            coupon_frequency=1,
        )
    ]
    r = compute_spreads(bonds, {"USD": curve}, asof=ASOF)[0]
    assert abs(r.z_spread_pct - (r.flat_yield_pct - 10.0)) < 1e-9
    assert abs(r.g_spread_pct - (r.ytm_pct - 10.0)) < 1e-9
    assert abs(r.z_spread_pct - (-4.7368)) < 1e-9
    assert abs(r.g_spread_pct - (-4.7368)) < 1e-9


def test_compute_spreads_skips_incomplete_bonds():
    curve = NelsonSiegelParams(beta0=10.0, beta1=0.0, beta2=0.0, tau=1.5)
    bonds = [
        FakeBond(
            "OK", currency="USD", maturity_date=date(2027, 1, 1), yield_to_maturity=5.0, price=95.0
        ),
        FakeBond(
            "NO-PRICE",
            currency="USD",
            maturity_date=date(2027, 1, 1),
            yield_to_maturity=5.0,
            price=None,
        ),
        FakeBond(
            "NO-YTM",
            currency="USD",
            maturity_date=date(2027, 1, 1),
            yield_to_maturity=None,
            price=95.0,
        ),
        FakeBond("NO-MAT", currency="USD", maturity_date=None, yield_to_maturity=5.0, price=95.0),
    ]
    reports = compute_spreads(bonds, {"USD": curve}, asof=ASOF)
    assert [r.internal_id for r in reports] == ["OK"]


def test_compute_spreads_skips_unknown_currency_and_matured():
    curve = NelsonSiegelParams(beta0=10.0, beta1=0.0, beta2=0.0, tau=1.5)
    bonds = [
        FakeBond(
            "NO-CURVE",
            currency="RUB",
            maturity_date=date(2027, 1, 1),
            yield_to_maturity=5.0,
            price=95.0,
        ),
        FakeBond("MATURED", currency="USD", maturity_date=ASOF, yield_to_maturity=5.0, price=95.0),
    ]
    assert compute_spreads(bonds, {"USD": curve}, asof=ASOF) == []


def test_compute_spreads_side_labels_cheap_and_fair():
    curve = NelsonSiegelParams(beta0=10.0, beta1=0.0, beta2=0.0, tau=1.5)
    bonds = [
        FakeBond(
            "CHEAP",
            currency="USD",
            maturity_date=date(2027, 1, 1),
            yield_to_maturity=25.0,
            price=80.0,
        ),
        FakeBond(
            "FAIR",
            currency="USD",
            maturity_date=date(2027, 1, 1),
            yield_to_maturity=10.0,
            price=90.9091,
        ),
    ]
    reports = {r.internal_id: r for r in compute_spreads(bonds, {"USD": curve}, asof=ASOF)}
    # model 90.9091 vs dirty 80 → mispricing +13.6364% ≥ +1 → cheap.
    assert reports["CHEAP"].side == "cheap"
    assert abs(reports["CHEAP"].mispricing_pct - 13.6364) < 1e-3
    assert reports["CHEAP"].flat_yield_pct == 25.0
    # dirty ≈ model price → mispricing ≈ 0 → fair.
    assert reports["FAIR"].side == "fair"
    assert abs(reports["FAIR"].mispricing_pct) < 0.01


def test_compute_spreads_sorted_by_abs_mispricing_desc():
    curve = NelsonSiegelParams(beta0=10.0, beta1=0.0, beta2=0.0, tau=1.5)
    bonds = [
        FakeBond(
            "FAIR",
            currency="USD",
            maturity_date=date(2027, 1, 1),
            yield_to_maturity=10.0,
            price=90.9091,
        ),
        FakeBond(
            "RICH",
            currency="USD",
            maturity_date=date(2027, 1, 1),
            yield_to_maturity=5.2632,
            price=95.0,
        ),
        FakeBond(
            "CHEAP",
            currency="USD",
            maturity_date=date(2027, 1, 1),
            yield_to_maturity=25.0,
            price=80.0,
        ),
    ]
    reports = compute_spreads(bonds, {"USD": curve}, asof=ASOF)
    assert [r.internal_id for r in reports] == ["CHEAP", "RICH", "FAIR"]
    abs_m = [abs(r.mispricing_pct or 0.0) for r in reports]
    assert abs_m == sorted(abs_m, reverse=True)


def test_compute_spreads_dirty_price_includes_accrued():
    # Semiannual 10% coupon, asof 3 months after issue (2026-01-01 → 2026-04-01).
    # ACT/365: elapsed 90/365, period 181/365 → accrued = 5.0 * 90/181 = 2.48619.
    curve = NelsonSiegelParams(beta0=10.0, beta1=0.0, beta2=0.0, tau=1.5)
    bonds = [
        FakeBond(
            "ACC-1",
            currency="USD",
            maturity_date=date(2031, 1, 1),
            yield_to_maturity=10.0,
            price=100.0,
            coupon_rate=10.0,
            coupon_frequency=2,
            start_date=date(2026, 1, 1),
        )
    ]
    r = compute_spreads(bonds, {"USD": curve}, asof=date(2026, 4, 1))[0]
    assert abs(r.market_price - 102.4862) < 1e-3  # 100 + 2.48619


# ══════════════════════════════════════════════════════════════════════════ #
# desk/yield_curve.py
# ══════════════════════════════════════════════════════════════════════════ #


def test_ns_rate_at_zero_is_beta0_plus_beta1():
    assert _ns_rate(0.0, 10.0, 2.0, -3.0, 2.0) == 12.0
    assert _ns_rate(-5.0, 10.0, 2.0, -3.0, 2.0) == 12.0


def test_ns_rate_matches_exact_formula():
    # t=2, tau=2 → x=1: factor1 = 1-e^-1, factor2 = factor1 - e^-1.
    x = 1.0
    factor1 = (1 - math.exp(-x)) / x
    factor2 = factor1 - math.exp(-x)
    expected = 10.0 + 2.0 * factor1 + (-3.0) * factor2
    assert abs(_ns_rate(2.0, 10.0, 2.0, -3.0, 2.0) - expected) < 1e-9


def test_ns_rate_asymptotic_beta0():
    # As t → ∞ both factors vanish → rate → beta0.
    assert abs(_ns_rate(1e6, 10.0, 2.0, -3.0, 2.0) - 10.0) < 1e-4
    assert abs(_ns_rate(1000.0, 10.0, 2.0, -3.0, 2.0) - 10.0) < 0.01


def test_ns_rate_negative_and_extreme_tenors_no_crash():
    assert _ns_rate(-1.0, 5.0, 1.0, 1.0, 1.5) == 6.0
    # factor1 ≈ 1/x → beta1+beta2 = 2 over 1e9 tenors: 5.000000003.
    assert abs(_ns_rate(1e9, 5.0, 1.0, 1.0, 1.5) - 5.0) < 1e-8


def test_interpolate_known_tenor_and_unknown_raises():
    params = NelsonSiegelParams(beta0=10.0, beta1=2.0, beta2=-3.0, tau=2.0)
    curve = YieldCurve(currency="USD", observed_at=datetime(2026, 1, 1), points=[])
    assert interpolate(curve, params, "1Y") == _ns_rate(1.0, 10.0, 2.0, -3.0, 2.0)
    assert interpolate(curve, params, "30Y") == _ns_rate(30.0, 10.0, 2.0, -3.0, 2.0)
    with pytest.raises(ValueError):
        interpolate(curve, params, "1Q")


def test_fit_nelson_siegel_empty_and_sparse():
    empty = fit_nelson_siegel([])
    assert (empty.beta0, empty.beta1, empty.beta2, empty.tau) == (0.0, 0.0, 0.0, 1.5)
    one = fit_nelson_siegel([CurvePoint(tenor="1Y", years=1.0, rate_pct=7.0)])
    assert (one.beta0, one.beta1, one.beta2) == (7.0, 0.0, 0.0)
    two = fit_nelson_siegel(
        [
            CurvePoint(tenor="1Y", years=1.0, rate_pct=5.0),
            CurvePoint(tenor="10Y", years=10.0, rate_pct=7.0),
        ]
    )
    assert (two.beta0, two.beta1, two.beta2) == (6.0, 0.0, 0.0)


def test_fit_nelson_siegel_reproduces_rates():
    true = NelsonSiegelParams(beta0=5.0, beta1=-1.5, beta2=1.0, tau=2.5)
    tenors = {"1Y": 1.0, "2Y": 2.0, "3Y": 3.0, "5Y": 5.0, "7Y": 7.0, "10Y": 10.0}
    points = [
        CurvePoint(tenor=t, years=y, rate_pct=_ns_rate(y, **true.model_dump()))
        for t, y in tenors.items()
    ]
    fitted = fit_nelson_siegel(points)
    for y in tenors.values():
        assert (
            abs(
                _ns_rate(y, fitted.beta0, fitted.beta1, fitted.beta2, fitted.tau)
                - _ns_rate(y, **true.model_dump())
            )
            < 1e-2
        )


def test_curve_from_bonds_buckets_and_averages():
    # 2055 maturities → ~28.4y → nearest bucket 30Y (stable for years to come;
    # the module computes tenors off datetime.now(), so we cannot pin the date).
    bonds = [
        _bond(internal_id="A", ytm=6.0, maturity="2055-01-01"),
        _bond(internal_id="B", ytm=8.0, maturity="2055-07-01"),  # same bucket → averaged
    ]
    curve = curve_from_bonds(bonds)
    assert curve.currency == "USD"
    assert len(curve.points) == 1
    p = curve.points[0]
    assert p.tenor == "30Y"
    assert p.rate_pct == 7.0  # mean of 6 and 8
    assert p.years == 30.0


def test_curve_from_bonds_skips_missing_and_matured():
    bonds = [
        _bond(internal_id="OK", ytm=6.0, maturity="2055-01-01"),
        _bond(internal_id="NO-YTM", ytm=None, maturity="2055-01-01"),
        _bond(internal_id="PAST", ytm=6.0, maturity="2020-01-01"),
        _bond(internal_id="NO-MAT", ytm=6.0, maturity=None),
    ]
    curve = curve_from_bonds(bonds)
    assert len(curve.points) == 1
    assert curve.points[0].rate_pct == 6.0


def test_curve_from_bonds_excludes_distribution_and_anomalies():
    """Eligibility gate: дистрибуция (цена 55%, YTM 57.6%) не должна
    поднимать бакет кривой (как 1545% поднимал «короткий» бакет до 130%)."""
    bonds = [
        _bond(internal_id="A", ytm=12.0, maturity="2055-01-01"),
        _bond(internal_id="B", ytm=14.0, maturity="2055-07-01"),
        _bond(internal_id="DIST", ytm=57.6, maturity="2055-06-01", price=55.0),
        _bond(internal_id="EXT", ytm=800.0, maturity="2055-06-01", price=50.0),
    ]
    curve = curve_from_bonds(bonds)
    assert len(curve.points) == 1
    assert curve.points[0].rate_pct == 13.0  # median of 12 и 14


def test_curve_from_bonds_uses_median_not_mean():
    """Медиана устойчива к одиночному высокому значению внутри бакета."""
    bonds = [
        _bond(internal_id="A", ytm=10.0, maturity="2055-01-01"),
        _bond(internal_id="B", ytm=12.0, maturity="2055-06-01"),
        _bond(internal_id="C", ytm=40.0, maturity="2055-03-01", price=100.0),
    ]
    curve = curve_from_bonds(bonds)
    assert curve.points[0].rate_pct == 12.0  # не среднее (20.67)


def test_curve_slope_and_curvature():
    curve = YieldCurve(
        currency="USD",
        observed_at=datetime(2026, 1, 1),
        points=[
            CurvePoint(tenor="1Y", years=1.0, rate_pct=5.0),
            CurvePoint(tenor="10Y", years=10.0, rate_pct=7.0),
        ],
    )
    assert curve_slope(curve) == 2.0
    assert (
        curve_curvature(curve, NelsonSiegelParams(beta0=5.0, beta1=-1.0, beta2=-3.0, tau=2.0))
        == -3.0
    )


# ══════════════════════════════════════════════════════════════════════════ #
# desk/relative_value.py
# ══════════════════════════════════════════════════════════════════════════ #


def test_rv_z_score_sign_and_sides():
    # YTMs 8, 12, 4, 8.5 → mean 8.125, pstdev 2.8367.
    # B (12): z = +1.3660 ≥ 1 → buy (cheap). C (4): z = -1.4542 ≤ -1 → sell (rich).
    bonds = [
        _bond(internal_id="A", ytm=8.0, maturity="2030-01-01"),
        _bond(internal_id="B", ytm=12.0, maturity="2030-01-01"),
        _bond(internal_id="C", ytm=4.0, maturity="2030-01-01"),
        _bond(internal_id="D", ytm=8.5, maturity="2030-01-01"),
    ]
    signals = relative_value_signals(bonds, asof=ASOF)
    by_id = {s.internal_id: s for s in signals}
    assert by_id["B"].z_score > 0
    assert by_id["B"].side == "buy"
    assert abs(by_id["B"].z_score - 1.3660) < 0.01
    assert by_id["C"].z_score < 0
    assert by_id["C"].side == "sell"
    assert abs(by_id["C"].z_score - (-1.4542)) < 0.01
    assert abs(by_id["D"].z_score) < 1.0  # near the mean → hold
    assert by_id["D"].side == "hold"


def test_rv_three_bond_deterministic_sides():
    bonds = [
        _bond(internal_id="A", ytm=8.0, maturity="2030-01-01"),
        _bond(internal_id="B", ytm=9.0, maturity="2030-01-01"),
        _bond(internal_id="C", ytm=10.0, maturity="2030-01-01"),
    ]
    signals = relative_value_signals(bonds, asof=ASOF)
    by_id = {s.internal_id: s for s in signals}
    assert by_id["A"].side == "sell"  # low yield → rich
    assert by_id["B"].side == "hold"
    assert by_id["C"].side == "buy"  # high yield → cheap


def test_rv_requires_three_peers():
    two = [_bond(internal_id="A", ytm=8.0), _bond(internal_id="B", ytm=9.0)]
    assert relative_value_signals(two, asof=ASOF) == []


def test_rv_grouped_by_currency_requires_three():
    # 2 USD + 1 EUR → neither group has 3 peers → no signals.
    bonds = [
        _bond(internal_id="A", ytm=8.0, currency="USD"),
        _bond(internal_id="B", ytm=9.0, currency="USD"),
        _bond(internal_id="C", ytm=8.0, currency="EUR"),
    ]
    assert relative_value_signals(bonds, asof=ASOF) == []


def test_rv_peer_set_and_fair_spread():
    bonds = [
        _bond(internal_id="A", ytm=8.0),
        _bond(internal_id="B", ytm=12.0),
        _bond(internal_id="C", ytm=4.0),
        _bond(internal_id="D", ytm=8.5),
    ]
    by_id = {s.internal_id: s for s in relative_value_signals(bonds, asof=ASOF)}
    assert by_id["B"].peer_set == ["A", "C", "D"]  # peers exclude the bond itself
    assert by_id["B"].fair_spread_pct == 8.125  # group mean
    assert by_id["B"].spread_pct == 3.875  # 12 - 8.125
    assert by_id["B"].peer_currency == "USD"


def test_rv_sorted_by_abs_z_desc():
    bonds = [
        _bond(internal_id="A", ytm=8.0),
        _bond(internal_id="B", ytm=12.0),
        _bond(internal_id="C", ytm=4.0),
        _bond(internal_id="D", ytm=8.5),
    ]
    signals = relative_value_signals(bonds, asof=ASOF)
    assert signals[0].internal_id == "C"  # |z| 1.4542 > 1.3660
    zs = [abs(s.z_score) for s in signals]
    assert zs == sorted(zs, reverse=True)


def test_rv_excludes_distribution_and_extreme_bonds():
    """Eligibility gate: дистрибуция (цена 55%, YTM 57.6%) и сверхвысокий
    риск (YTM 800%) не должны выдавать «Недооценена (BUY)» с Z=+8."""
    bonds = [
        _bond(internal_id="A", ytm=8.0),
        _bond(internal_id="B", ytm=12.0),
        _bond(internal_id="C", ytm=4.0),
        _bond(internal_id="D", ytm=8.5),
        _bond(internal_id="DIST", ytm=57.6, price=55.0),
        _bond(internal_id="EXT", ytm=800.0, price=50.0),
    ]
    ids = {s.internal_id for s in relative_value_signals(bonds, asof=ASOF)}
    assert "DIST" not in ids
    assert "EXT" not in ids
    assert {"A", "B", "C", "D"} <= ids


def test_rv_excludes_ytm_anomaly_bond():
    """Обычная бумага (цена 99%) с YTM 57.6% при аналогах 4-15% — аномалия:
    не должна ломать z-score всего бакета."""
    bonds = [
        _bond(internal_id=f"P{i}", ytm=y) for i, y in enumerate([4.0, 6.0, 8.0, 10.0, 12.0, 15.0])
    ]
    bonds.append(_bond(internal_id="ANOM", ytm=57.6, price=99.0))
    ids = {s.internal_id for s in relative_value_signals(bonds, asof=ASOF)}
    assert "ANOM" not in ids
    # Остальные сравниваются между собой, без раздутого «справедливого уровня».
    by_id = {s.internal_id: s for s in relative_value_signals(bonds, asof=ASOF)}
    assert abs(by_id["P0"].fair_spread_pct - 9.1666) < 0.01  # среднее 4..15


def test_signals_from_curve_consistency():
    params = NelsonSiegelParams(beta0=5.0, beta1=-1.0, beta2=0.5, tau=2.5)
    curve = YieldCurve(
        currency="USD",
        observed_at=datetime(2026, 1, 1),
        points=[
            CurvePoint(tenor=t, years=y, rate_pct=_ns_rate(y, **params.model_dump()))
            for t, y in (("1Y", 1.0), ("3Y", 3.0), ("5Y", 5.0), ("10Y", 10.0))
        ],
    )
    signals = signals_from_curve(curve, asof=ASOF)
    assert len(signals) == 4
    rates = [p.rate_pct for p in curve.points]
    avg = sum(rates) / len(rates)
    sd = (sum((r - avg) ** 2 for r in rates) / len(rates)) ** 0.5
    for s, p in zip(signals, curve.points, strict=True):
        z = (p.rate_pct - avg) / sd
        assert s.z_score == round(z, 4)
        expected_side = "buy" if z >= 1 else ("sell" if z <= -1 else "hold")
        assert s.side == expected_side
        assert s.fair_spread_pct == round(avg, 4)


def test_signals_from_curve_sparse_returns_empty():
    curve = YieldCurve(
        currency="USD",
        observed_at=datetime(2026, 1, 1),
        points=[CurvePoint(tenor="1Y", years=1.0, rate_pct=5.0)],
    )
    assert signals_from_curve(curve, asof=ASOF) == []


# ══════════════════════════════════════════════════════════════════════════ #
# desk/repo.py
# ══════════════════════════════════════════════════════════════════════════ #


def test_repo_deal_haircut_math():
    deal = repo_deal(
        _bond(internal_id="REPO-1"),
        notional=Decimal("1000"),
        haircut_pct=5.0,
        repo_rate_pct=10.0,
        tenor_days=30,
        asof=ASOF,
    )
    assert deal.internal_id == "REPO-1"
    assert deal.asof_date == ASOF
    # cash_lent = notional * (1 - 5%) = 950.00; collateral booked at notional.
    assert deal.cash_lent == Decimal("950.00")
    assert deal.collateral_value == Decimal("1000.00")
    # accrued = 950 * 10/100 * 30/365 = 2850/365 = 7.80822 → 7.81.
    assert deal.accrued_interest == Decimal("7.81")


def test_repo_deal_haircut_clamped_to_zero():
    for bad in (150.0, -10.0):
        deal = repo_deal(
            _bond(internal_id=f"CLAMP-{bad}"),
            notional=Decimal("1000"),
            haircut_pct=bad,
            repo_rate_pct=10.0,
            tenor_days=30,
            asof=ASOF,
        )
        assert deal.haircut_pct == 0.0
        assert deal.cash_lent == Decimal("1000.00")


def test_repo_deal_repo_rate_zero_no_interest():
    deal = repo_deal(
        _bond(internal_id="R0"),
        notional=Decimal("1000"),
        haircut_pct=5.0,
        repo_rate_pct=0.0,
        tenor_days=30,
        asof=ASOF,
    )
    assert deal.accrued_interest == Decimal("0.00")
    assert deal.cash_lent == Decimal("950.00")


def test_haircut_by_issuer_tiers():
    assert haircut_by_issuer("Министерство финансов") == 1.0
    assert haircut_by_issuer("Республика Беларусь") == 1.0
    assert haircut_by_issuer("Government of Canada") == 1.0
    assert haircut_by_issuer("State Treasury") == 1.0
    assert haircut_by_issuer("Some Bank") == 3.0
    assert haircut_by_issuer("Сбербанк") == 3.0
    assert haircut_by_issuer("Gazprom") == 5.0
    assert haircut_by_issuer(None) == 5.0


# ══════════════════════════════════════════════════════════════════════════ #
# desk/carry.py
# ══════════════════════════════════════════════════════════════════════════ #


def test_carry_hand_numbers_with_curve():
    """1Y 10% annual bond, ytm 10, funding 6, horizon 30d, flat 8% curve.

    Hand check: carry = (10-6)*30/365.25 = 0.328542%. With a flat beta0=8
    curve ytm_next = 8 → rolldown_bps = (10-8)*100 = 200.
    mod_dur = 1/(1+0.10) = 0.9091 (single flow at t=1).
    rolldown P&L = 0.9091 * (10-8) = 1.8182 → expected = 2.1467.
    breakeven = carry / mod_dur * 100 = 36.14 bps.
    """
    bond = _bond(internal_id="CARRY-1", ytm=10.0, coupon=10.0, freq=1, maturity="2027-01-01")
    curve = NelsonSiegelParams(beta0=8.0, beta1=0.0, beta2=0.0, tau=1.5)
    ct = carry_for_bond(bond, funding_rate_pct=6.0, horizon_days=30, curve_params=curve, asof=ASOF)
    assert ct is not None
    assert ct.rolldown_bps == 200.0
    assert abs(ct.expected_pnl_pct - 2.1467) < 1e-3
    assert abs(ct.breakeven_bps - 36.14) < 0.01
    assert ct.horizon_days == 30
    assert ct.notional == Decimal("1000")


def test_carry_no_curve_rolldown_zero():
    bond = _bond(internal_id="CARRY-2", ytm=10.0, coupon=10.0, freq=1, maturity="2027-01-01")
    ct = carry_for_bond(bond, funding_rate_pct=6.0, horizon_days=30, asof=ASOF)
    assert ct is not None
    assert ct.rolldown_bps == 0.0
    # carry only: (10-6)*30/365.25 = 0.328542 → 0.3285.
    assert abs(ct.expected_pnl_pct - 0.3285) < 1e-4
    assert abs(ct.breakeven_bps - 36.14) < 0.01


def test_carry_negative_when_funding_above_coupon():
    bond = _bond(internal_id="CARRY-3", ytm=10.0, coupon=6.0, freq=1, maturity="2027-01-01")
    ct = carry_for_bond(bond, funding_rate_pct=10.0, horizon_days=30, asof=ASOF)
    assert ct is not None
    assert ct.expected_pnl_pct < 0
    assert abs(ct.expected_pnl_pct - (-0.3285)) < 1e-4
    assert ct.breakeven_bps < 0  # negative carry → negative cushion


def test_carry_zero_horizon():
    bond = _bond(internal_id="CARRY-4", ytm=10.0, coupon=10.0, freq=1, maturity="2027-01-01")
    ct = carry_for_bond(bond, funding_rate_pct=6.0, horizon_days=0, asof=ASOF)
    assert ct is not None
    assert ct.expected_pnl_pct == 0.0
    assert ct.breakeven_bps == 0.0
    assert ct.rolldown_bps == 0.0


def test_carry_returns_none_missing_inputs():
    assert (
        carry_for_bond(
            _bond(internal_id="X", ytm=None, coupon=8.0), funding_rate_pct=5.0, asof=ASOF
        )
        is None
    )
    assert (
        carry_for_bond(
            _bond(internal_id="Y", ytm=8.0, coupon=None), funding_rate_pct=5.0, asof=ASOF
        )
        is None
    )
    assert (
        carry_for_bond(
            _bond(internal_id="Z", ytm=8.0, coupon=8.0, maturity=None),
            funding_rate_pct=5.0,
            asof=ASOF,
        )
        is None
    )


# ══════════════════════════════════════════════════════════════════════════ #
# desk/stress.py
# ══════════════════════════════════════════════════════════════════════════ #


def _zero_coupon(
    internal_id: str, *, maturity: str, ytm: float, price: float = 100.0, freq: int = 1, **kw
) -> Bond:
    return _bond(
        internal_id=internal_id,
        ytm=ytm,
        coupon=0.0,
        freq=freq,
        maturity=maturity,
        price=price,
        **kw,
    )


def test_run_stress_parallel_up_hand_numbers():
    """1Y zero-coupon, ytm 10 → mod duration = 1/1.1 = 0.9091.

    parallel_+100bp: shock 1% → price_change = -0.9091*0.01
    + 0.5*0.9091^2*0.0001 = -0.0090497. new price = 99.0950 → P&L = -9.05
    per 1000 face → pnl_pct = -0.905.
    """
    bond = _zero_coupon("S1", maturity="2027-01-01", ytm=10.0)
    res = run_stress(PRESET_SCENARIOS["parallel_+100bp"], [(bond, Decimal("1000"))], asof=ASOF)
    assert res.by_position["S1"] == Decimal("-9.05")
    assert abs(res.pnl_pct - (-0.905)) < 0.01
    assert res.pnl == Decimal("-9.05")
    assert res.portfolio_value == Decimal("1000.00")


def test_run_stress_duration5_100bp_about_minus_5pct():
    # 5Y zero-coupon at ytm 0 → modified duration ≈ 5.0027. A +100bp shock
    # costs ≈ -5% linearly; convexity correction adds +0.125% of the square.
    bond = _zero_coupon("S5", maturity="2031-01-01", ytm=0.0)
    res = run_stress(PRESET_SCENARIOS["parallel_+100bp"], [(bond, Decimal("1000"))], asof=ASOF)
    assert -5.1 < res.pnl_pct < -4.7
    # exact per formula: -5.0027*0.01 + 0.5*5.0027^2*1e-4 = -0.048776 → -4.878%.
    assert abs(res.pnl_pct - (-4.878)) < 0.01


def test_run_stress_fx_shock_hand_numbers():
    # No rate shock; BYN bond vs USD base: fx_impact = 1 - 20% = 0.8.
    # cur_value = amount * new_price/100 * 0.8 = 1000*1.0*0.8 = 800 → P&L -200.
    usd = _zero_coupon("USD-1", maturity="2030-01-01", ytm=8.0, currency="USD")
    byn = _zero_coupon("BYN-1", maturity="2030-01-01", ytm=8.0, currency="BYN")
    res = run_stress(
        PRESET_SCENARIOS["fx_shock_-20%"],
        [(usd, Decimal("1000")), (byn, Decimal("1000"))],
        asof=ASOF,
    )
    assert res.by_position["USD-1"] == Decimal("0.00")
    assert res.by_position["BYN-1"] == Decimal("-200.00")
    assert res.pnl == Decimal("-200.00")
    # pnl -200 over a 2000 portfolio (both bonds) → -10.0%.
    assert res.pnl_pct == -10.0


def test_run_stress_by_tenor_buckets():
    bonds = [
        _zero_coupon("T1", maturity="2026-07-01", ytm=8.0),  # 0.5y → 1Y
        _zero_coupon("T2", maturity="2028-01-01", ytm=8.0),  # 2y → 5Y
        _zero_coupon("T3", maturity="2033-01-01", ytm=8.0),  # 7y → 10Y
        _zero_coupon("T4", maturity="2046-01-01", ytm=8.0),  # 20y → 30Y
    ]
    scn = StressScenario(kind="parallel", name="none", description="no shocks")
    res = run_stress(scn, [(b, Decimal("1000")) for b in bonds], asof=ASOF)
    assert set(res.by_tenor) == {"1Y", "5Y", "10Y", "30Y"}
    assert all(v == Decimal("0.00") for v in res.by_tenor.values())


def test_run_stress_credit_shock_skips_government():
    gov = _zero_coupon("GOV", maturity="2030-01-01", ytm=8.0, is_government=True)
    corp = _zero_coupon("CORP", maturity="2030-01-01", ytm=8.0, is_government=False)
    res = run_stress(
        PRESET_SCENARIOS["credit_shock_+150bp"],
        [(gov, Decimal("1000")), (corp, Decimal("1000"))],
        asof=ASOF,
    )
    assert res.by_position["GOV"] == Decimal("0.00")  # sovereign is risk-free
    assert res.by_position["CORP"] < res.by_position["GOV"]


def test_run_stress_missing_duration_fallback():
    # ytm=-250% makes (1+ytm/freq) ≤ 0 → duration_report raises (math domain
    # error on fractional-period pow) → run_stress falls back to
    # duration = years*0.75 = (379/365.25)*0.75 = 0.778234.
    # price_change = -0.778234*0.01 + 0.5*0.778234^2*1e-4 = -0.0077521
    # → new price 99.2248 → P&L = -7.75 per 1000 face.
    bond = _zero_coupon("FB", maturity="2027-01-15", ytm=-250.0, freq=2)
    res = run_stress(PRESET_SCENARIOS["parallel_+100bp"], [(bond, Decimal("1000"))], asof=ASOF)
    assert res.by_position["FB"] == Decimal("-7.75")
    assert abs(res.pnl_pct - (-0.775)) < 0.01


def test_run_stress_zero_amounts():
    bond = _zero_coupon("ZA", maturity="2030-01-01", ytm=8.0)
    res = run_stress(PRESET_SCENARIOS["parallel_+100bp"], [(bond, Decimal("0"))], asof=ASOF)
    assert res.by_position["ZA"] == Decimal("0.00")
    assert res.pnl == Decimal("0.00")
    assert res.pnl_pct == 0.0


def test_run_stress_value_convention_amount_treated_as_face():
    # cur_value = amount * new_price/100: amount is face value, price is
    # % of face. With no shock new_price == base_price → portfolio_value
    # must equal amount * price/100 = 1000*95/100 = 950.
    bond = _zero_coupon("CV", maturity="2030-01-01", ytm=8.0, price=95.0)
    scn = StressScenario(kind="parallel", name="none", description="no shocks")
    res = run_stress(scn, [(bond, Decimal("1000"))], asof=ASOF)
    assert res.portfolio_value == Decimal("950.00")
    assert res.stressed_value == Decimal("950.00")
    assert res.by_position["CV"] == Decimal("0.00")


def test_run_stress_skips_missing_maturity_and_ytm():
    bonds = [
        (_bond(internal_id="NM", ytm=8.0, maturity=None), Decimal("1000")),
        (_bond(internal_id="NY", ytm=None, maturity="2030-01-01"), Decimal("1000")),
    ]
    res = run_stress(PRESET_SCENARIOS["parallel_+100bp"], bonds, asof=ASOF)
    assert res.by_position == {}
    assert res.portfolio_value == Decimal("0.00")
    assert res.pnl_pct == 0.0


def test_preset_scenarios_cover_all_kinds_and_run():
    bond = _zero_coupon("PS", maturity="2030-01-01", ytm=8.0)
    kinds = set()
    for _name, scn in PRESET_SCENARIOS.items():
        res = run_stress(scn, [(bond, Decimal("1000"))], asof=ASOF)
        assert isinstance(res.pnl, Decimal)
        kinds.add(scn.kind)
        assert scn.name and scn.description
    assert kinds == {"parallel", "steepener", "flattener", "inversion", "credit_shock", "fx_shock"}


# ══════════════════════════════════════════════════════════════════════════ #
# desk/duration.py
# ══════════════════════════════════════════════════════════════════════════ #


def test_par_bond_duration_below_maturity():
    bond = _bond(internal_id="PAR", ytm=10.0, coupon=10.0, freq=2, maturity="2036-01-01")
    rep = duration_report(bond, asof=ASOF)
    assert 0 < rep.macaulay_duration < 10.0  # coupons pull duration below maturity
    assert 0 < rep.modified_duration < rep.macaulay_duration
    assert abs(rep.modified_duration - rep.macaulay_duration / 1.05) < 1e-4
    assert rep.convexity > 0
    assert rep.dv01 > 0


def test_zero_coupon_duration_equals_ttm():
    bond = _zero_coupon("ZC", maturity="2027-01-01", ytm=10.0)
    rep = duration_report(bond, asof=ASOF)
    assert abs(rep.macaulay_duration - 1.0) < 1e-6  # single flow at t=1.0
    assert abs(rep.modified_duration - 0.9091) < 1e-3  # 1/(1+0.10)
    # DV01: p_now - p_up = 1000/1.1 - 1000/1.1001 = 0.0826 per 1000 face.
    assert abs(rep.dv01 - 0.0826) < 1e-3


def test_dv01_equals_price_difference():
    flows = pricing_cashflows(
        nominal=1000.0,
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        maturity=date(2036, 1, 1),
        asof=ASOF,
        issue_date=date(2024, 1, 1),
    )
    p_now = _price_from_yield(flows, 10.0, freq=2)
    p_up = _price_from_yield(flows, 10.01, freq=2)  # +1bp
    d = dv01(
        nominal=Decimal("1000"),
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        ytm_pct=10.0,
        maturity=date(2036, 1, 1),
        ref=ASOF,
        issue_date=date(2024, 1, 1),
    )
    assert abs(d - (p_now - p_up)) < 1e-9
    assert d > 0


def test_convexity_positive_for_zero_coupon():
    cvx = convexity(
        nominal=Decimal("1000"),
        coupon_rate_pct=0.0,
        coupon_frequency=1,
        ytm_pct=10.0,
        maturity=date(2027, 1, 1),
        ref=ASOF,
    )
    assert cvx > 0


def test_maturity_today_duration_zero():
    bond = _zero_coupon("MT", maturity="2026-01-01", ytm=8.0)
    rep = duration_report(bond, asof=ASOF)
    assert rep.modified_duration == 0.0
    assert rep.macaulay_duration == 0.0
    assert rep.convexity == 0.0
    assert rep.dv01 == 0.0


def test_negative_ytm_within_floor_works():
    # ytm -5% keeps (1 + ytm/100/freq) = 0.975 > 0 → duration is computable
    # and stays positive (negative yields raise prices, so Macaulay shrinks).
    bond = _bond(internal_id="NY", ytm=-5.0, coupon=5.0, freq=2, maturity="2036-01-01")
    rep = duration_report(bond, asof=ASOF)
    assert rep.modified_duration > 0
    assert math.isfinite(rep.modified_duration)


def test_extreme_negative_ytm_raises():
    # Documented quirk: ytm ≤ -100% makes (1+ytm/100/freq) ≤ 0; float ** with a
    # fractional exponent then returns a complex number, so duration_report's
    # `price <= 0` guard in macaulay_duration raises TypeError. No guard for
    # this exists in duration_report itself (run_stress catches it and falls
    # back to the tenor-based estimate).
    bond = _zero_coupon("XY", maturity="2027-01-15", ytm=-250.0)
    with pytest.raises((TypeError, ValueError)):
        duration_report(bond, asof=ASOF)


def test_duration_report_none_and_no_maturity():
    empty = duration_report(None, asof=ASOF)
    assert (empty.modified_duration, empty.macaulay_duration, empty.convexity, empty.dv01) == (
        0.0,
        0.0,
        0.0,
        0.0,
    )
    nomat = duration_report(_bond(internal_id="N", maturity=None), asof=ASOF)
    assert nomat.modified_duration == 0.0


def test_key_rate_duration_keys():
    bond = _bond(internal_id="KR", ytm=10.0, coupon=10.0, freq=2, maturity="2036-01-01")
    rep = duration_report(bond, asof=ASOF)
    assert set(rep.key_rate_durations) == {"3M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"}


def test_low_level_duration_functions_agree():
    mac = macaulay_duration(
        nominal=Decimal("1000"),
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        ytm_pct=10.0,
        maturity=date(2036, 1, 1),
        ref=ASOF,
    )
    mod = modified_duration(
        nominal=Decimal("1000"),
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        ytm_pct=10.0,
        maturity=date(2036, 1, 1),
        ref=ASOF,
    )
    assert abs(mod - mac / 1.05) < 1e-9


# ══════════════════════════════════════════════════════════════════════════ #
# desk/cashflow.py
# ══════════════════════════════════════════════════════════════════════════ #


def test_pricing_cashflows_frequency_flow_counts():
    for freq, expected in ((1, 10), (2, 20), (4, 40)):
        flows = pricing_cashflows(
            nominal=100.0,
            coupon_rate_pct=10.0,
            coupon_frequency=freq,
            maturity=date(2034, 1, 1),
            asof=date(2024, 1, 1),
            issue_date=date(2024, 1, 1),
        )
        assert len(flows) == expected, f"freq={freq}"


def test_pricing_cashflows_coupon_amounts():
    flows = pricing_cashflows(
        nominal=100.0,
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        maturity=date(2034, 1, 1),
        asof=date(2024, 1, 1),
        issue_date=date(2024, 1, 1),
    )
    assert all(abs(amt - 5.0) < 1e-9 for t, amt in flows[:-1])
    assert abs(flows[-1][1] - 105.0) < 1e-9  # final coupon + redemption


def test_pricing_cashflows_zero_coupon_single_redemption_flow():
    # ACT/365 → t in years = days/365 (NOT /365.25 as in tenor math).
    flows = pricing_cashflows(
        nominal=100.0,
        coupon_rate_pct=0.0,
        coupon_frequency=1,
        maturity=date(2028, 1, 1),
        asof=date(2026, 1, 1),
        issue_date=date(2026, 1, 1),
    )
    assert [(round(t, 9), round(a, 9)) for t, a in flows] == [(1.0, 0.0), (2.0, 100.0)]


def test_pricing_cashflows_after_maturity_no_flows():
    assert (
        pricing_cashflows(
            nominal=100.0,
            coupon_rate_pct=10.0,
            coupon_frequency=2,
            maturity=date(2034, 1, 1),
            asof=date(2034, 1, 1),
            issue_date=date(2024, 1, 1),
        )
        == []
    )
    assert (
        pricing_cashflows(
            nominal=100.0,
            coupon_rate_pct=10.0,
            coupon_frequency=2,
            maturity=date(2034, 1, 1),
            asof=date(2035, 1, 1),
            issue_date=date(2024, 1, 1),
        )
        == []
    )


def test_pricing_cashflows_fallback_without_issue_date():
    # Month-spaced coupons backward from maturity: 2026-07-01 (181/365 y) and
    # 2027-01-01 (1.0 y).
    flows = pricing_cashflows(
        nominal=100.0,
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        maturity=date(2027, 1, 1),
        asof=date(2026, 1, 1),
    )
    assert len(flows) == 2
    assert abs(flows[0][0] - 181 / 365) < 1e-9
    assert abs(flows[0][1] - 5.0) < 1e-9
    assert abs(flows[1][0] - 1.0) < 1e-9
    assert abs(flows[1][1] - 105.0) < 1e-9


def test_year_fraction_act365_one_year():
    # One-year cashflow time convention: 365/365 = 1.0 (the /365.25 constant
    # is only used for tenor bucketing elsewhere).
    assert year_fraction(date(2026, 1, 1), date(2027, 1, 1), "ACT/365") == 1.0


def test_accrued_interest_at_coupon_date_zero():
    # Ex-coupon convention: exactly on a coupon date the previous coupon was
    # just paid → 0.0 accrued.
    ai = accrued_interest(
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        issue_date=date(2026, 1, 1),
        maturity_date=date(2030, 1, 1),
        asof=date(2026, 7, 1),
        face=100.0,
    )
    assert ai == 0.0


def test_accrued_interest_half_period_act365():
    # Semiannual 10%: coupon per period = 100*10%/2 = 5.00. Half a period
    # (2026-01-01 → 2026-04-01 is 90 of 181 days) → 5.00*90/181 = 2.486.
    ai = accrued_interest(
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        issue_date=date(2026, 1, 1),
        maturity_date=date(2030, 1, 1),
        asof=date(2026, 4, 1),
        convention="ACT/365",
        face=100.0,
    )
    assert abs(ai - 5.0 * 90 / 181) < 1e-9
    assert abs(ai - 2.5) < 0.02  # ≈ half the 5.00 per-period coupon


def test_accrued_interest_30_360_exact_half():
    ai = accrued_interest(
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        issue_date=date(2026, 1, 1),
        maturity_date=date(2030, 1, 1),
        asof=date(2026, 4, 1),
        convention="30/360",
        face=100.0,
    )
    assert abs(ai - 2.5) < 1e-9


def test_accrued_interest_guards():
    kw = {"coupon_frequency": 2, "maturity_date": date(2030, 1, 1), "face": 100.0}
    assert (
        accrued_interest(coupon_rate_pct=10.0, **kw, issue_date=None, asof=date(2026, 4, 1)) == 0.0
    )
    assert (
        accrued_interest(
            coupon_rate_pct=10.0, **kw, issue_date=date(2026, 1, 1), asof=date(2025, 12, 1)
        )
        == 0.0
    )  # before issue
    assert (
        accrued_interest(
            coupon_rate_pct=0.0, **kw, issue_date=date(2026, 1, 1), asof=date(2026, 4, 1)
        )
        == 0.0
    )
    assert (
        accrued_interest(
            coupon_rate_pct=10.0, **kw, issue_date=date(2026, 1, 1), asof=date(2031, 1, 1)
        )
        == 0.0
    )  # past maturity


# ══════════════════════════════════════════════════════════════════════════ #
# desk/ytm.py
# ══════════════════════════════════════════════════════════════════════════ #


def test_ytm_par_bond_equals_coupon():
    y = ytm_from_price(100.0, 10.0, 2, date(2036, 1, 1), asof=ASOF)
    assert y is not None
    assert abs(y - 10.0) < 1e-6


def test_ytm_discount_above_coupon_premium_below():
    disc = ytm_from_price(95.0, 5.0, 1, date(2031, 1, 1), asof=ASOF)
    assert disc is not None and disc > 5.0 and disc < 7.0
    prem = ytm_from_price(105.0, 10.0, 2, date(2036, 1, 1), asof=ASOF)
    assert prem is not None and 9.0 < prem < 10.0


def test_ytm_zero_coupon_hand_formula():
    # 5Y zero-coupon at 80 → ytm = (100/80)^(1/5) - 1 = 4.564%.
    y = ytm_from_price(80.0, 0.0, 1, date(2031, 1, 1), asof=ASOF)
    expected = ((100.0 / 80.0) ** (1.0 / 5.0) - 1.0) * 100.0
    assert y is not None
    assert abs(y - expected) < 0.5  # fractional-period Newton, 0.5% tolerance


def test_ytm_guards_bad_inputs():
    future = date(2030, 1, 1)
    assert ytm_from_price(0.0, 10.0, 2, future, asof=ASOF) is None
    assert ytm_from_price(-5.0, 10.0, 2, future, asof=ASOF) is None
    assert ytm_from_price(float("nan"), 10.0, 2, future, asof=ASOF) is None
    assert ytm_from_price(float("inf"), 10.0, 2, future, asof=ASOF) is None
    assert ytm_from_price(100.0, -5.0, 2, future, asof=ASOF) is None
    assert ytm_from_price(100.0, 10.0, 0, future, asof=ASOF) is None
    assert ytm_from_price(100.0, 10.0, 2, date(2020, 1, 1), asof=ASOF) is None  # matured
    assert ytm_from_price(100.0, 10.0, 2, ASOF, asof=ASOF) is None


def test_to_price_pct_normalization():
    assert to_price_pct(100.0, None) == 100.0
    assert abs((to_price_pct(1374.5, 1000.0) or 0) - 137.45) < 1e-9  # absolute → % of face
    assert abs((to_price_pct(0.2, 1000.0) or 0) - 0.02) < 1e-9  # penny quote
    assert to_price_pct(float("nan"), 1000.0) is None
    assert to_price_pct(float("inf"), 1000.0) is None
    assert to_price_pct(0, 1000.0) is None
    assert to_price_pct(None, 1000.0) is None
    assert to_price_pct("100.5", None) == 100.5


def test_sane_yield_and_tolerance():
    assert sane_yield(10.0, 10.0) is True
    assert sane_yield(12.0, 11.0) is True  # within 15 pp
    assert sane_yield(12.0, 30.0) is False  # |12-30| = 18 > 15
    assert sane_yield(None, 10.0) is False
    assert sane_yield(10.0, None) is False
    assert sane_yield(-5.0, 10.0) is False
    assert sane_yield(10.0, float("nan")) is False
    assert sanity_tolerance_pp() == 15.0


# ══════════════════════════════════════════════════════════════════════════ #
# desk/repository.py — exercised against the in-memory SQLite schema
# (root conftest.py recompiles BigInteger PKs to INTEGER so they autoincrement).
# ══════════════════════════════════════════════════════════════════════════ #


async def _count_rows(session, model) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())


def _rv_signal() -> RVSignal:
    return RVSignal(
        internal_id="RV-1",
        peer_currency="USD",
        z_score=1.5,
        spread_pct=3.0,
        fair_spread_pct=8.0,
        side="buy",
        rationale="cheap vs peers",
        peer_set=["B", "C"],
        asof_date=ASOF,
    )


def _carry_trade() -> CarryTrade:
    return CarryTrade(
        internal_id="CT-1",
        notional=Decimal("1000"),
        coupon_pct=10.0,
        funding_rate_pct=6.0,
        rolldown_bps=12.5,
        expected_pnl_pct=2.1,
        breakeven_bps=36.0,
        horizon_days=30,
        asof_date=ASOF,
    )


def _repo_deal() -> RepoDeal:
    return RepoDeal(
        internal_id="RD-1",
        notional=Decimal("1000"),
        haircut_pct=5.0,
        repo_rate_pct=10.0,
        tenor_days=30,
        cash_lent=Decimal("950.00"),
        collateral_value=Decimal("1000.00"),
        accrued_interest=Decimal("7.81"),
        asof_date=ASOF,
    )


def _stress_result(name: str = "T1") -> StressResult:
    return StressResult(
        scenario=StressScenario(
            kind="parallel", name=name, description="d", rate_shocks={"1Y": 1.0}
        ),
        portfolio_value=Decimal("1000.00"),
        stressed_value=Decimal("950.00"),
        pnl=Decimal("-50.00"),
        pnl_pct=-5.0,
        by_position={"A": Decimal("-50.00")},
        by_tenor={"1Y": Decimal("-50.00")},
        asof_date=ASOF,
    )


def _spread_report() -> SpreadReport:
    return SpreadReport(
        internal_id="SR-1",
        currency="USD",
        tenor_years=0.9993,
        ytm_pct=5.2632,
        flat_yield_pct=5.2632,
        z_spread_pct=-4.7368,
        g_spread_pct=-4.7368,
        curve_rate_pct=10.0,
        model_price=90.9091,
        market_price=95.0,
        mispricing_pct=-4.3062,
        side="rich",
        asof_date=ASOF,
    )


async def test_save_curve_points_empty_and_rows():
    async with session_scope() as session:
        assert await save_curve_points(session, currency="USD", points=[]) == 0
        n = await save_curve_points(
            session,
            currency="USD",
            points=[("1Y", 1.0, 10.0), ("10Y", 10.0, 8.0)],
            ns_params={"beta0": 10.0},
        )
        assert n == 2
        rows = (
            (await session.execute(select(CurvePointORM).where(CurvePointORM.currency == "USD")))
            .scalars()
            .all()
        )
        assert len(rows) == 2
        assert rows[0].ns_params == {"beta0": 10.0}
        assert float(rows[0].years) == 1.0
        assert float(rows[0].rate_pct) == 10.0


async def test_save_curve_points_no_duplicates_same_day():
    async with session_scope() as session:
        points = [("1Y", 1.0, 10.0)]
        assert await save_curve_points(session, currency="USD", points=points) == 1
        c1 = await _count_rows(session, CurvePointORM)
        assert await save_curve_points(session, currency="USD", points=points) == 1
        # sqlite path deletes the day's points first → still one row.
        assert await _count_rows(session, CurvePointORM) == c1


async def test_save_rv_signals_upsert_by_key():
    async with session_scope() as session:
        sig = _rv_signal()
        assert await save_rv_signals(session, []) == 0
        assert await save_rv_signals(session, [sig]) == 1
        before = await _count_rows(session, RVSignalORM)
        await save_rv_signals(session, [sig.model_copy(update={"z_score": 2.0, "side": "sell"})])
        # Upsert by (internal_id, peer_currency, asof_date) → still one row.
        assert await _count_rows(session, RVSignalORM) == before
        rows = await latest_rv_signals(session, limit=10)
        assert len(rows) == 1
        assert float(rows[0].z_score) == 2.0
        assert rows[0].side == "sell"
        assert rows[0].peer_set == ["B", "C"]


async def test_latest_rv_signals_limit():
    async with session_scope() as session:
        await session.execute(delete(RVSignalORM))
        sig = _rv_signal()
        await save_rv_signals(session, [sig, sig.model_copy(update={"internal_id": "RV-2"})])
        assert len(await latest_rv_signals(session, limit=1)) == 1


async def test_save_carry_trades_upsert_by_key():
    async with session_scope() as session:
        trade = _carry_trade()
        assert await save_carry_trades(session, []) == 0
        await save_carry_trades(session, [trade])
        before = await _count_rows(session, CarryTradeORM)
        await save_carry_trades(session, [trade.model_copy(update={"expected_pnl_pct": 3.0})])
        assert await _count_rows(session, CarryTradeORM) == before
        rows = (await session.execute(select(CarryTradeORM))).scalars().all()
        assert len(rows) == 1
        assert float(rows[0].expected_pnl_pct) == 3.0


# Note: save_repo_deal has no unique constraint — two saves are two rows.
async def test_save_repo_deal_insert():
    async with session_scope() as session:
        await save_repo_deal(session, _repo_deal())
        await save_repo_deal(session, _repo_deal())
        assert await _count_rows(session, RepoDealORM) == 2
        row = (
            (await session.execute(select(RepoDealORM).where(RepoDealORM.internal_id == "RD-1")))
            .scalars()
            .first()
        )
        assert float(row.cash_lent) == 950.0
        assert float(row.haircut_pct) == 5.0


async def test_save_stress_run_upsert_returns_id():
    async with session_scope() as session:
        res = _stress_result()
        id1 = await save_stress_run(session, res)
        id2 = await save_stress_run(session, res)  # same scenario+date → upsert
        assert isinstance(id1, int) and isinstance(id2, int)
        assert await _count_rows(session, StressRunORM) == 1
        row = (await session.execute(select(StressRunORM))).scalar_one()
        assert row.scenario["kind"] == "parallel"
        assert row.by_position == {"A": -50.0}


async def test_latest_stress_runs_ordering():
    async with session_scope() as session:
        await session.execute(delete(StressRunORM))
        await save_stress_run(session, _stress_result(name="ORDER-A"))
        # Pin the older run's created_at so ordering is deterministic.
        await session.execute(
            update(StressRunORM)
            .where(StressRunORM.scenario_name == "ORDER-A")
            .values(created_at=datetime(2000, 1, 1, 12, 0, 0))
        )
        await save_stress_run(session, _stress_result(name="ORDER-B"))
        latest = await latest_stress_runs(session, limit=10)
        assert [r.scenario_name for r in latest] == ["ORDER-B", "ORDER-A"]


async def test_save_spread_reports_upsert_by_key():
    async with session_scope() as session:
        rep = _spread_report()
        assert await save_spread_reports(session, []) == 0
        await save_spread_reports(session, [rep])
        before = await _count_rows(session, SpreadReportORM)
        await save_spread_reports(session, [rep.model_copy(update={"flat_yield_pct": 5.5})])
        assert await _count_rows(session, SpreadReportORM) == before
        rows = await latest_spread_reports(session, limit=10)
        assert len(rows) == 1
        assert float(rows[0].flat_yield_pct) == 5.5
        assert rows[0].side == "rich"


async def test_latest_spread_reports_limit():
    async with session_scope() as session:
        await session.execute(delete(SpreadReportORM))
        await save_spread_reports(session, [_spread_report()])
        rows = await latest_spread_reports(session, limit=1)
        assert len(rows) == 1
        assert rows[0].internal_id == "SR-1"
