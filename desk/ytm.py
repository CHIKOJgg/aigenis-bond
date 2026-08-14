"""Shared YTM helpers: price normalization and a Newton-Raphson yield solver.

The scraper and the demo/desk API must agree on what a "sane" yield is, so
both sides import from here instead of re-implementing the formula.  This is
what keeps huge yields caused by missing/garbage source parameters out of the
product: a source-reported yield is only trusted when a price exists and it is
within ``_DEFAULT_TOLERANCE_PP`` percentage points of the yield implied by the
coupon schedule.
"""

from __future__ import annotations

import math
import os
from datetime import date
from math import isfinite
from typing import Any

_DEFAULT_TOLERANCE_PP = 15.0


def to_price_pct(price: Any, nominal: Any) -> float | None:
    """Normalize a raw source price to percent-of-face (100.0 = par).

    The DB contract is percent-of-face for every market: MOEX and BCSE quote
    percentages natively and the Aigenis client converts absolute settlement
    units at ingestion (``_to_price_pct``).

    Only values that cannot be bond quotes in percent (e.g. prices > 500 or
    penny quotes < 0.5, or absolute prices near large nominals >= 2000) are
    treated as absolute settlement units and converted to percent of face.
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
        if nom > 0 and (p > 500 or p < 0.5 or (nom >= 2000 and p > 150 and abs(p - nom) < abs(p - 100))):
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

    Newton-Raphson on the present-value equation supporting fractional first period.
    Returns None when the equation cannot be solved.
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
    face = 100.0
    c = face * coupon_rate_pct / 100.0 / coupon_frequency
    freq = coupon_frequency

    # Total period count N = years * freq.
    # n is total coupon payments remaining, w is fraction of period to next payment (0 < w <= 1).
    total_periods = years * freq
    rounded_periods = round(total_periods)
    if abs(total_periods - rounded_periods) < 0.02:
        n = max(1, int(rounded_periods))
        w = 1.0
    else:
        n = max(1, math.ceil(total_periods))
        w = total_periods - (n - 1)
        if w <= 0 or w > 1.0:
            w = 1.0

    y = (coupon_rate_pct / 100.0) * (face / price_pct)
    if not isfinite(y) or y <= -0.99:
        y = 0.05

    for _ in range(50):
        base = 1 + y / freq
        if base <= 1e-4:
            return None

        # Present value of coupons and face with fractional first period w
        pv_coupons = sum(c / (base ** (i - 1 + w)) for i in range(1, n + 1))
        pv_face = face / (base ** (n - 1 + w))
        px = pv_coupons + pv_face

        # Derivative with respect to y
        dpx = -sum(
            (i - 1 + w) * c / (freq * (base ** (i + w)))
            for i in range(1, n + 1)
        )
        dpx -= (n - 1 + w) * face / (freq * (base ** (n + w)))

        if dpx == 0 or not isfinite(dpx):
            break

        # px is the dirty price. Convert it to clean price by subtracting accrued interest
        accrued = (1.0 - w) * c if w < 1.0 else 0.0
        px_clean = px - accrued

        diff = px_clean - price_pct
        if abs(diff) < 1e-6:
            return y * 100.0
        y -= diff / dpx
        if y <= -0.99:
            return None

    return y * 100.0 if isfinite(y) and y > -0.99 else None



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
