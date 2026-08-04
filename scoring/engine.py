"""Reward/Risk Score v4 — professional multi-factor scoring engine.

    score = yield + currency + duration + liquidity + metal + credit
          + inflation + coupon + volatility + hist_volatility + peer_relative

    Также вычисляет:
      reward_subtotal  — сумма всех положительных вкладов
      risk_subtotal    — сумма модулей отрицательных вкладов
      efficiency_ratio — reward / (1 + risk), Sharpe-подобный коэффициент
      risk_adjusted_score — efficiency_ratio × 100 (отдельный score)

    Калибровка выверена на 60+ реалистичных профилях (аудит 2026-08).
    Тиры: S≥85, A≥75, B≥60, C≥45, D<45.
"""

from __future__ import annotations

import math
import statistics
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
    if ytm_pct is None or ytm_pct <= 0:
        return 0.0
    if ytm_pct <= 40:
        return round(ytm_pct, 2)
    return round(40.0 + math.log(ytm_pct - 39.0) * 2, 2)


def _coupon_component(coupon_pct: float | None, ytm_pct: float | None) -> float:
    if coupon_pct is None:
        return 0.0
    cp = float(coupon_pct)
    if cp <= 0:
        return -3.0
    score = min(cp * 0.5, 6.0)
    if ytm_pct is not None and ytm_pct > 0 and cp > ytm_pct * 0.8:
        score += 1.0
    return round(score, 2)


def _historical_volatility_component(ytm_history: list[float] | None) -> float:
    """Стабильность YTM: бонус за низкую волатильность, штраф за высокую."""
    if not ytm_history or len(ytm_history) < 3:
        return 0.0
    clean = [y for y in ytm_history if y > 0]
    if len(clean) < 3:
        return 0.0
    try:
        stdev = float(statistics.stdev(clean))
    except statistics.StatisticsError:
        return 0.0
    if stdev < 0.5:
        return 5.0
    if stdev < 1.0:
        return 3.0
    if stdev < 2.0:
        return 1.0
    if stdev < 5.0:
        return 0.0
    if stdev < 10.0:
        return -2.0
    return -4.0


def _peer_relative_component(
    ytm_pct: float | None, currency: str, peer_ytms: list[float] | None
) -> float:
    """Сравнение с аналогами в той же валюте: z-score выше среднего = бонус."""
    if ytm_pct is None or ytm_pct <= 0:
        return 0.0
    if not peer_ytms or len(peer_ytms) < 5:
        return 0.0
    clean = [y for y in peer_ytms if y > 0]
    if len(clean) < 5:
        return 0.0
    try:
        avg = float(statistics.mean(clean))
        stdev = float(statistics.stdev(clean))
    except statistics.StatisticsError:
        return 0.0
    if stdev < 0.1:
        return 0.0
    z = (ytm_pct - avg) / stdev
    if z >= 2.0:
        return 5.0
    if z >= 1.0:
        return 3.0
    if z >= 0.0:
        return 1.0
    if z >= -1.0:
        return -1.0
    if z >= -2.0:
        return -3.0
    return -5.0


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
    if status == "delisted":
        return -28.0
    if status == "matured":
        return -12.0
    if status == "defaulted":
        return -35.0
    tier = _classify_issuer(issuer)
    return _CREDIT_TIERS.get(tier, -3.0)


def _inflation_component(currency: str, ytm_pct: float | None) -> float:
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


def _compute_efficiency_ratio(breakdown: ScoreBreakdown) -> float:
    """Sharpe-подобный коэффициент. reward/(reward+risk+1)*15 → диапазон 0-15."""
    reward = sum(max(v, 0.0) for v in [
        breakdown.yield_component, breakdown.currency_component,
        breakdown.duration_component, breakdown.liquidity_component,
        breakdown.metal_component, breakdown.credit_risk_component,
        breakdown.inflation_component, breakdown.coupon_component,
        breakdown.historical_volatility_component, breakdown.peer_relative_component,
    ])
    risk = sum(abs(min(v, 0.0)) for v in [
        breakdown.yield_component, breakdown.currency_component,
        breakdown.duration_component, breakdown.liquidity_component,
        breakdown.metal_component, breakdown.credit_risk_component,
        breakdown.inflation_component, breakdown.coupon_component,
        breakdown.volatility_component, breakdown.historical_volatility_component,
        breakdown.peer_relative_component,
    ])
    if reward < 0.5:
        return 0.0
    ratio = reward / (reward + risk + 1.0)
    return round(ratio * 15.0, 2)


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
    ytm_history: list[float] | None = None,
    peer_ytms: list[float] | None = None,
) -> BondScore:
    """Рассчитать Reward/Risk Score v4 для одной облигации.

    market='bcse' — белорусский рынок
    market='moex' — российский рынок
    ytm_history — история YTM для расчёта волатильности
    peer_ytms — YTM аналогов в той же валюте для z-score
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
            has_price=has_price, status=status, days_to_maturity=days_to_maturity,
            price=price_f, nominal=nominal_f,
        ),
        metal_component=_metal_component(currency),
        credit_risk_component=_credit_risk_component(issuer, status),
        inflation_component=_inflation_component_market(currency, ytm_pct, is_moex),
        coupon_component=_coupon_component(coupon_pct, ytm_pct),
        volatility_component=_volatility_component(
            ytm_pct=ytm_pct, price=price_f, nominal=nominal_f,
            status=status, coupon_pct=coupon_pct,
        ),
        historical_volatility_component=_historical_volatility_component(ytm_history),
        peer_relative_component=_peer_relative_component(ytm_pct, currency, peer_ytms),
    )

    reward_sum = sum(max(v, 0.0) for v in [
        breakdown.yield_component, breakdown.currency_component,
        breakdown.duration_component, breakdown.liquidity_component,
        breakdown.metal_component, breakdown.credit_risk_component,
        breakdown.inflation_component, breakdown.coupon_component,
        breakdown.historical_volatility_component, breakdown.peer_relative_component,
    ])
    risk_sum = sum(abs(min(v, 0.0)) for v in [
        breakdown.yield_component, breakdown.currency_component,
        breakdown.duration_component, breakdown.liquidity_component,
        breakdown.metal_component, breakdown.credit_risk_component,
        breakdown.inflation_component, breakdown.coupon_component,
        breakdown.volatility_component, breakdown.historical_volatility_component,
        breakdown.peer_relative_component,
    ])

    breakdown.reward_subtotal = round(reward_sum, 2)
    breakdown.risk_subtotal = round(risk_sum, 2)
    breakdown.efficiency_ratio = _compute_efficiency_ratio(breakdown)

    raw_score = round(breakdown.total(), 2)
    risk_adj = round(breakdown.efficiency_ratio * 6.0, 2)

    return BondScore(
        internal_id=internal_id,
        score=raw_score,
        risk_adjusted_score=risk_adj,
        breakdown=breakdown,
        computed_at=datetime.now(UTC),
    )


def score_bonds(bonds: list[dict[str, Any]], *, ref_date: date | None = None) -> list[BondScore]:
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
