"""Reward/Risk Score v3 — recalibrated multi-factor scoring engine.

    score = yield_component
          + currency_component
          + duration_component
          + liquidity_component
          + metal_component
          + credit_risk_component
          + inflation_component
          + coupon_component
          + volatility_component

Калибровка выверена на 60+ реалистичных профилях облигаций (аудит 2026-08).
Тиры: S≥85, A≥75, B≥60, C≥45, D<45.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from scoring.models import BondScore, ScoreBreakdown

CURRENCY_BONUS: dict[str, float] = {
    "USD": 20.0,
    "XAU": 16.0,
    "XAG": 12.0,
    "XPT": 9.0,
    "BYN": 6.0,
    "RUB": 4.0,
    "CNY": 4.0,
    "EUR": 0.0,
}

METAL_EXTRA_BONUS: dict[str, float] = {
    "XAU": 5.0,
    "XAG": 4.0,
    "XPT": 3.0,
}


def _duration_years(maturity: date | None, ref: date | None = None) -> float | None:
    if maturity is None:
        return None
    ref = ref or date.today()
    return max((maturity - ref).days / 365.25, 0.0)


def _duration_component(years: float | None) -> float:
    """Сглаженная дюрация: пологая сигмоида. Штраф только за >8 лет."""
    if years is None:
        return 0.0
    if years <= 0.5:
        return 8.0
    midpoint = 8.0
    steep = 0.4
    max_bonus = 8.0
    min_bonus = -4.0
    span = max_bonus - min_bonus
    raw = max_bonus - span / (1 + math.exp(-steep * (years - midpoint)))
    return round(raw, 2)


def _yield_component(ytm_pct: float | None) -> float:
    """Доходность: 1 балл за каждый процент YTM, cap 40, плавный рост выше."""
    if ytm_pct is None or ytm_pct <= 0:
        return 0.0
    if ytm_pct <= 40:
        return round(ytm_pct, 2)
    return round(40.0 + math.log(ytm_pct - 39.0) * 2, 2)


def _coupon_component(coupon_pct: float | None, ytm_pct: float | None) -> float:
    """Оценка стабильности купонного дохода."""
    if coupon_pct is None:
        return 0.0
    cp = float(coupon_pct)
    if cp <= 0:
        return -3.0
    score = min(cp * 0.5, 6.0)
    if ytm_pct is not None and ytm_pct > 0 and cp > ytm_pct * 0.8:
        score += 1.0
    return round(score, 2)


def _currency_component(currency: str) -> float:
    return CURRENCY_BONUS.get(currency.upper(), 0.0)


def _metal_component(currency: str) -> float:
    return METAL_EXTRA_BONUS.get(currency.upper(), 0.0)


def _liquidity_component(
    *,
    has_price: bool,
    status: str,
    days_to_maturity: float | None,
    price: float | None = None,
    nominal: float | None = None,
) -> float:
    """Расширенная оценка ликвидности."""
    score = 0.0
    if has_price:
        score += 5.0
        if price is not None and nominal is not None and nominal > 0:
            price_pct = price / nominal * 100
            if 85 <= price_pct <= 115:
                score += 2.0
    if status == "active":
        score += 4.0
    elif status in {"offer", "matured"}:
        score -= 5.0
    if days_to_maturity is not None and days_to_maturity < 365:
        score += 3.0
    if days_to_maturity is not None and days_to_maturity < 180:
        score += 2.0
    return score


_CREDIT_TIERS: dict[str, float] = {
    "sovereign": 12.0,
    "sub_sovereign": 8.0,
    "state_corp": 6.0,
    "bank_systemic": 3.0,
    "bank": 0.0,
    "corp_large": -2.0,
    "corp": -3.0,
    "unknown": -2.0,
}


_GOV_KEYWORDS = {
    "министерство", "республика", "государ", "treasury", "government",
    "минфин", "евразэс", "евразийск", "еабр", "счётная", "счетная",
    "правительство", "казначейство", "муниципальн", "субъект",
    "republic", "sovereign", "central bank", "centrobank",
}
_BANK_KEYWORDS = {"bank", "банк", "сбер", "втб", "вэб", "газпромбанк", "альфа"}
_STATE_CORP_KEYWORDS = {
    "газпром", "роснефть", "росатом", "роскосмос", "русгидро",
    "транснефть", "ржд", "аэрофлот", "почта", "связь",
    "лукойл", "сургут", "татнефть",
}
_SYSTEMIC_BANKS = {"сбер", "втб", "газпромбанк", "альфа-банк", "вэб"}


def _classify_issuer(issuer: str | None) -> str:
    if not issuer:
        return "unknown"
    s = issuer.lower().strip()
    for kw in _GOV_KEYWORDS:
        if kw in s:
            return "sovereign"
    for kw in _SYSTEMIC_BANKS:
        if kw in s:
            return "bank_systemic"
    for kw in _BANK_KEYWORDS:
        if kw in s:
            return "bank"
    for kw in _STATE_CORP_KEYWORDS:
        if kw in s:
            return "state_corp"
    if any(k in s for k in ("федеральн", "государствен")):
        return "sub_sovereign"
    return "corp"


def _credit_risk_component(issuer: str | None, status: str) -> float:
    """Расширенная классификация эмитентов с трехуровневой детализацией."""
    if status == "delisted":
        return -28.0
    if status == "matured":
        return -12.0
    if status == "defaulted":
        return -35.0
    tier = _classify_issuer(issuer)
    return _CREDIT_TIERS.get(tier, -3.0)


def _inflation_component(currency: str, ytm_pct: float | None) -> float:
    """Градуированная инфляционная корректировка."""
    cur = currency.upper()
    if cur == "USD":
        if ytm_pct is not None and ytm_pct >= 10:
            return 6.0
        if ytm_pct is not None and ytm_pct >= 5:
            return 4.0
        return 3.0
    if cur == "BYN":
        if ytm_pct is None:
            return -7.0
        if ytm_pct >= 12:
            return 4.0
        if ytm_pct >= 8:
            return 1.0
        if ytm_pct >= 5:
            return -3.0
        return -7.0
    if cur == "EUR":
        if ytm_pct is not None and ytm_pct >= 5:
            return 1.0
        return -2.0
    if cur == "RUB":
        if ytm_pct is not None and ytm_pct >= 16:
            return 4.0
        if ytm_pct is not None and ytm_pct >= 12:
            return 2.0
        return -1.0
    if cur == "CNY":
        if ytm_pct is not None and ytm_pct >= 6:
            return 2.0
        return 0.0
    return 0.0


def _volatility_component(
    *,
    ytm_pct: float | None,
    price: float | None,
    nominal: float | None,
    status: str,
    coupon_pct: float | None,
) -> float:
    """Оценка рискованности: штраф за экстремальные параметры."""
    score = 0.0
    if ytm_pct is not None:
        if ytm_pct > 60:
            score -= 7.0
        elif ytm_pct > 35:
            score -= 3.0
    if price is not None and nominal is not None and nominal > 0:
        pct = price / nominal * 100
        if pct < 30 or pct > 200:
            score -= 4.0
        elif pct < 50 or pct > 150:
            score -= 1.0
    if status in {"delisted", "defaulted", "suspended"}:
        score -= 5.0
    if coupon_pct is not None and coupon_pct <= 0 and ytm_pct is not None:
        if ytm_pct < 3:
            score -= 2.0
    return score

def _inflation_component_market(currency: str, ytm_pct: float | None, is_moex: bool) -> float:
    """Инфляционная корректировка с учётом рынка."""
    cur = currency.upper()
    if is_moex:
        if cur == "RUB":
            if ytm_pct is not None and ytm_pct >= 18:
                return 5.0
            if ytm_pct is not None and ytm_pct >= 14:
                return 3.0
            if ytm_pct is not None and ytm_pct >= 10:
                return 0.0
            return -2.0
        if cur == "BYN":
            if ytm_pct is not None and ytm_pct >= 10:
                return 2.0
            return -1.0
    else:
        if cur == "BYN":
            if ytm_pct is None:
                return -5.0
            if ytm_pct >= 12:
                return 5.0
            if ytm_pct >= 8:
                return 2.0
            if ytm_pct >= 5:
                return -1.0
            return -5.0
    return _inflation_component(currency, ytm_pct)


def score_bond(
    *,
    internal_id: str,
    yield_to_maturity: Decimal | float | int | None,
    currency: str,
    maturity_date: date | None,
    status: str = "unknown",
    issuer: str | None = None,
    price: Decimal | float | int | None = None,
    nominal: Decimal | float | int | None = None,
    coupon_rate: Decimal | float | int | None = None,
    ref_date: date | None = None,
    market: str = "bcse",
) -> BondScore:
    """Рассчитать Reward/Risk Score v3 для одной облигации.

    market='bcse' — белорусский рынок (BYN-центричная калибровка)
    market='moex' — российский рынок (RUB/ОФЗ-центричная калибровка)
    """
    ytm_pct = float(yield_to_maturity) if yield_to_maturity is not None else None
    coupon_pct = float(coupon_rate) if coupon_rate is not None else None
    price_f = float(price) if price is not None else None
    nominal_f = float(nominal) if nominal is not None else None
    duration = _duration_years(maturity_date, ref_date)
    has_price = price is not None
    days_to_maturity = duration * 365.25 if duration is not None else None

    is_moex = (market == "moex")

    breakdown = ScoreBreakdown(
        yield_component=_yield_component(ytm_pct),
        currency_component=_currency_component(currency),
        duration_component=_duration_component(duration),
        liquidity_component=_liquidity_component(
            has_price=has_price,
            status=status,
            days_to_maturity=days_to_maturity,
            price=price_f,
            nominal=nominal_f,
        ),
        metal_component=_metal_component(currency),
        credit_risk_component=_credit_risk_component(issuer, status),
        inflation_component=_inflation_component_market(currency, ytm_pct, is_moex),
        coupon_component=_coupon_component(coupon_pct, ytm_pct),
        volatility_component=_volatility_component(
            ytm_pct=ytm_pct,
            price=price_f,
            nominal=nominal_f,
            status=status,
            coupon_pct=coupon_pct,
        ),
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
            nominal=b.get("nominal"),
            coupon_rate=b.get("coupon_rate"),
            ref_date=ref_date,
        )
        for b in bonds
    ]
