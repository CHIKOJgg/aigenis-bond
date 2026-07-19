"""Carry Trade: P&L от купона и rolldown при заданном funding rate."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from desk.duration import duration_report
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
    if bond.yield_to_maturity is None or bond.maturity_date is None or bond.coupon_rate is None:
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
        except Exception:
            ytm_next = ytm_pct
    else:
        ytm_next = ytm_pct

    rolldown = _rolldown_bps(ytm_pct, ytm_next)
    # Modified duration drives the price sensitivity to the yield roll-down.
    mod_dur = duration_report(bond, asof=asof, ytm_override=ytm_pct).modified_duration
    # Carry = coupon income minus funding cost, annualised, over the horizon.
    carry_pnl_pct = (coupon_pct - funding_rate_pct) * (horizon_days / 365.25)
    # Rolldown P&L: as the bond ages it yields drop to the shorter tenor, so the
    # price appreciates by ~ modified_duration * (yield drop in decimal). A
    # positively-sloped curve (ytm_pct > ytm_next) therefore adds to P&L.
    rolldown_pnl_pct = mod_dur * (ytm_pct - ytm_next) / 100.0
    expected_pnl_pct = carry_pnl_pct + rolldown_pnl_pct
    # Breakeven adverse yield move (bps) that erases the positive carry: how far
    # rates can rise before the price loss equals the carry. Signed — a negative
    # carry yields a negative breakeven (no cushion).
    breakeven = (carry_pnl_pct / mod_dur * 100.0) if mod_dur > 0 else 0.0

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
