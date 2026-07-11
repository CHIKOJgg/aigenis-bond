"""Yield Curve: парсинг реальных точек + Nelson-Siegel интерполяция."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from math import exp
from statistics import fmean

from scipy.optimize import minimize

from desk.models import CurvePoint, NelsonSiegelParams, YieldCurve

TENOR_YEARS = {
    "1M": 1 / 12,
    "3M": 0.25,
    "6M": 0.5,
    "1Y": 1.0,
    "2Y": 2.0,
    "3Y": 3.0,
    "5Y": 5.0,
    "7Y": 7.0,
    "10Y": 10.0,
    "20Y": 20.0,
    "30Y": 30.0,
}


def _ns_rate(t: float, beta0: float, beta1: float, beta2: float, tau: float) -> float:
    if t <= 0:
        return beta0 + beta1
    x = t / tau
    factor1 = (1 - exp(-x)) / x
    factor2 = factor1 - exp(-x)
    return beta0 + beta1 * factor1 + beta2 * factor2


def fit_nelson_siegel(points: list[CurvePoint]) -> NelsonSiegelParams:
    """Подобрать параметры NS по точкам кривой (минимизация MSE)."""
    if len(points) < 3:
        return NelsonSiegelParams(beta0=0.0, beta1=0.0, beta2=0.0, tau=1.5)

    ts = [p.years for p in points]
    ys = [p.rate_pct for p in points]

    def _loss(params: list[float]) -> float:
        b0, b1, b2, tau = params
        if tau <= 0:
            return 1e9
        err = sum((_ns_rate(t, b0, b1, b2, tau) - y) ** 2 for t, y in zip(ts, ys, strict=True))
        return err

    init = [fmean(ys), ys[0] - ys[-1] if len(ys) > 1 else 0.0, 0.0, 1.5]
    res = minimize(_loss, init, method="Nelder-Mead")
    b0, b1, b2, tau = res.x
    return NelsonSiegelParams(
        beta0=round(float(b0), 4),
        beta1=round(float(b1), 4),
        beta2=round(float(b2), 4),
        tau=round(float(max(tau, 0.01)), 4),
    )


def interpolate(_curve: YieldCurve, params: NelsonSiegelParams, tenor: str) -> float:
    years = TENOR_YEARS.get(tenor)
    if years is None:
        raise ValueError(f"unknown tenor {tenor}")
    return _ns_rate(years, params.beta0, params.beta1, params.beta2, params.tau)


def curve_from_bonds(bonds: Iterable) -> YieldCurve:
    """Сгруппировать облигации по срокам и построить среднюю кривую."""
    buckets: dict[str, list[float]] = {}
    for b in bonds:
        if b.maturity_date is None or b.yield_to_maturity is None:
            continue
        years = (b.maturity_date - datetime.now(UTC).date()).days / 365.25
        if years <= 0:
            continue
        tenor = _nearest_tenor(years)
        buckets.setdefault(tenor, []).append(float(b.yield_to_maturity))
    points = [
        CurvePoint(
            tenor=t,
            years=TENOR_YEARS[t],
            rate_pct=round(fmean(vs), 4),
        )
        for t, vs in sorted(buckets.items(), key=lambda kv: TENOR_YEARS[kv[0]])
    ]
    currency = next((b.currency for b in bonds if getattr(b, "currency", None)), "USD")
    return YieldCurve(currency=currency, observed_at=datetime.now(UTC), points=points)


def _nearest_tenor(years: float) -> str:
    best = min(TENOR_YEARS.items(), key=lambda kv: abs(kv[1] - years))
    return best[0]


def curve_slope(curve: YieldCurve) -> float:
    return curve.slope()


def curve_curvature(_curve: YieldCurve, params: NelsonSiegelParams) -> float:
    return params.beta2
