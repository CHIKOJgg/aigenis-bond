"""Portfolio Eligibility Gate — жёсткие исключения бумаг из портфеля.

Три класса бумаг не могут попасть в портфель ни при какой стратегии:

1. DISTRIBUTION — «Дистрибуция / высокая вероятность дефолта»:
   цена < 80% номинала И YTM > 30%. Рынок закладывает дефолт: заявленная
   «доходность» — это риск, а не возможность.

2. EXTREME_RISK — сверхвысокорисковые активы:
   - YTM > 100% (аномалия данных источника или экстремальный дистресс,
     например 1545% у «Сбер CIB-CO-621», 800% у «ВТБ С-1-518»);
   - цена < 30% номинала (критический дисконт, рынок уже списал бумагу).

3. ANOMALY — аномалия относительно аналогов: YTM отклоняется от медианы
   YTM бумаг той же валюты более чем на ANOMALY_Z_SIGMA робастных сигм
   (MAD). Ловит «обычные» бумаги, у которых источник прислал ошибочную
   доходность (например 57.6% у обычной корпоративной облигации при
   аналогах 4-15%) — такие выстрелы ломают кривую доходности,
   оптимизацию и графики.

Проверка только односторонняя (вверх): низкая доходность не является
аномалией для портфеля — суверенные бумаги легитимно ниже корпоративных.

Модуль используется во всех точках входа в портфель: оптимизатор,
рекомендации, демо-API и список лучших бумаг (opportunity list).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

# 1. Дистрибуция: цена < 80% номинала при YTM > 30%
DISTRIBUTION_MAX_PRICE_PCT = 80.0
DISTRIBUTION_MIN_YTM_PCT = 30.0

# 2. Сверхвысокорисковые: YTM > 100% или цена < 30% номинала
EXTREME_MAX_YTM_PCT = 100.0
EXTREME_MIN_PRICE_PCT = 30.0

# 3. Аномалия: z > ANOMALY_Z_SIGMA при минимуме аналогов ANOMALY_MIN_PEERS
ANOMALY_Z_SIGMA = 4.0
ANOMALY_MIN_PEERS = 5

EXCLUDED_STATUSES = frozenset({"defaulted", "bankrupt", "suspended", "delisted", "matured"})


@dataclass(frozen=True)
class EligibilityResult:
    """Результат проверки пригодности бумаги для портфеля."""

    internal_id: str
    eligible: bool
    reason: str | None = None
    kind: str | None = None  # "status" | "distribution" | "extreme_risk" | "anomaly"


def _robust_anomaly_z(ytm_pct: float, peers: list[float]) -> float | None:
    """Робастный z-score: (ytm - медиана) / (1.4826 * MAD).

    Устойчив к выбросам в самих аналогах: одна бумага на 1545% не раздувает
    разброс, и 57.6% «обычной» облигации всё равно даст z >> 4.
    """
    if len(peers) < ANOMALY_MIN_PEERS:
        return None
    med = float(statistics.median(peers))
    mad = float(statistics.median([abs(p - med) for p in peers]))
    if mad > 0:
        spread = 1.4826 * mad
    else:
        if len(peers) < 2:
            return None
        spread = float(statistics.stdev(peers))
        if spread <= 0:
            return None
    return (ytm_pct - med) / spread


def check_eligibility(
    *,
    internal_id: str,
    price_pct: float | None = None,
    ytm_pct: float | None = None,
    status: str | None = None,
    peer_ytms: list[float] | None = None,
) -> EligibilityResult:
    """Проверить одну бумагу по всем правилам eligibility gate.

    ``price_pct`` — цена в процентах от номинала (100 = паритет).
    ``peer_ytms`` — YTM аналогов в той же валюте для детекции аномалий.
    """
    status_l = (status or "").strip().lower()
    if status_l in EXCLUDED_STATUSES:
        return EligibilityResult(
            internal_id=internal_id,
            eligible=False,
            kind="status",
            reason=f"Статус '{status}' — бумага не допускается в портфель",
        )

    # No usable market data: a bond with neither a price nor a yield cannot be
    # priced, yield-assessed or allocated. Keep it out of the portfolio instead
    # of letting it be scored/allocated on a phantom signal.
    if price_pct is None and ytm_pct is None:
        return EligibilityResult(
            internal_id=internal_id,
            eligible=False,
            kind="no_data",
            reason="Нет рыночных данных (ни цены, ни доходности) — бумага не может быть оценена",
        )

    if (
        price_pct is not None
        and ytm_pct is not None
        and price_pct < DISTRIBUTION_MAX_PRICE_PCT
        and ytm_pct > DISTRIBUTION_MIN_YTM_PCT
    ):
        return EligibilityResult(
            internal_id=internal_id,
            eligible=False,
            kind="distribution",
            reason=(
                "Дистрибуция / высокая вероятность дефолта: "
                f"цена {price_pct:.1f}% от номинала при YTM {ytm_pct:.1f}%"
            ),
        )

    if ytm_pct is not None and ytm_pct > EXTREME_MAX_YTM_PCT:
        return EligibilityResult(
            internal_id=internal_id,
            eligible=False,
            kind="extreme_risk",
            reason=f"Сверхвысокорисковый актив: YTM {ytm_pct:.1f}% (аномалия данных или дистресс)",
        )

    if price_pct is not None and price_pct < EXTREME_MIN_PRICE_PCT:
        return EligibilityResult(
            internal_id=internal_id,
            eligible=False,
            kind="extreme_risk",
            reason=f"Цена {price_pct:.1f}% от номинала — сверхвысокий риск",
        )

    if ytm_pct is not None and peer_ytms:
        z = _robust_anomaly_z(ytm_pct, peer_ytms)
        if z is not None and z > ANOMALY_Z_SIGMA:
            return EligibilityResult(
                internal_id=internal_id,
                eligible=False,
                kind="anomaly",
                reason=(
                    f"Аномалия доходности: YTM {ytm_pct:.1f}% на {z:.1f} "
                    f"сигм выше аналогов в валюте"
                ),
            )

    return EligibilityResult(internal_id=internal_id, eligible=True)


def _field(bond: Any, name: str) -> Any:
    """Достать поле из dict или объекта (ORM / Pydantic)."""
    if isinstance(bond, dict):
        return bond.get(name)
    return getattr(bond, name, None)


def peer_ytms_by_currency(bonds: list[Any]) -> dict[str, list[float]]:
    """Группировать положительные YTM по валюте для детекции аномалий."""
    out: dict[str, list[float]] = {}
    for b in bonds:
        ytm = _field(b, "yield_to_maturity")
        currency = str(_field(b, "currency") or "").upper()
        if not currency or ytm is None:
            continue
        try:
            y = float(ytm)
        except (TypeError, ValueError):
            continue
        if y > 0:
            out.setdefault(currency, []).append(y)
    return out


def filter_eligible(
    bonds: list[Any],
    *,
    peer_bonds: list[Any] | None = None,
) -> tuple[list[Any], dict[str, EligibilityResult]]:
    """Разделить список бумаг на пригодные и исключённые.

    Принимает объекты с атрибутами (BondORM, Bond) или dict'ы со стандартными
    полями: internal_id, price, nominal, yield_to_maturity, status, currency.
    Возвращает (eligible, {internal_id: EligibilityResult}).
    """
    universe = peer_bonds if peer_bonds is not None else bonds
    peers_by_currency = peer_ytms_by_currency(universe)

    # Ленивый импорт: desk/__init__ импортирует desk.relative_value, который
    # импортирует scoring.eligibility — цикл ломается здесь.
    from desk.ytm import to_price_pct

    eligible: list[Any] = []
    excluded: dict[str, EligibilityResult] = {}
    for b in bonds:
        internal_id = str(_field(b, "internal_id") or "")
        price = _field(b, "price")
        ytm = _field(b, "yield_to_maturity")
        status = _field(b, "status")
        currency = _field(b, "currency")

        price_pct = to_price_pct(price, _field(b, "nominal")) if price is not None else None
        ytm_pct = None
        if ytm is not None:
            try:
                ytm_pct = float(ytm)
            except (TypeError, ValueError):
                ytm_pct = None

        res = check_eligibility(
            internal_id=internal_id,
            price_pct=price_pct,
            ytm_pct=ytm_pct,
            status=str(status) if status is not None else None,
            peer_ytms=peers_by_currency.get(str(currency or "").upper()),
        )
        if res.eligible:
            eligible.append(b)
        else:
            excluded[internal_id] = res
    return eligible, excluded
