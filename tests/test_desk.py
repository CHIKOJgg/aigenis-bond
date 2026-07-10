"""Pure-math tests for the Fixed Income Desk analytics.

These verify numerical correctness of the core calculations without any DB or
network access, so they run fast and are a good safety net for refactors.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from desk.duration import duration_report
from desk.models import CurvePoint, NelsonSiegelParams
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
