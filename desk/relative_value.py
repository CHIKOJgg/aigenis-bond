"""Relative Value: z-score спредов внутри валюты, rich/cheap сигналы."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from statistics import fmean, pstdev

from desk.cashflow import accrued_interest
from desk.models import RVSignal, YieldCurve


def _bucket_by_tenor(years_to_maturity: float) -> str:
    if years_to_maturity <= 1:
        return "short"
    if years_to_maturity <= 5:
        return "mid"
    return "long"


def _bucket_zscore(ytm_pcts: list[float], value: float) -> tuple[float, float]:
    if len(ytm_pcts) < 3:
        return 0.0, value
    avg = fmean(ytm_pcts)
    sd = pstdev(ytm_pcts) or 1e-6
    return avg, (value - avg) / sd


def relative_value_signals(
    bonds: Iterable,
    *,
    asof: date | None = None,
    z_threshold: float = 1.0,
) -> list[RVSignal]:
    """Сгенерировать rich/cheap сигналы внутри валюты по tenor-бакетам."""
    asof = asof or date.today()
    groups: dict[tuple[str, str], list[dict]] = {}
    today = asof

    for b in bonds:
        if b.yield_to_maturity is None or b.maturity_date is None:
            continue
        years = max((b.maturity_date - today).days / 365.25, 0.0)
        if years <= 0:
            continue
        key = (str(b.currency), _bucket_by_tenor(years))
        groups.setdefault(key, []).append({
            "id": b.internal_id,
            "name": getattr(b, "name", None) or b.internal_id,
            "issuer": getattr(b, "issuer", None),
            "isin": getattr(b, "isin", None),
            "price": float(b.price) if getattr(b, "price", None) is not None else None,
            "nominal": float(b.nominal) if getattr(b, "nominal", None) is not None else 1000.0,
            "ytm": float(b.yield_to_maturity),
            "accrued_interest": round(
                accrued_interest(
                    coupon_rate_pct=float(b.coupon_rate) if getattr(b, "coupon_rate", None) is not None else 0.0,
                    coupon_frequency=int(b.coupon_frequency) if getattr(b, "coupon_frequency", None) is not None else 2,
                    issue_date=getattr(b, "start_date", None) or getattr(b, "issue_date", None),
                    maturity_date=b.maturity_date,
                    asof=today,
                    face=float(b.nominal) if getattr(b, "nominal", None) is not None else 100.0,
                ),
                2,
            ),
        })

    signals: list[RVSignal] = []
    for (currency, _tenor_bucket), items in groups.items():
        if len(items) < 3:
            continue
        ytm_values = [item["ytm"] for item in items]
        fair_avg, _ = _bucket_zscore(ytm_values, fmean(ytm_values))
        sd = pstdev(ytm_values) or 1e-6
        for item in items:
            value = item["ytm"]
            z = (value - fair_avg) / sd
            spread = value - fair_avg
            if z >= z_threshold:
                side = "buy"
                rationale = (
                    f"Дешевле аналогов на {abs(spread):.1f}% (Z={z:+.2f}). "
                    f"Привлекательная доходность {value:.1f}% при справедливом уровне {fair_avg:.1f}%."
                )
            elif z <= -z_threshold:
                side = "sell"
                rationale = (
                    f"Переоценена на {abs(spread):.1f}% относительно рынка (Z={z:+.2f}). "
                    f"Доходность {value:.1f}% ниже средней {fair_avg:.1f}% — рекомендуется фиксация."
                )
            else:
                side = "hold"
                rationale = f"Цена соответствует справедливой рыночной оценке (Z={z:+.2f})."

            signals.append(
                RVSignal(
                    internal_id=item["id"],
                    name=item["name"],
                    issuer=item["issuer"],
                    isin=item["isin"],
                    price=item["price"],
                    nominal=item["nominal"],
                    accrued_interest=item["accrued_interest"],
                    peer_currency=currency,
                    peer_set=[j["id"] for j in items if j["id"] != item["id"]],
                    z_score=round(z, 4),
                    spread_pct=round(spread, 4),
                    fair_spread_pct=round(fair_avg, 4),
                    side=side,
                    rationale=rationale,
                    asof_date=asof,
                )
            )

    signals.sort(key=lambda s: abs(s.z_score), reverse=True)
    return signals


def signals_from_curve(curve: YieldCurve, *, asof: date | None = None) -> list[RVSignal]:
    """Relative value сигналы против самой кривой (model price vs market)."""
    asof = asof or date.today()
    if len(curve.points) < 3:
        return []
    avg_yield = fmean(p.rate_pct for p in curve.points)
    sd_yield = pstdev(p.rate_pct for p in curve.points) or 1e-6
    signals: list[RVSignal] = []
    for p in curve.points:
        z = (p.rate_pct - avg_yield) / sd_yield
        # Higher rate than the curve average => cheap => buy; lower => rich => sell.
        side = "buy" if z >= 1 else ("sell" if z <= -1 else "hold")
        signals.append(
            RVSignal(
                internal_id=f"{curve.currency}-{p.tenor}",
                peer_currency=curve.currency,
                z_score=round(z, 4),
                spread_pct=round(p.rate_pct - avg_yield, 4),
                fair_spread_pct=round(avg_yield, 4),
                side=side,
                rationale=f"{p.tenor} {p.rate_pct:.2f}% vs curve avg {avg_yield:.2f}% (Z={z:+.2f})",
                asof_date=asof,
            )
        )
    return signals
