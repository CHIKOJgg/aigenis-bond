"""Z-spread / G-spread и сигнал «модельная цена vs рынок».

Что считаем:

- ``flat_yield`` — единая ставка, при которой PV денежных потоков облигации
  (по ``desk.cashflow.pricing_cashflows``) равен рыночной грязной цене.
  Решается бисекцией.
- ``curve_rate`` — ставка Nelson-Siegel кривой на точный тенор облигации.
- ``z_spread`` = flat_yield − curve_rate — спред к кривой на плоской базе.
- ``g_spread`` = YTM − curve_rate — простейший спред доходности к кривой.
- ``model_price`` — PV потоков по curve_rate; ``mispricing_pct`` —
  (model_price − market_price) / market_price × 100. Положительный → облигация
  дешевле модели (cheap), отрицательный → дороже (rich).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from desk.cashflow import accrued_interest, pricing_cashflows
from desk.models import NelsonSiegelParams, SpreadReport
from desk.yield_curve import _ns_rate
from desk.ytm import to_price_pct

_PV_LO_RATE = 0.001
_PV_HI_RATE = 0.60
_MISPRICING_THRESHOLD_PCT = 1.0


def _pv_at_rate(flows: list[tuple[float, float]], rate: float) -> float:
    return sum(amt / (1.0 + rate) ** t for t, amt in flows)


def solve_flat_yield(
    flows: list[tuple[float, float]],
    dirty_price: float,
    *,
    lo: float = _PV_LO_RATE,
    hi: float = _PV_HI_RATE,
    tol: float = 1e-7,
) -> float | None:
    """Найти ставку r: PV(потоки, r) = dirty_price (бисекция)."""
    if not flows or dirty_price <= 0:
        return None
    f_lo = _pv_at_rate(flows, lo) - dirty_price
    f_hi = _pv_at_rate(flows, hi) - dirty_price
    if f_lo * f_hi > 0:
        return None
    for _ in range(120):
        mid = (lo + hi) / 2.0
        f_mid = _pv_at_rate(flows, mid) - dirty_price
        if abs(f_mid) < tol or (hi - lo) < 1e-9:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def compute_spreads(
    bonds: Iterable,
    curves: dict[str, NelsonSiegelParams],
    *,
    asof: date | None = None,
) -> list[SpreadReport]:
    """Посчитать spread-отчёты по облигациям против NS-кривых валют.

    Облигации без цены/доходности/срока или без кривой валюты пропускаются.
    """
    asof = asof or date.today()
    reports: list[SpreadReport] = []

    for b in bonds:
        if b.maturity_date is None or b.yield_to_maturity is None or b.price is None:
            continue
        params = curves.get(str(b.currency))
        if params is None:
            continue

        tenor = max((b.maturity_date - asof).days / 365.25, 0.0)
        if tenor <= 0:
            continue

        curve_rate = _ns_rate(tenor, params.beta0, params.beta1, params.beta2, params.tau)
        ytm_pct = float(b.yield_to_maturity)
        clean_price = to_price_pct(b.price, getattr(b, "nominal", None))
        if clean_price is None:
            continue

        accrued = accrued_interest(
            coupon_rate_pct=float(b.coupon_rate) if b.coupon_rate is not None else 0.0,
            coupon_frequency=int(b.coupon_frequency) if b.coupon_frequency else 2,
            issue_date=b.start_date if getattr(b, "start_date", None) else None,
            maturity_date=b.maturity_date,
            asof=asof,
            face=100.0,
        )
        dirty_price = clean_price + accrued

        flows = pricing_cashflows(
            nominal=100.0,
            coupon_rate_pct=float(b.coupon_rate) if b.coupon_rate is not None else 0.0,
            coupon_frequency=int(b.coupon_frequency) if b.coupon_frequency else 2,
            maturity=b.maturity_date,
            asof=asof,
            issue_date=b.start_date if getattr(b, "start_date", None) else None,
        )

        flat = solve_flat_yield(flows, dirty_price)
        flat_pct = flat * 100.0 if flat is not None else None
        model_dirty = _pv_at_rate(flows, curve_rate / 100.0) if flows else None
        mispricing = (
            (model_dirty - dirty_price) / dirty_price * 100.0
            if model_dirty is not None and dirty_price > 0
            else None
        )
        if mispricing is None:
            side = "fair"
        elif mispricing >= _MISPRICING_THRESHOLD_PCT:
            side = "cheap"
        elif mispricing <= -_MISPRICING_THRESHOLD_PCT:
            side = "rich"
        else:
            side = "fair"

        reports.append(
            SpreadReport(
                internal_id=b.internal_id,
                currency=str(b.currency),
                tenor_years=round(tenor, 4),
                ytm_pct=round(ytm_pct, 4),
                flat_yield_pct=round(flat_pct, 4) if flat_pct is not None else None,
                z_spread_pct=round(flat_pct - curve_rate, 4) if flat_pct is not None else None,
                g_spread_pct=round(ytm_pct - curve_rate, 4),
                curve_rate_pct=round(curve_rate, 4),
                model_price=round(model_dirty, 4) if model_dirty is not None else None,
                market_price=round(dirty_price, 4),
                mispricing_pct=round(mispricing, 4) if mispricing is not None else None,
                side=side,
                asof_date=asof,
            )
        )

    reports.sort(key=lambda r: abs(r.mispricing_pct or 0.0), reverse=True)
    return reports
