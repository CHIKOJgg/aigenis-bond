"""Comprehensive tests for desk.relative_value (rich/cheap RV signals)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from desk.models import CurvePoint, YieldCurve
from desk.relative_value import (
    _bucket_by_tenor,
    _bucket_zscore,
    relative_value_signals,
    signals_from_curve,
)


def _bond(internal_id, ytm, currency="BYN", maturity=date(2028, 1, 1), price=100.0):
    return SimpleNamespace(
        internal_id=internal_id,
        name=internal_id,
        issuer="Issuer",
        isin=None,
        price=price,
        nominal=1000,
        yield_to_maturity=ytm,
        coupon_rate=10.0,
        coupon_frequency=2,
        currency=currency,
        start_date=date(2024, 1, 1),
        maturity_date=maturity,
        status="active",
    )


def test_bucket_by_tenor_boundaries():
    assert _bucket_by_tenor(0.5) == "short"
    assert _bucket_by_tenor(1.0) == "short"
    assert _bucket_by_tenor(3.0) == "mid"
    assert _bucket_by_tenor(5.0) == "mid"
    assert _bucket_by_tenor(10.0) == "long"


def test_bucket_zscore_few_samples_returns_zero():
    avg, z = _bucket_zscore([1.0], 5.0)
    # <3 samples => no meaningful z, returns (0.0, value)
    assert avg == 0.0 and z == 5.0


def test_bucket_zscore_computes_z():
    avg, z = _bucket_zscore([8.0, 10.0, 12.0, 14.0], 14.0)
    # mean = 11, pstdev = sqrt(5) ~= 2.236
    assert avg == 11.0
    assert z == (14.0 - 11.0) / (5.0 ** 0.5)


def test_relative_value_signals_buy_and_sell():
    bonds = [
        _bond("low", 8.0),
        _bond("mid", 10.0),
        _bond("high", 12.0),
        _bond("top", 14.0),
    ]
    signals = relative_value_signals(bonds, asof=date(2024, 1, 1))
    by_id = {s.internal_id: s for s in signals}
    assert by_id["top"].side == "buy"
    assert by_id["low"].side == "sell"
    # sorted by |z| descending
    assert signals[0].internal_id in ("top", "low")


def test_relative_value_signals_needs_three_per_bucket():
    bonds = [_bond("a", 9.0), _bond("b", 11.0)]
    assert relative_value_signals(bonds, asof=date(2024, 1, 1)) == []


def test_relative_value_signals_excludes_extreme_ytm():
    # 1545% bond must be filtered out by the eligibility gate, not reported.
    bonds = [
        _bond("ok1", 8.0),
        _bond("ok2", 10.0),
        _bond("ok3", 12.0),
        _bond("crazy", 1545.0),
    ]
    signals = relative_value_signals(bonds, asof=date(2024, 1, 1))
    ids = {s.internal_id for s in signals}
    assert "crazy" not in ids


def test_relative_value_signals_groups_by_currency():
    bonds = [
        _bond("u1", 6.0, currency="USD"),
        _bond("u2", 7.0, currency="USD"),
        _bond("u3", 9.0, currency="USD"),
        _bond("b1", 10.0, currency="BYN"),
        _bond("b2", 12.0, currency="BYN"),
        _bond("b3", 14.0, currency="BYN"),
    ]
    signals = relative_value_signals(bonds, asof=date(2024, 1, 1))
    usd = [s for s in signals if s.peer_currency == "USD"]
    byn = [s for s in signals if s.peer_currency == "BYN"]
    assert len(usd) == 3 and len(byn) == 3


def test_signals_from_curve_buy_sell_hold():
    curve = YieldCurve(
        currency="BYN",
        observed_at=date(2024, 1, 1),
        points=[
            CurvePoint(tenor="1Y", years=1.0, rate_pct=12.0),
            CurvePoint(tenor="5Y", years=5.0, rate_pct=10.0),
            CurvePoint(tenor="10Y", years=10.0, rate_pct=9.0),
        ],
    )
    signals = signals_from_curve(curve)
    sides = {s.internal_id.split("-")[1]: s.side for s in signals}
    assert sides["1Y"] == "buy"   # highest rate => cheap
    assert sides["10Y"] == "sell"  # lowest rate => rich
    assert sides["5Y"] == "hold"


def test_signals_from_curve_needs_three_points():
    curve = YieldCurve(
        currency="BYN",
        observed_at=date(2024, 1, 1),
        points=[CurvePoint(tenor="1Y", years=1.0, rate_pct=10.0)],
    )
    assert signals_from_curve(curve) == []
