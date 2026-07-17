"""Feature engineering: построение признаков из Bond + bond_history."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
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
    except (TypeError, ValueError):
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


# --------------------------------------------------------------------------- #
# Leakage-free supervised training samples
# --------------------------------------------------------------------------- #
# The old training target was a linear function of the input features
# (``y = ytm + spread*0.3 + score*0.02``), which the model could trivially learn
# — R² looked great but the forecast was meaningless. Instead we build genuine
# (features_as_of_t, realized_ytm_at_t+horizon) pairs from ``bond_history`` so
# the target comes from the *future*, not from the current feature vector.


@dataclass(frozen=True)
class TrainingSample:
    """One supervised example: features observed at ``asof`` and the realized
    outcome ``horizon_days`` later."""

    features: BondFeatures
    asof: date
    future_ytm: float
    future_return_pct: float  # future_ytm - current_ytm (realized YTM move)


def _nearest_future_row(
    history: list[dict], target_day: date, tolerance_days: int
) -> dict | None:
    """Return the history row closest to ``target_day`` (on/after preferred),
    within ``tolerance_days``; ``None`` if no row is close enough."""
    best: dict | None = None
    best_gap = tolerance_days + 1
    for r in history:
        d = r.get("date")
        if d is None:
            continue
        gap = abs((d - target_day).days)
        if gap <= tolerance_days and gap < best_gap:
            best, best_gap = r, gap
    return best


def build_training_samples(
    bonds: list[dict],
    history_by_bond: dict[str, list[dict]],
    *,
    horizon_days: int = 90,
    tolerance_days: int = 20,
    step_days: int = 30,
    min_history_span_days: int = 60,
) -> list[TrainingSample]:
    """Build leakage-free (features, future_ytm) samples.

    For every bond we slide an ``asof`` cursor across its history and, for each
    position, compute the feature vector using only data up to ``asof`` and pair
    it with the actual YTM observed ~``horizon_days`` later. The current YTM is
    never used as the label; the label is a genuine future observation.
    """
    avg_by_currency: dict[str, list[float]] = {}
    for b in bonds:
        cur = str(b.get("currency", "USD")).upper()
        avg_by_currency.setdefault(cur, []).append(_safe_float(b.get("yield_to_maturity")))
    avg = {k: (fmean(v) if v else 0.0) for k, v in avg_by_currency.items()}

    samples: list[TrainingSample] = []
    for b in bonds:
        iid = b.get("internal_id")
        if iid is None:
            continue
        hist = sorted(
            (h for h in history_by_bond.get(iid, []) if h.get("date") is not None),
            key=lambda r: r["date"],
        )
        if len(hist) < 2:
            continue
        span = (hist[-1]["date"] - hist[0]["date"]).days
        if span < min_history_span_days:
            continue

        # Slide the as-of cursor; leave room for the horizon at the end.
        cursor = hist[0]["date"] + timedelta(days=step_days)
        last_valid_asof = hist[-1]["date"] - timedelta(days=horizon_days)
        while cursor <= last_valid_asof:
            # Snapshot of the bond as observed at `cursor`.
            asof_row = _nearest_future_row(hist, cursor, tolerance_days)
            future_row = _nearest_future_row(
                hist, cursor + timedelta(days=horizon_days), tolerance_days
            )
            if (
                asof_row is not None
                and future_row is not None
                and asof_row.get("yield") is not None
                and future_row.get("yield") is not None
            ):
                current_ytm = _safe_float(asof_row.get("yield"))
                future_ytm = _safe_float(future_row.get("yield"))
                snapshot = dict(b)
                # Use the historical observation, not today's live values.
                snapshot["yield_to_maturity"] = current_ytm
                if asof_row.get("price") is not None:
                    snapshot["price"] = _safe_float(asof_row.get("price"))
                feats = build_features(
                    bond_dict=snapshot,
                    history=hist,
                    asof=cursor,
                    avg_yield_by_currency=avg,
                )
                samples.append(
                    TrainingSample(
                        features=feats,
                        asof=cursor,
                        future_ytm=round(future_ytm, 6),
                        future_return_pct=round(future_ytm - current_ytm, 6),
                    )
                )
            cursor += timedelta(days=step_days)

    return samples
