"""Duration engine: Macaulay/Modified duration, convexity, DV01, key-rate."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

from desk.cashflow import pricing_cashflows
from desk.models import DurationReport
from scraper.models import Bond


def _cashflows(
    *,
    nominal: Decimal,
    coupon_rate_pct: float,
    coupon_frequency: int,
    maturity: date,
    ref: date,
    issue_date: date | None = None,
) -> list[tuple[float, float]]:
    """Future cashflows as ``(years_from_ref, amount)`` using real day-count."""
    return pricing_cashflows(
        nominal=float(nominal),
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        maturity=maturity,
        asof=ref,
        issue_date=issue_date,
    )


def _price_from_yield(flows: list[tuple[float, float]], ytm_pct: float, freq: int = 2) -> float:
    y = ytm_pct / 100
    return sum(cf / ((1 + y / freq) ** (freq * t)) for t, cf in flows)


def _price_shift(
    flows: list[tuple[float, float]], ytm_pct: float, shift_bps: float, freq: int = 2
) -> float:
    return _price_from_yield(flows, ytm_pct + shift_bps / 100, freq=freq)


def macaulay_duration(
    *,
    nominal: Decimal,
    coupon_rate_pct: float,
    coupon_frequency: int,
    ytm_pct: float,
    maturity: date,
    ref: date,
    issue_date: date | None = None,
) -> float:
    flows = _cashflows(
        nominal=nominal,
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        maturity=maturity,
        ref=ref,
        issue_date=issue_date,
    )
    if not flows:
        return 0.0
    price = _price_from_yield(flows, ytm_pct, freq=coupon_frequency)
    if price <= 0:
        return 0.0
    freq = coupon_frequency
    weighted = sum(t * cf / ((1 + ytm_pct / 100 / freq) ** (freq * t)) for t, cf in flows)
    return weighted / price


def modified_duration(
    *,
    nominal: Decimal,
    coupon_rate_pct: float,
    coupon_frequency: int,
    ytm_pct: float,
    maturity: date,
    ref: date,
    issue_date: date | None = None,
) -> float:
    mac = macaulay_duration(
        nominal=nominal,
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        ytm_pct=ytm_pct,
        maturity=maturity,
        ref=ref,
        issue_date=issue_date,
    )
    return mac / (1 + ytm_pct / 100 / coupon_frequency)


def convexity(
    *,
    nominal: Decimal,
    coupon_rate_pct: float,
    coupon_frequency: int,
    ytm_pct: float,
    maturity: date,
    ref: date,
    issue_date: date | None = None,
) -> float:
    flows = _cashflows(
        nominal=nominal,
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        maturity=maturity,
        ref=ref,
        issue_date=issue_date,
    )
    if not flows:
        return 0.0
    price = _price_from_yield(flows, ytm_pct, freq=coupon_frequency)
    freq = coupon_frequency
    y_per = ytm_pct / 100 / freq
    cvx = sum(cf * t * (t + 1 / freq) / ((1 + y_per) ** (freq * t + 2)) for t, cf in flows)
    return cvx / price


def dv01(
    *,
    nominal: Decimal,
    coupon_rate_pct: float,
    coupon_frequency: int,
    ytm_pct: float,
    maturity: date,
    ref: date,
    issue_date: date | None = None,
) -> float:
    """Dollar Value of 1bp: убыток стоимости при росте YTM на 1bp."""
    flows = _cashflows(
        nominal=nominal,
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        maturity=maturity,
        ref=ref,
        issue_date=issue_date,
    )
    if not flows:
        return 0.0
    p_up = _price_shift(flows, ytm_pct, 1, freq=coupon_frequency)
    p_now = _price_from_yield(flows, ytm_pct, freq=coupon_frequency)
    # Cashflows are already scaled by ``nominal`` (see ``_cashflows``), so both
    # ``p_now`` and ``p_up`` are full position values. ``p_now - p_up`` is thus
    # the dollar change in value for a 1bp yield move — i.e. DV01. Multiplying
    # by ``nominal / 100`` would overstate it by a factor of ``nominal / 100``.
    return float(p_now - p_up)


def _krd_label(tenor: float) -> str:
    return f"{int(tenor)}Y" if tenor >= 1 else f"{int(tenor * 12)}M"


def key_rate_durations(
    *,
    nominal: Decimal,
    coupon_rate_pct: float,
    coupon_frequency: int,
    ytm_pct: float,
    maturity: date,
    ref: date,
    issue_date: date | None = None,
    tenors: Iterable[float] = (0.25, 1, 2, 3, 5, 7, 10, 20, 30),
) -> dict[str, float]:
    """Key-rate (bucket) durations.

    Each future cashflow is attributed to its nearest tenor bucket; bumping a
    bucket's rate moves exactly the cashflows assigned to it. This guarantees
    every cashflow is covered (the old ±0.5y window left mid-bucket flows
    unbumped) and the bucket durations sum to (approximately) the total
    modified duration.
    """
    flows = _cashflows(
        nominal=nominal,
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        maturity=maturity,
        ref=ref,
        issue_date=issue_date,
    )
    tenor_list = list(tenors)
    out = {_krd_label(t): 0.0 for t in tenor_list}
    if not flows:
        return out
    freq = coupon_frequency
    base_price = _price_from_yield(flows, ytm_pct, freq=freq)
    if not base_price:
        return out
    y0 = ytm_pct / 100
    for t in tenor_list:
        bump = 0.0001
        bumped_price = 0.0
        for time, cf in flows:
            nearest = min(tenor_list, key=lambda x: abs(x - time))
            rate = (y0 + bump) if nearest == t else y0
            bumped_price += cf / ((1 + rate / freq) ** (freq * time))
        krd = -(bumped_price - base_price) / (base_price * bump)
        out[_krd_label(t)] = round(krd, 4)
    return out


def bond_modified_duration(bond: Any, *, asof: date | None = None) -> float | None:
    """Cashflow-based modified (rate-risk) duration for a bond-like row.

    Returns ``None`` when duration cannot be derived (missing maturity/YTM,
    zero/negative yield, or a numeric failure) so callers can fall back to a
    time-to-maturity proxy. This is the single source of truth for "duration"
    across the platform — do not substitute ``(maturity - today)`` for it.
    """
    ref = asof or date.today()
    maturity = getattr(bond, "maturity_date", None)
    if maturity is None:
        return None
    ytm = getattr(bond, "yield_to_maturity", None)
    if ytm is None:
        return None
    try:
        ytm_pct = float(ytm)
    except (TypeError, ValueError):
        return None
    if ytm_pct <= 0:
        # Zero yield (e.g. indexed-metal zero-coupons) has no meaningful rate
        # duration; let the caller fall back. Negative yields are invalid input.
        return None
    nominal = getattr(bond, "nominal", None) or Decimal("1000")
    try:
        nominal_d = Decimal(str(nominal))
    except (TypeError, ValueError):
        nominal_d = Decimal("1000")
    coupon = float(getattr(bond, "coupon_rate", None) or ytm_pct)
    freq = int(getattr(bond, "coupon_frequency", None) or 2)
    issue = getattr(bond, "start_date", None)
    try:
        return modified_duration(
            nominal=nominal_d,
            coupon_rate_pct=coupon,
            coupon_frequency=freq,
            ytm_pct=ytm_pct,
            maturity=maturity,
            ref=ref,
            issue_date=issue,
        )
    except Exception:
        return None


def duration_report(
    bond: Bond | None,
    *,
    asof: date | None = None,
    ytm_override: float | None = None,
) -> DurationReport:
    """Сформировать DurationReport для одной облигации или пустого портфеля."""
    ref = asof or date.today()
    if bond is None or bond.maturity_date is None:
        return DurationReport(
            internal_id=None,
            modified_duration=0.0,
            macaulay_duration=0.0,
            convexity=0.0,
            dv01=0.0,
            asof_date=ref,
        )

    nominal = bond.nominal or Decimal("1000")
    ytm = float(ytm_override if ytm_override is not None else (bond.yield_to_maturity or 0.0))
    coupon_pct = float(bond.coupon_rate) if bond.coupon_rate is not None else ytm
    freq = int(bond.coupon_frequency or 2)
    issue = bond.start_date

    mac = macaulay_duration(
        nominal=nominal,
        coupon_rate_pct=coupon_pct,
        coupon_frequency=freq,
        ytm_pct=ytm,
        maturity=bond.maturity_date,
        ref=ref,
        issue_date=issue,
    )
    mod = mac / (1 + ytm / 100 / freq)
    cvx = convexity(
        nominal=nominal,
        coupon_rate_pct=coupon_pct,
        coupon_frequency=freq,
        ytm_pct=ytm,
        maturity=bond.maturity_date,
        ref=ref,
        issue_date=issue,
    )
    dv = dv01(
        nominal=nominal,
        coupon_rate_pct=coupon_pct,
        coupon_frequency=freq,
        ytm_pct=ytm,
        maturity=bond.maturity_date,
        ref=ref,
        issue_date=issue,
    )
    krd = key_rate_durations(
        nominal=nominal,
        coupon_rate_pct=coupon_pct,
        coupon_frequency=freq,
        ytm_pct=ytm,
        maturity=bond.maturity_date,
        ref=ref,
        issue_date=issue,
    )

    from desk.cashflow import accrued_interest

    accrued = accrued_interest(
        coupon_rate_pct=coupon_pct,
        coupon_frequency=freq,
        issue_date=issue,
        maturity_date=bond.maturity_date,
        asof=ref,
        face=float(nominal),
    )

    return DurationReport(
        internal_id=bond.internal_id,
        modified_duration=round(mod, 4),
        macaulay_duration=round(mac, 4),
        convexity=round(cvx, 4),
        dv01=round(dv, 4),
        accrued_interest=round(accrued, 6),
        key_rate_durations=krd,
        asof_date=ref,
    )


def portfolio_duration(
    bonds: list[Bond],
    *,
    weights: dict[str, float] | None = None,
    asof: date | None = None,
) -> DurationReport:
    """Взвешенный по весам duration-отчёт по портфелю."""
    if not bonds:
        return DurationReport(
            modified_duration=0.0,
            macaulay_duration=0.0,
            convexity=0.0,
            dv01=0.0,
            asof_date=asof or date.today(),
        )

    if weights is None:
        w = 1.0 / len(bonds)
        weights = {b.internal_id: w for b in bonds}

    total_w = sum(float(weights.get(b.internal_id, 0.0)) for b in bonds) or 1.0
    reports = {b.internal_id: duration_report(b, asof=asof) for b in bonds}
    mod = (
        sum(
            float(weights.get(b.internal_id, 0.0)) * reports[b.internal_id].modified_duration
            for b in bonds
        )
        / total_w
    )
    mac = (
        sum(
            float(weights.get(b.internal_id, 0.0)) * reports[b.internal_id].macaulay_duration
            for b in bonds
        )
        / total_w
    )
    cvx = (
        sum(
            float(weights.get(b.internal_id, 0.0)) * reports[b.internal_id].convexity for b in bonds
        )
        / total_w
    )
    dv = (
        sum(float(weights.get(b.internal_id, 0.0)) * reports[b.internal_id].dv01 for b in bonds)
        / total_w
    )
    krds: dict[str, float] = {}
    for b in bonds:
        rep = reports[b.internal_id]
        w = float(weights.get(b.internal_id, 0.0)) / total_w
        for tenor, krd in rep.key_rate_durations.items():
            krds[tenor] = krds.get(tenor, 0.0) + w * krd

    return DurationReport(
        internal_id=None,
        modified_duration=round(mod, 4),
        macaulay_duration=round(mac, 4),
        convexity=round(cvx, 4),
        dv01=round(dv, 4),
        key_rate_durations={k: round(v, 4) for k, v in krds.items()},
        asof_date=asof or date.today(),
    )
