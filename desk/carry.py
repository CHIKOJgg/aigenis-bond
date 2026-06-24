"""Carry Trade: P&L от купона и rolldown при заданном funding rate."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from desk.models import CarryTrade, NelsonSiegelParams
from scraper.models import Bond


def _rolldown_bps(ytm_pct: float, ytm_next_pct: float) -> float:
    return (ytm_pct - ytm_next_pct) * 100


def carry_for_bond(
    bond: Bond,
    *,
    funding_rate_pct: float,
    horizon_days: int = 90,
    curve_params: NelsonSiegelParams | None = None,
    asof: date | None = None,
) -> CarryTrade | None:
    """Оценить carry-P&L для одной облигации."""
    if (
        bond.yield_to_maturity is None
        or bond.maturity_date is None
        or bond.coupon_rate is None
    ):
        return None

    asof = asof or date.today()
    coupon_pct = float(bond.coupon_rate)
    ytm_pct = float(bond.yield_to_maturity)

    years_to_mat = max((bond.maturity_date - asof).days / 365.25, 0.0)
    years_after = max(years_to_mat - horizon_days / 365.25, 0.0)

    if curve_params is not None and years_after > 0:
        try:
            from desk.yield_curve import _ns_rate

            ytm_next = _ns_rate(
                years_after,
                curve_params.beta0,
                curve_params.beta1,
                curve_params.beta2,
                curve_params.tau,
            )
        except Exception:  # noqa: BLE001
            ytm_next = ytm_pct
    else:
        ytm_next = ytm_pct

    rolldown = _rolldown_bps(ytm_pct, ytm_next)
    carry = coupon_pct - funding_rate_pct
    expected_pnl_pct = carry * (horizon_days / 365.25) - 0.5 * abs(rolldown) / 100
    breakeven = max(0.0, (funding_rate_pct - coupon_pct) * (horizon_days / 365.25) * 100)

    return CarryTrade(
        internal_id=bond.internal_id,
        notional=bond.nominal or Decimal("1000"),
        coupon_pct=coupon_pct,
        funding_rate_pct=funding_rate_pct,
        rolldown_bps=round(rolldown, 2),
        expected_pnl_pct=round(expected_pnl_pct, 4),
        breakeven_bps=round(breakeven, 2),
        horizon_days=horizon_days,
        asof_date=asof,
    )


def rank_carry(bonds: list[Bond], *, funding_rate_pct: float = 5.0) -> list[CarryTrade]:
    """Отранжировать облигации по ожидаемому carry-P&L."""
    out: list[CarryTrade] = []
    for b in bonds:
        ct = carry_for_bond(b, funding_rate_pct=funding_rate_pct)
        if ct is not None:
            out.append(ct)
    out.sort(key=lambda c: c.expected_pnl_pct, reverse=True)
    return out
