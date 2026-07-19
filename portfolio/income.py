"""Coupon income projection — the core "how much money and when?" for bonds.

Pure, deterministic functions (no I/O) that turn a bond's coupon terms into a
concrete cashflow schedule, and aggregate a set of holdings into an income
calendar: annual income, yield-on-cost, next payment and month-by-month totals.
"""
from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal

__all__ = [
    "CashFlow",
    "annual_income",
    "bond_cashflows",
    "portfolio_income",
]

_Q = Decimal("0.01")


class CashFlow:
    """A single future payment."""

    __slots__ = ("amount", "date", "internal_id", "kind")

    def __init__(self, *, date: date, amount: Decimal, kind: str, internal_id: str) -> None:
        self.date = date
        self.amount = amount.quantize(_Q)
        self.kind = kind  # "coupon" | "redemption"
        self.internal_id = internal_id

    def as_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "amount": float(self.amount),
            "kind": self.kind,
            "internal_id": self.internal_id,
        }


def _add_months(d: date, months: int) -> date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _face_value(amount_invested: Decimal, price: Decimal | None) -> Decimal:
    """Face (nominal) value bought for ``amount_invested`` at a % ``price``.

    Bond prices are quoted as a percent of par. Investing 1000 at price 98
    buys ~1020.41 of face value. If price is missing we assume par.
    """
    if price and price > 0:
        return (amount_invested * Decimal("100") / price)
    return amount_invested


def bond_cashflows(
    *,
    internal_id: str,
    amount_invested: Decimal,
    coupon_rate: Decimal | None,
    coupon_frequency: int | None,
    maturity_date: date | None,
    price: Decimal | None = None,
    from_date: date | None = None,
    include_redemption: bool = True,
    issue_date: date | None = None,
    day_count: str = "30/360",
    settlement: date | None = None,
) -> list[CashFlow]:
    """Project future cashflows for a single holding.

    Coupon dates are generated from ``issue_date`` when available (so the
    day-count timing is exact), keeping only dates strictly after ``from_date``
    (or ``settlement``). The per-coupon amount is day-count adjusted. When no
    ``issue_date`` is known we fall back to the legacy month-spaced schedule so
    existing callers (portfolio income calendar) stay unchanged. The final
    coupon coincides with maturity; principal is returned as a ``redemption``
    flow.
    """
    from_date = from_date or settlement or date.today()
    if maturity_date is None or maturity_date <= from_date:
        return []

    face = _face_value(amount_invested, price)
    flows: list[CashFlow] = []

    freq = coupon_frequency if coupon_frequency in (1, 2, 4, 12) else None
    if freq and coupon_rate and coupon_rate > 0:
        if issue_date is not None:
            from desk.cashflow import coupon_dates, year_fraction

            schedule = coupon_dates(issue_date, maturity_date, freq)
            for i, d in enumerate(schedule):
                if d <= from_date:
                    continue
                prev = schedule[i - 1] if i > 0 else issue_date
                yf = Decimal(str(year_fraction(prev, d, day_count)))
                per = face * (coupon_rate / Decimal("100")) * yf
                flows.append(
                    CashFlow(date=d, amount=per, kind="coupon", internal_id=internal_id)
                )
        else:
            step = 12 // freq
            per_period = face * (coupon_rate / Decimal("100")) / Decimal(freq)
            cur = maturity_date
            dates: list[date] = []
            while cur > from_date:
                dates.append(cur)
                cur = _add_months(cur, -step)
            for d in sorted(dates):
                flows.append(
                    CashFlow(date=d, amount=per_period, kind="coupon", internal_id=internal_id)
                )

    if include_redemption:
        flows.append(
            CashFlow(date=maturity_date, amount=face, kind="redemption", internal_id=internal_id)
        )

    flows.sort(key=lambda f: (f.date, f.kind))
    return flows


def annual_income(
    *,
    amount_invested: Decimal,
    coupon_rate: Decimal | None,
    price: Decimal | None = None,
) -> Decimal:
    """Expected coupon income per year for a holding (excludes principal)."""
    if not coupon_rate or coupon_rate <= 0:
        return Decimal("0.00")
    face = _face_value(amount_invested, price)
    return (face * coupon_rate / Decimal("100")).quantize(_Q)


def portfolio_income(
    holdings: list[dict],
    *,
    from_date: date | None = None,
    horizon_months: int = 12,
) -> dict:
    """Aggregate a coupon-income calendar across holdings.

    Each holding dict needs: ``internal_id``, ``amount`` and the bond terms
    (``coupon_rate``, ``coupon_frequency``, ``maturity_date``, ``price``,
    ``currency``, ``name``). Returns totals, yield-on-cost, the next payment
    and a month-by-month breakdown of coupon income over ``horizon_months``.
    """
    from_date = from_date or date.today()
    horizon_end = _add_months(from_date, horizon_months)

    total_invested = Decimal("0.00")
    total_annual = Decimal("0.00")
    all_coupons: list[CashFlow] = []
    per_bond: list[dict] = []

    for h in holdings:
        amount = Decimal(str(h["amount"]))
        coupon_rate = h.get("coupon_rate")
        coupon_rate = Decimal(str(coupon_rate)) if coupon_rate is not None else None
        price = h.get("price")
        price = Decimal(str(price)) if price is not None else None
        total_invested += amount

        ann = annual_income(amount_invested=amount, coupon_rate=coupon_rate, price=price)
        total_annual += ann

        flows = bond_cashflows(
            internal_id=str(h["internal_id"]),
            amount_invested=amount,
            coupon_rate=coupon_rate,
            coupon_frequency=int(h["coupon_frequency"]) if h.get("coupon_frequency") is not None else None,
            maturity_date=date.fromisoformat(h["maturity_date"]) if isinstance(h.get("maturity_date"), str) else h.get("maturity_date"),
            price=price,
            from_date=from_date,
            include_redemption=False,
        )
        all_coupons.extend(flows)
        next_flow = flows[0] if flows else None
        per_bond.append(
            {
                "internal_id": str(h["internal_id"]),
                "name": h.get("name"),
                "currency": h.get("currency"),
                "amount": float(amount),
                "annual_income": float(ann),
                "yield_on_cost": round(float(ann / amount * 100), 2) if amount > 0 else 0.0,
                "next_payment": next_flow.as_dict() if next_flow else None,
            }
        )

    all_coupons.sort(key=lambda f: f.date)
    next_payment = all_coupons[0].as_dict() if all_coupons else None

    horizon_income = sum(
        (f.amount for f in all_coupons if from_date < f.date <= horizon_end),
        start=Decimal("0.00"),
    )

    calendar_map: dict[str, Decimal] = {}
    for f in all_coupons:
        if f.date > horizon_end:
            continue
        key = f"{f.date.year}-{f.date.month:02d}"
        calendar_map[key] = calendar_map.get(key, Decimal("0.00")) + f.amount
    monthly_calendar = [
        {"month": k, "amount": float(v.quantize(_Q))} for k, v in sorted(calendar_map.items())
    ]

    yield_on_cost = (
        round(float(total_annual / total_invested * 100), 2) if total_invested > 0 else 0.0
    )

    return {
        "total_invested": float(total_invested.quantize(_Q)),
        "annual_income": float(total_annual.quantize(_Q)),
        "yield_on_cost": yield_on_cost,
        "next_payment": next_payment,
        "horizon_months": horizon_months,
        "income_next_horizon": float(Decimal(horizon_income).quantize(_Q)),
        "monthly_calendar": monthly_calendar,
        "per_bond": sorted(per_bond, key=lambda b: b["annual_income"], reverse=True),
    }
