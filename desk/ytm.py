"""Shared YTM helpers: price normalization and a Newton-Raphson yield solver.

The scraper and the demo/desk API must agree on what a "sane" yield is, so
both sides import from here instead of re-implementing the formula.  This is
what keeps huge yields caused by missing/garbage source parameters out of the
product: a source-reported yield is only trusted when a price exists and it is
within ``_DEFAULT_TOLERANCE_PP`` percentage points of the yield implied by the
coupon schedule.
"""

from __future__ import annotations

import os
from datetime import date
from math import isfinite
from typing import Any

_DEFAULT_TOLERANCE_PP = 15.0


def to_price_pct(price: Any, nominal: Any) -> float | None:
    """Normalize a raw source price to percent-of-face (100.0 = par).

    The Aigenis feed quotes most instruments in absolute units (e.g. 10039.58
    for a 10 000-nominal bond) while MOEX quotes everything as % of face.
    Consumers downstream (desk, scoring, demo) expect the percent scale, so a
    value that sits within 0.5x-500x of the nominal is treated as absolute and
    converted; anything else passes through as already-percent.  Returns None
    for missing/non-positive prices.
    """
    if price is None:
        return None
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if not isfinite(p) or p <= 0:
        return None
    if nominal is not None:
        try:
            nom = float(nominal)
        except (TypeError, ValueError):
            nom = 0.0
        if nom > 0 and 0.5 <= p / nom <= 500:
            return p / nom * 100.0
    return p


def ytm_from_price(
    price_pct: float,
    coupon_rate_pct: float,
    coupon_frequency: int,
    maturity: date,
    asof: date | None = None,
) -> float | None:
    """Approximate YTM (in percent) from a price quoted as % of face value.

    Newton-Raphson on the present-value equation.  Returns None when the
    equation cannot be solved (no maturity, non-positive price, etc.), so
    callers can honestly show "insufficient data" instead of a fake yield.
    """
    if not isfinite(price_pct) or price_pct <= 0:
        return None
    if not isfinite(coupon_rate_pct) or coupon_rate_pct < 0:
        return None
    if coupon_frequency <= 0:
        return None
    ref = asof or date.today()
    if maturity is None or maturity <= ref:
        return None
    years = (maturity - ref).days / 365.25
    if years <= 0:
        return None
    # The equation is homogeneous in face, so fix face=100 to match price_pct.
    face = 100.0
    c = face * coupon_rate_pct / 100.0 / coupon_frequency
    n = int(years * coupon_frequency)
    if n <= 0:
        return None
    y = (coupon_rate_pct / 100.0) * (face / price_pct)
    if y <= -0.99:
        return None
    for _ in range(50):
        pv_coupons = sum(c / (1 + y / coupon_frequency) ** i for i in range(1, n + 1))
        pv_face = face / (1 + y / coupon_frequency) ** n
        px = pv_coupons + pv_face
        dpx = -sum(
            i * c / (coupon_frequency * (1 + y / coupon_frequency) ** (i + 1))
            for i in range(1, n + 1)
        )
        dpx -= n * face / (coupon_frequency * (1 + y / coupon_frequency) ** (n + 1))
        if dpx == 0:
            break
        diff = px - price_pct
        if abs(diff) < 1e-6:
            return y * 100.0
        y -= diff / dpx
        if y <= -0.99:
            return None
    return y * 100.0 if y > -0.99 else None


def sanity_tolerance_pp() -> float:
    """Allowed deviation (percentage points) between source and computed YTM."""
    try:
        return float(os.getenv("MOEX_YTM_SANITY_TOL_PP", str(_DEFAULT_TOLERANCE_PP)))
    except ValueError:
        return _DEFAULT_TOLERANCE_PP


def sane_yield(source_ytm_pct: float | None, computed_ytm_pct: float | None) -> bool:
    """Whether a source-supplied yield may be persisted as-is.

    A yield is sane only when it is positive AND our own estimate from the
    coupon schedule exists and is within ``sanity_tolerance_pp()`` of it.
    Without a computable estimate (missing coupon/maturity, or the bond
    matures before the next coupon period) the source value is NOT trusted:
    MOEX ISS reports garbage for such rows (negative values, 1374%, etc.).
    """
    if source_ytm_pct is None or computed_ytm_pct is None:
        return False
    if not isfinite(source_ytm_pct) or source_ytm_pct <= 0:
        return False
    if not isfinite(computed_ytm_pct):
        return False
    return abs(source_ytm_pct - computed_ytm_pct) <= sanity_tolerance_pp()
