"""Data Quality Gate — проверка входных данных перед скорингом.

Каждая облигация проходит обязательную валидацию. Скоринг выполняется ТОЛЬКО
на проверенных данных. Если данные не прошли gate — облигация помечается
как UNRATED с указанием причины. Это гарантирует, что цифры скоринга
«никогда не врут».

Правила:
- Нет critical-ошибок → полный скоринг с разбором
- Есть warning → скоринг с пометкой о сниженной достоверности
- Есть critical → UNRATED, причина в ответе
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

Severity = Literal["ok", "warning", "critical"]

# Максимальный возраст данных (часов) для признания «свежими»
MAX_DATA_AGE_HOURS = 48

# Минимально допустимая цена относительно номинала (%)
MIN_PRICE_NOMINAL_RATIO_PCT = 1.0
MAX_PRICE_NOMINAL_RATIO_PCT = 500.0

# YTM bounds: за пределами — явная ошибка данных. Потолок согласован с
# портфельным eligibility-гейтом (scoring/eligibility.EXTREME_MAX_YTM_PCT = 100):
# бумага, слишком рискованная для включения в портфель (YTM > 100%), не должна ни
# скориться, ни показываться как жизнеспособная возможность. Для реального
# высокодоходного долга (фронтир) YTM редко превышает 40-60%, так что 100% —
# безопасный предел «явной ошибки / экстремального дистресса».
MIN_REALISTIC_YTM = -10.0
MAX_REALISTIC_YTM = 100.0

# Купон bounds
MAX_REALISTIC_COUPON = 100.0

# Максимальная дюрация (лет) — дальше ошибка
MAX_DURATION_YEARS = 100.0

# ISIN pattern
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")


@dataclass
class DataQualityResult:
    """Результат проверки качества данных облигации."""

    internal_id: str
    overall: Severity = "ok"
    issues: list[str] = field(default_factory=list)

    @property
    def is_rated(self) -> bool:
        """Можно ли скорить эту облигацию."""
        return self.overall != "critical"

    @property
    def confidence(self) -> str:
        if self.overall == "ok":
            return "high"
        if self.overall == "warning":
            return "medium"
        return "low"


def validate_bond_data(
    *,
    internal_id: str,
    yield_to_maturity: float | None,
    currency: str | None,
    maturity_date: date | None,
    status: str | None,
    issuer: str | None,  # noqa: ARG001 (reserved for future use)
    price: float | None,
    nominal: float | None,
    coupon_rate: float | None,
    fetched_at: datetime | None = None,
    isin: str | None = None,
) -> DataQualityResult:
    """Проверить данные облигации перед скорингом.

    Возвращает DataQualityResult с уровнем:
    - ok: все данные валидны, скоринг точен
    - warning: есть сомнительные данные, скоринг с оговоркой
    - critical: данные непригодны, скоринг невозможен
    """
    result = DataQualityResult(internal_id=internal_id)

    # 1. Проверка обязательных полей
    if not internal_id or not internal_id.strip():
        result.issues.append("MISSING_ID: отсутствует идентификатор")
        result.overall = "critical"
        return result

    if not currency or not currency.strip():
        result.issues.append("MISSING_CURRENCY: валюта не указана")
        result.overall = "critical"
        return result

    # 2. Проверка ISIN (если есть)
    if isin is not None and isin.strip() and not ISIN_RE.match(isin.strip()):
        result.issues.append(f"INVALID_ISIN: '{isin}' не соответствует формату")
        _downgrade(result, "warning")

    # 3. Проверка свежести данных
    if fetched_at is not None:
        age_hours = (datetime.now(fetched_at.tzinfo) - fetched_at).total_seconds() / 3600
        if age_hours > MAX_DATA_AGE_HOURS * 3:
            result.issues.append(
                f"STALE_DATA: данные старше {MAX_DATA_AGE_HOURS * 3}ч (возраст: {age_hours:.0f}ч)"
            )
            _downgrade(result, "warning")
        elif age_hours > MAX_DATA_AGE_HOURS:
            result.issues.append(
                f"DATA_AGE_WARN: данные старше {MAX_DATA_AGE_HOURS}ч (возраст: {age_hours:.0f}ч)"
            )
            _downgrade(result, "warning")

    # 4. Проверка YTM
    if yield_to_maturity is not None:
        if yield_to_maturity < MIN_REALISTIC_YTM:
            result.issues.append(f"YTM_TOO_LOW: {yield_to_maturity}% (мин: {MIN_REALISTIC_YTM}%)")
            _downgrade(result, "critical")
        elif yield_to_maturity > MAX_REALISTIC_YTM:
            result.issues.append(f"YTM_TOO_HIGH: {yield_to_maturity}% (макс: {MAX_REALISTIC_YTM}%)")
            _downgrade(result, "critical")
        elif yield_to_maturity > 100:
            result.issues.append(f"YTM_EXTREME: {yield_to_maturity}% — возможно, ошибка данных")
            _downgrade(result, "warning")
    else:
        result.issues.append("YTM_MISSING: доходность к погашению не указана")
        _downgrade(result, "warning")

    # 5. Проверка даты погашения
    if maturity_date is not None:
        if maturity_date < date.today() - timedelta(days=365):
            result.issues.append(f"MATURITY_PAST: дата погашения в прошлом ({maturity_date})")
            _downgrade(result, "warning")
        dur = (maturity_date - date.today()).days / 365.25
        if dur > MAX_DURATION_YEARS:
            result.issues.append(f"DURATION_EXCESSIVE: {dur:.0f} лет (макс: {MAX_DURATION_YEARS})")
            _downgrade(result, "critical")

    # 6. Проверка цены к номиналу
    if price is not None and nominal is not None and nominal > 0:
        ratio = price / nominal * 100
        if ratio < MIN_PRICE_NOMINAL_RATIO_PCT:
            result.issues.append(f"PRICE_TOO_LOW: {ratio:.1f}% от номинала")
            _downgrade(result, "warning")
        elif ratio > MAX_PRICE_NOMINAL_RATIO_PCT:
            result.issues.append(f"PRICE_TOO_HIGH: {ratio:.1f}% от номинала")
            _downgrade(result, "warning")

    # 7. Проверка купона
    if coupon_rate is not None:
        if coupon_rate < 0:
            result.issues.append(f"COUPON_NEGATIVE: {coupon_rate}%")
            _downgrade(result, "critical")
        elif coupon_rate > MAX_REALISTIC_COUPON:
            result.issues.append(
                f"COUPON_EXCESSIVE: {coupon_rate}% (макс: {MAX_REALISTIC_COUPON}%)"
            )
            _downgrade(result, "warning")

    # 8. Проверка статуса
    if status is not None:
        if status.lower() in {"defaulted", "bankrupt", "suspended"}:
            result.issues.append(f"STATUS_RISKY: {status}")
            _downgrade(result, "critical")
        elif status.lower() in {"delisted", "matured"}:
            result.issues.append(f"STATUS_INACTIVE: {status}")
            _downgrade(result, "warning")

    # 9. Проверка на дублирование/противоречия
    if price is not None and price <= 0:
        result.issues.append(f"PRICE_ZERO_OR_NEGATIVE: {price}")
        _downgrade(result, "warning")

    if nominal is not None and nominal <= 0:
        result.issues.append(f"NOMINAL_ZERO_OR_NEGATIVE: {nominal}")
        _downgrade(result, "critical")

    return result


def _downgrade(result: DataQualityResult, level: Severity) -> None:
    severity_order: dict[Severity, int] = {"ok": 0, "warning": 1, "critical": 2}
    if severity_order[level] > severity_order[result.overall]:
        result.overall = level


def score_bond_safe(
    *,
    internal_id: str,
    yield_to_maturity: float | None,
    currency: str,
    maturity_date: date | None,
    status: str = "unknown",
    issuer: str | None = None,
    price: float | None = None,
    nominal: float | None = None,
    coupon_rate: float | None = None,
    ref_date: date | None = None,
    fetched_at: datetime | None = None,
    isin: str | None = None,
) -> tuple[DataQualityResult, object | None]:  # BondScore | None
    """Безопасный скоринг с валидацией данных.

    Возвращает (DataQualityResult, BondScore | None).
    Если данные критически плохие — BondScore = None.
    """
    from scoring.engine import score_bond

    dq = validate_bond_data(
        internal_id=internal_id,
        yield_to_maturity=yield_to_maturity,
        currency=currency,
        maturity_date=maturity_date,
        status=status,
        issuer=issuer,
        price=price,
        nominal=nominal,
        coupon_rate=coupon_rate,
        fetched_at=fetched_at,
        isin=isin,
    )

    if not dq.is_rated:
        return dq, None

    bond_score = score_bond(
        internal_id=internal_id,
        yield_to_maturity=yield_to_maturity,
        currency=currency,
        maturity_date=maturity_date,
        status=status,
        issuer=issuer,
        price=price,
        nominal=nominal,
        coupon_rate=coupon_rate,
        ref_date=ref_date,
    )

    if dq.overall == "warning":
        discount = 0.85
        bond_score.score = round(bond_score.score * discount, 2)

    return dq, bond_score
