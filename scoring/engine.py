"""Reward/Risk Score — формулы по ТЗ.

Базовый скоринг:

    score = yield_component
          + currency_component
          + duration_component
          + liquidity_component
          + metal_component
          + credit_risk_component
          + inflation_component

Все компоненты — аддитивные баллы. Итоговый Score — float.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from scoring.models import BondScore, ScoreBreakdown

CURRENCY_BONUS: dict[str, float] = {
    "USD": 25.0,
    "XAU": 20.0,
    "XAG": 15.0,
    "XPT": 12.0,
    "BYN": 5.0,
    "EUR": 0.0,
}


METAL_EXTRA_BONUS: dict[str, float] = {
    "XAU": 10.0,
    "XAG": 5.0,
    "XPT": 3.0,
}


def _duration_years(maturity: date | None, ref: date | None = None) -> float | None:
    if maturity is None:
        return None
    ref = ref or date.today()
    return max((maturity - ref).days / 365.25, 0.0)


def _duration_component(years: float | None) -> float:
    if years is None:
        return 0.0
    if years <= 2.0:
        return 20.0
    if years <= 4.0:
        return 10.0
    if years <= 6.0:
        return 0.0
    return -15.0


def _yield_component(ytm_pct: float | None) -> float:
    """Доходность: 1 балл за каждый полный процент YTM, ограничено 60."""
    if ytm_pct is None or ytm_pct <= 0:
        return 0.0
    return min(ytm_pct, 60.0)


def _currency_component(currency: str) -> float:
    return CURRENCY_BONUS.get(currency.upper(), 0.0)


def _metal_component(currency: str) -> float:
    return METAL_EXTRA_BONUS.get(currency.upper(), 0.0)


def _liquidity_component(
    *,
    has_price: bool,
    status: str,
    days_to_maturity: float | None,
) -> float:
    """Ликвидность: оцениваем наличие цены, активный статус, близость к погашению."""
    score = 0.0
    if has_price:
        score += 5.0
    if status == "active":
        score += 5.0
    elif status in {"offer", "matured"}:
        score -= 5.0
    if days_to_maturity is not None and days_to_maturity < 365:
        score += 2.0
    return score


def _credit_risk_component(issuer: str | None, status: str) -> float:
    """Кредитный риск: упрощённо по типу эмитента и статусу."""
    if status == "delisted":
        return -25.0
    if status == "matured":
        return -10.0
    if not issuer:
        return -3.0
    s = issuer.lower()
    if any(k in s for k in ("министерство", "республика", "государ", "treasury", "government")):
        return 10.0
    if "bank" in s or "банк" in s:
        return 0.0
    return -5.0


def _inflation_component(currency: str, ytm_pct: float | None) -> float:
    """Инфляционная корректировка: для BYN/EUR — штраф при низкой доходности."""
    if currency.upper() == "USD":
        return 5.0
    if currency.upper() == "BYN":
        if ytm_pct is None or ytm_pct < 8:
            return -5.0
        return 2.0
    if currency.upper() == "EUR":
        return -2.0
    return 0.0


def score_bond(
    *,
    internal_id: str,
    yield_to_maturity: Decimal | float | int | None,
    currency: str,
    maturity_date: date | None,
    status: str = "unknown",
    issuer: str | None = None,
    price: Decimal | float | int | None = None,
    ref_date: date | None = None,
) -> BondScore:
    """Рассчитать Reward/Risk Score для одной облигации."""
    ytm_pct = float(yield_to_maturity) if yield_to_maturity is not None else None
    duration = _duration_years(maturity_date, ref_date)
    has_price = price is not None
    days_to_maturity = duration * 365.25 if duration is not None else None

    breakdown = ScoreBreakdown(
        yield_component=_yield_component(ytm_pct),
        currency_component=_currency_component(currency),
        duration_component=_duration_component(duration),
        liquidity_component=_liquidity_component(
            has_price=has_price,
            status=status,
            days_to_maturity=days_to_maturity,
        ),
        metal_component=_metal_component(currency),
        credit_risk_component=_credit_risk_component(issuer, status),
        inflation_component=_inflation_component(currency, ytm_pct),
    )

    return BondScore(
        internal_id=internal_id,
        score=round(breakdown.total(), 2),
        breakdown=breakdown,
        computed_at=datetime.now(UTC),
    )


def score_bonds(bonds: list[dict[str, Any]], *, ref_date: date | None = None) -> list[BondScore]:
    """Балтийский список облигаций (dict-формат)."""
    return [
        score_bond(
            internal_id=str(b["internal_id"]),
            yield_to_maturity=b.get("yield_to_maturity"),
            currency=str(b.get("currency", "")),
            maturity_date=b.get("maturity_date"),
            status=str(b.get("status", "unknown")),
            issuer=b.get("issuer"),
            price=b.get("price"),
            ref_date=ref_date,
        )
        for b in bonds
    ]
