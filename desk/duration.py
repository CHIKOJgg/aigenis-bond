"""Duration engine: Macaulay/Modified duration, convexity, DV01, key-rate."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from desk.models import DurationReport
from scraper.models import Bond


def _cashflows(
    *,
    nominal: Decimal,
    coupon_rate_pct: float,
    coupon_frequency: int,
    maturity: date,
    ref: date,
) -> list[tuple[float, float]]:
    """Дисконтированные/недисконтированные денежные потоки (год, CF)."""
    if maturity <= ref:
        return []
    cf_per_period = float(nominal) * coupon_rate_pct / 100 / coupon_frequency
    years_total = (maturity - ref).days / 365.25
    n_periods = max(int(round(years_total * coupon_frequency)), 1)
    period_years = years_total / n_periods
    flows: list[tuple[float, float]] = []
    for k in range(1, n_periods + 1):
        cf = cf_per_period
        if k == n_periods:
            cf += float(nominal)
        flows.append((period_years * k, cf))
    return flows


def _price_from_yield(flows: list[tuple[float, float]], ytm_pct: float, freq: int = 2) -> float:
    y = ytm_pct / 100
    return sum(cf / ((1 + y / freq) ** (freq * t)) for t, cf in flows)


def _price_shift(flows: list[tuple[float, float]], ytm_pct: float, shift_bps: float, freq: int = 2) -> float:
    return _price_from_yield(flows, ytm_pct + shift_bps / 100, freq=freq)


def macaulay_duration(
    *,
    nominal: Decimal,
    coupon_rate_pct: float,
    coupon_frequency: int,
    ytm_pct: float,
    maturity: date,
    ref: date,
) -> float:
    flows = _cashflows(
        nominal=nominal,
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        maturity=maturity,
        ref=ref,
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
) -> float:
    mac = macaulay_duration(
        nominal=nominal,
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        ytm_pct=ytm_pct,
        maturity=maturity,
        ref=ref,
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
) -> float:
    flows = _cashflows(
        nominal=nominal,
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        maturity=maturity,
        ref=ref,
    )
    if not flows:
        return 0.0
    price = _price_from_yield(flows, ytm_pct, freq=coupon_frequency)
    freq = coupon_frequency
    y_per = ytm_pct / 100 / freq
    cvx = sum(
        cf * t * (t + 1 / freq) / ((1 + y_per) ** (freq * t + 2))
        for t, cf in flows
    )
    return cvx / price


def dv01(
    *,
    nominal: Decimal,
    coupon_rate_pct: float,
    coupon_frequency: int,
    ytm_pct: float,
    maturity: date,
    ref: date,
) -> float:
    """Dollar Value of 1bp: убыток стоимости при росте YTM на 1bp."""
    flows = _cashflows(
        nominal=nominal,
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        maturity=maturity,
        ref=ref,
    )
    if not flows:
        return 0.0
    p_up = _price_shift(flows, ytm_pct, 1, freq=coupon_frequency)
    p_now = _price_from_yield(flows, ytm_pct, freq=coupon_frequency)
    return float(nominal) * (p_now - p_up) / 100


def key_rate_durations(
    *,
    nominal: Decimal,
    coupon_rate_pct: float,
    coupon_frequency: int,
    ytm_pct: float,
    maturity: date,
    ref: date,
    tenors: Iterable[float] = (0.25, 1, 2, 3, 5, 7, 10, 20, 30),
) -> dict[str, float]:
    flows = _cashflows(
        nominal=nominal,
        coupon_rate_pct=coupon_rate_pct,
        coupon_frequency=coupon_frequency,
        maturity=maturity,
        ref=ref,
    )
    if not flows:
        return {f"{int(t)}Y": 0.0 for t in tenors}
    freq = coupon_frequency
    base_price = _price_from_yield(flows, ytm_pct, freq=freq)
    out: dict[str, float] = {}
    for t in tenors:
        bumped: list[tuple[float, float]] = []
        for time, cf in flows:
            if abs(time - t) < 0.5:
                bump = 0.0001
            else:
                bump = 0.0
            bumped.append((time, cf / ((1 + (ytm_pct / 100 + bump) / freq) ** (freq * time))))
        bumped_price = sum(cf for _, cf in bumped)
        krd = -(bumped_price - base_price) / (base_price * 0.0001) if base_price else 0.0
        out[f"{int(t)}Y" if t >= 1 else f"{int(t*12)}M"] = round(krd, 4)
    return out


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
    coupon_pct = float(bond.coupon_rate or 0.0)
    freq = int(bond.coupon_frequency or 2)

    mac = macaulay_duration(
        nominal=nominal,
        coupon_rate_pct=coupon_pct,
        coupon_frequency=freq,
        ytm_pct=ytm,
        maturity=bond.maturity_date,
        ref=ref,
    )
    mod = mac / (1 + ytm / 100 / freq)
    cvx = convexity(
        nominal=nominal,
        coupon_rate_pct=coupon_pct,
        coupon_frequency=freq,
        ytm_pct=ytm,
        maturity=bond.maturity_date,
        ref=ref,
    )
    dv = dv01(
        nominal=nominal,
        coupon_rate_pct=coupon_pct,
        coupon_frequency=freq,
        ytm_pct=ytm,
        maturity=bond.maturity_date,
        ref=ref,
    )
    krd = key_rate_durations(
        nominal=nominal,
        coupon_rate_pct=coupon_pct,
        coupon_frequency=freq,
        ytm_pct=ytm,
        maturity=bond.maturity_date,
        ref=ref,
    )

    return DurationReport(
        internal_id=bond.internal_id,
        modified_duration=round(mod, 4),
        macaulay_duration=round(mac, 4),
        convexity=round(cvx, 4),
        dv01=round(dv, 4),
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
        return DurationReport(modified_duration=0.0, macaulay_duration=0.0, convexity=0.0, dv01=0.0, asof_date=asof or date.today())

    if weights is None:
        w = 1.0 / len(bonds)
        weights = {b.internal_id: w for b in bonds}

    total_w = sum(weights.get(b.internal_id, 0.0) for b in bonds) or 1.0
    reports = {b.internal_id: duration_report(b, asof=asof) for b in bonds}
    mod = sum(
        weights.get(b.internal_id, 0.0) * reports[b.internal_id].modified_duration
        for b in bonds
    ) / total_w
    mac = sum(
        weights.get(b.internal_id, 0.0) * reports[b.internal_id].macaulay_duration
        for b in bonds
    ) / total_w
    cvx = sum(
        weights.get(b.internal_id, 0.0) * reports[b.internal_id].convexity
        for b in bonds
    ) / total_w
    dv = sum(
        weights.get(b.internal_id, 0.0) * reports[b.internal_id].dv01
        for b in bonds
    ) / total_w
    krds: dict[str, float] = {}
    for b in bonds:
        rep = reports[b.internal_id]
        w = weights.get(b.internal_id, 0.0) / total_w
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
