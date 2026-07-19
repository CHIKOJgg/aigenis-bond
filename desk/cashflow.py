"""Day-count conventions, coupon schedules and accrued interest.

The desk previously split a bond's life into equal ``/365.25`` periods, which
is inaccurate for anything but theoretical bonds. This module provides proper
day-count year fractions (30/360, ACT/360, ACT/365, ACT/ACT), real coupon-date
schedules generated from the issue date, and accrued-interest math — the
building blocks for correct DV01, carry and income projections.
"""

from __future__ import annotations

import calendar
from datetime import date

CONVENTIONS = ("30/360", "ACT/360", "ACT/365", "ACT/ACT")


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def year_fraction(d1: date, d2: date, convention: str = "ACT/ACT") -> float:
    """Year fraction between two dates under the given day-count ``convention``."""
    if d2 <= d1:
        return 0.0
    if convention == "30/360":
        day1 = min(d1.day, 30)
        day2 = min(d2.day, 30)
        return (360 * (d2.year - d1.year) + 30 * (d2.month - d1.month) + (day2 - day1)) / 360.0
    if convention == "ACT/360":
        return (d2 - d1).days / 360.0
    if convention == "ACT/365":
        return (d2 - d1).days / 365.0
    # ACT/ACT: actual days over the (leap-aware) length of the start year.
    days_in_year = 366 if _is_leap(d1.year) else 365
    return (d2 - d1).days / days_in_year


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def coupon_dates(issue_date: date, maturity_date: date, frequency: int) -> list[date]:
    """All coupon payment dates from ``issue_date`` through ``maturity_date``."""
    freq = frequency if frequency in (1, 2, 4, 12) else 2
    step = 12 // freq
    dates: list[date] = []
    cur = issue_date
    while cur < maturity_date:
        dates.append(cur)
        cur = _add_months(cur, step)
    dates.append(maturity_date)  # final coupon coincides with redemption
    return dates


def accrued_interest(
    *,
    coupon_rate_pct: float,
    coupon_frequency: int,
    issue_date: date | None,
    maturity_date: date | None,
    asof: date,
    convention: str = "ACT/365",
    face: float = 100.0,
) -> float:
    """Accrued interest per ``face`` of par as of ``asof`` (ex-coupon=0)."""
    if (
        not coupon_frequency
        or coupon_frequency <= 0
        or coupon_rate_pct <= 0
        or issue_date is None
        or maturity_date is None
        or asof >= maturity_date
    ):
        return 0.0
    schedule = coupon_dates(issue_date, maturity_date, coupon_frequency)
    prev: date | None = None
    nxt: date | None = None
    for d in schedule:
        if d <= asof:
            prev = d
        if d > asof:
            nxt = d
            break
    if prev is None:
        prev = issue_date
    if nxt is None:
        nxt = maturity_date
    period_frac = year_fraction(prev, nxt, convention)
    if period_frac <= 0:
        return 0.0
    elapsed = year_fraction(prev, asof, convention)
    frac = elapsed / period_frac
    coupon_per_period = face * coupon_rate_pct / 100 / coupon_frequency
    return coupon_per_period * frac


def pricing_cashflows(
    *,
    nominal: float,
    coupon_rate_pct: float,
    coupon_frequency: int,
    maturity: date,
    asof: date,
    issue_date: date | None = None,
    convention: str = "ACT/365",
) -> list[tuple[float, float]]:
    """Future cashflows as ``(years_from_asof, amount)`` for pricing/duration.

    Coupon dates are generated from the issue date when available (so the
    day-count timing is exact); otherwise a month-spaced schedule is derived
    backward from maturity. Redemption is added to the final flow.
    """
    if maturity <= asof:
        return []
    freq = coupon_frequency if coupon_frequency in (1, 2, 4, 12) else 2
    cf_per_period = nominal * coupon_rate_pct / 100 / freq

    if issue_date is not None:
        schedule = coupon_dates(issue_date, maturity, freq)
        flows = [
            (year_fraction(asof, d, convention), cf_per_period + (nominal if d == maturity else 0.0))
            for d in schedule
            if d > asof
        ]
        if not flows:
            flows = [(year_fraction(asof, maturity, convention), nominal)]
        return flows

    # Fallback: month-spaced coupons backward from maturity (no issue date).
    step = 12 // freq
    dates: list[date] = []
    cur = maturity
    while cur > asof:
        dates.append(cur)
        cur = _add_months(cur, -step)
    flows = []
    for d in sorted(dates):
        t = year_fraction(asof, d, convention)
        amt = cf_per_period + (nominal if d == maturity else 0.0)
        flows.append((t, amt))
    return flows
