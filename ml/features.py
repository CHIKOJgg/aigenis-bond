"""Feature engineering: построение признаков из Bond + bond_history."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from statistics import fmean, pstdev

from ml.models import BondFeatures
from scoring.engine import score_bond

CURRENCY_IDX = {"USD": 0, "EUR": 1, "BYN": 2, "XAU": 3, "XAG": 4, "XPT": 5}


def _safe_float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except TypeError, ValueError:
        return 0.0


def _history_window(history: list[dict], asof: date, window: int) -> list[dict]:
    cutoff = asof - timedelta(days=window)
    return [h for h in history if h["date"] <= asof and h["date"] >= cutoff]


def _rolling_stats(history: list[dict], asof: date, window: int) -> tuple[float, float]:
    rows = _history_window(history, asof, window)
    yields = [_safe_float(r.get("yield")) for r in rows if r.get("yield") is not None]
    if not yields:
        return 0.0, 0.0
    return fmean(yields), pstdev(yields) if len(yields) > 1 else 0.0


def _momentum(history: list[dict], asof: date, window: int, key: str) -> float:
    rows = sorted(_history_window(history, asof, window), key=lambda r: r["date"])
    if len(rows) < 2:
        return 0.0
    first = _safe_float(rows[0].get(key))
    last = _safe_float(rows[-1].get(key))
    if first == 0:
        return 0.0
    return (last - first) / abs(first)


def _duration_years(maturity: date | None, ref: date) -> float:
    if maturity is None:
        return 0.0
    return max((maturity - ref).days / 365.25, 0.0)


def build_features(
    *,
    bond_dict: dict,
    history: list[dict] | None = None,
    asof: date | None = None,
    avg_yield_by_currency: dict[str, float] | None = None,
) -> BondFeatures:
    """Сформировать вектор признаков для одной облигации на дату asof."""
    asof = asof or date.today()
    history = history or []

    currency = str(bond_dict.get("currency", "USD")).upper()
    ytm = _safe_float(bond_dict.get("yield_to_maturity"))
    price = _safe_float(bond_dict.get("price"))
    coupon = _safe_float(bond_dict.get("coupon_rate"))
    maturity = bond_dict.get("maturity_date")
    if not isinstance(maturity, date):
        maturity = None
    issuer = (bond_dict.get("issuer") or "").lower()
    is_gov = int(
        any(
            k in issuer for k in ("министерство", "республика", "государ", "treasury", "government")
        )
    )
    is_active = int(str(bond_dict.get("status", "")).lower() == "active")

    avg_yield = (avg_yield_by_currency or {}).get(currency, 0.0)
    spread = ytm - avg_yield

    duration = _duration_years(maturity, asof)
    days_to_maturity = duration * 365.25

    mean30, std30 = _rolling_stats(history, asof, 30)
    yield_mom = _momentum(history, asof, 30, "yield")
    price_mom = _momentum(history, asof, 30, "price")

    score = score_bond(
        internal_id=str(bond_dict["internal_id"]),
        yield_to_maturity=ytm,
        currency=currency,
        maturity_date=maturity,
        status=str(bond_dict.get("status", "unknown")),
        issuer=bond_dict.get("issuer"),
        price=price if price else None,
    )

    return BondFeatures(
        internal_id=str(bond_dict["internal_id"]),
        asof_date=asof,
        currency_idx=CURRENCY_IDX.get(currency, 99),
        duration_years=round(duration, 4),
        days_to_maturity=round(days_to_maturity, 2),
        coupon_rate=coupon,
        price=price,
        yield_to_maturity=ytm,
        spread_to_avg=round(spread, 4),
        rolling_yield_mean_30d=round(mean30, 4),
        rolling_yield_std_30d=round(std30, 4),
        yield_momentum_30d=round(yield_mom, 4),
        price_momentum_30d=round(price_mom, 4),
        score=score.score,
        score_yield_component=score.breakdown.yield_component,
        score_currency_component=score.breakdown.currency_component,
        score_duration_component=score.breakdown.duration_component,
        score_metal_component=score.breakdown.metal_component,
        is_gov_issuer=is_gov,
        is_active=is_active,
    )


def build_dataset(
    bonds: list[dict],
    history_by_bond: dict[str, list[dict]],
    *,
    asof: date | None = None,
) -> list[BondFeatures]:
    """Собрать датасет фичей для всех облигаций."""
    asof = asof or date.today()

    avg_by_currency: dict[str, list[float]] = {}
    for b in bonds:
        cur = str(b.get("currency", "USD")).upper()
        y = _safe_float(b.get("yield_to_maturity"))
        avg_by_currency.setdefault(cur, []).append(y)
    avg = {k: (fmean(v) if v else 0.0) for k, v in avg_by_currency.items()}

    return [
        build_features(
            bond_dict=b,
            history=history_by_bond.get(b["internal_id"], []),
            asof=asof,
            avg_yield_by_currency=avg,
        )
        for b in bonds
    ]


def features_to_matrix(features: Iterable[BondFeatures]) -> tuple[list[list[float]], list[str]]:
    """Преобразовать список BondFeatures в матрицу X и список имён фичей."""
    feature_names = [
        "currency_idx",
        "duration_years",
        "days_to_maturity",
        "coupon_rate",
        "price",
        "yield_to_maturity",
        "spread_to_avg",
        "rolling_yield_mean_30d",
        "rolling_yield_std_30d",
        "yield_momentum_30d",
        "price_momentum_30d",
        "score",
        "score_yield_component",
        "score_currency_component",
        "score_duration_component",
        "score_metal_component",
        "is_gov_issuer",
        "is_active",
    ]
    matrix: list[list[float]] = []
    for f in features:
        matrix.append([getattr(f, name) for name in feature_names])
    return matrix, feature_names
