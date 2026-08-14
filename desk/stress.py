"""Stress Testing: сценарии шока ставок, кредитных спредов, FX."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from desk.duration import duration_report
from desk.models import StressResult, StressScenario
from scraper.models import Bond

PRESET_SCENARIOS: dict[str, StressScenario] = {
    "parallel_+100bp": StressScenario(
        kind="parallel",
        name="Параллельный сдвиг +100 б.п. (+1%)",
        description="Синхронный рост процентных ставок ЦБ и доходностей по всей кривой на 100 б.п.",
        simple_description="Ставки в экономике выросли на 1%. Облигации слегка дешевеют в цене, но продолжают давать стабильный купон. Чем длиннее выпуск, тем чувствительнее цена.",
        rate_shocks={"1Y": 1.0, "5Y": 1.0, "10Y": 1.0, "30Y": 1.0},
    ),
    "parallel_+300bp": StressScenario(
        kind="parallel",
        name="Параллельный шок +300 б.п. (+3%)",
        description="Резкое ужесточение ДКП и стрессовый подъем ключевой ставки регулятора на 300 б.п.",
        simple_description="Жесткий кризисный подъем ставок (+3%). Рыночные цены текущих облигаций заметно проседают, так как новые бумаги будут выходить с повышенным процентом.",
        rate_shocks={"1Y": 3.0, "5Y": 3.0, "10Y": 3.0, "30Y": 3.0},
    ),
    "parallel_-100bp": StressScenario(
        kind="parallel",
        name="Снижение ставок -100 б.п. (-1%)",
        description="Смягчение денежно-кредитной политики и параллельное снижение доходностей на 100 б.п.",
        simple_description="ЦБ снижает ставки на 1%. Текущие облигации с высокой фиксированной доходностью дорожают на бирже, принося дополнительную прибыль к купонам.",
        rate_shocks={"1Y": -1.0, "5Y": -1.0, "10Y": -1.0, "30Y": -1.0},
    ),
    "steepener_+50_+150": StressScenario(
        kind="steepener",
        name="Steepener (Крутизна кривой)",
        description="Короткие ставки +50 б.п., долгосрочные ставки +150 б.п. Рост премии за срочность.",
        simple_description="Инвесторы требуют повышенную премию за риск вдолгую. Длинные бумаги (от 5 лет) дешевеют сильнее, а короткие (до 1 года) сохраняют стоимость.",
        rate_shocks={"1Y": 0.5, "5Y": 1.0, "10Y": 1.3, "30Y": 1.5},
    ),
    "flattener_+150_+50": StressScenario(
        kind="flattener",
        name="Flattener (Уплощение кривой)",
        description="Опережающий рост коротких ставок (+150 б.п.) при умеренном изменении длинных (+50 б.п.).",
        simple_description="Краткосрочные деньги резко дорожают. Разница в доходности между короткими и длинными бумагами почти исчезает.",
        rate_shocks={"1Y": 1.5, "5Y": 1.0, "10Y": 0.7, "30Y": 0.5},
    ),
    "inversion_+200_-50": StressScenario(
        kind="inversion",
        name="Инверсия кривой (+200 / -50 б.п.)",
        description="Резкий скачок коротких ставок (+200 б.п.) при снижении долгосрочных (-50 б.п.). Сигнал замедления.",
        simple_description="Аномалия: короткие вклады и бумаги дают больше процентов, чем длинные. Обычно такое бывает перед экономическим спадом и скорым снижением ставок.",
        rate_shocks={"1Y": 2.0, "5Y": 1.0, "10Y": 0.0, "30Y": -0.5},
    ),
    "credit_shock_+150bp": StressScenario(
        kind="credit_shock",
        name="Кредитный шок спредов (+150 б.п.)",
        description="Расширение кредитных спредов корпоративного сектора на 150 б.п. из-за роста риска компаний.",
        simple_description="Рынок начинает больше опасаться за надежность коммерческих эмитентов. Корпоративные бумаги дешевеют, а гособлигации Минфина остаются в безопасности.",
        credit_spread_shock_bps=150.0,
    ),
    "fx_shock_-20%": StressScenario(
        kind="fx_shock",
        name="Валютный шок (-20% к USD)",
        description="Девальвация национальной валюты (BYN/RUB) к доллару США на 20%.",
        simple_description="Курс доллара подскочил на 20%. Валютные и индексируемые облигации в пересчете на рубли дают мощную курсовую прибыль, защищая капитал.",
        fx_shock_pct=-20.0,
    ),
}


def _bucket_tenor(years: float) -> str:
    if years <= 1:
        return "1Y"
    if years <= 5:
        return "5Y"
    if years <= 10:
        return "10Y"
    return "30Y"


def run_stress(
    scenario: StressScenario,
    bonds_with_amounts: Iterable[tuple[Bond, Decimal]],
    *,
    base_currency: str = "USD",
    asof: date | None = None,
) -> StressResult:
    """Прогнать стресс-сценарий: оценить P&L портфеля."""
    asof = asof or date.today()

    by_position: dict[str, Decimal] = {}
    by_tenor: dict[str, Decimal] = {}
    portfolio_value = Decimal("0")
    stressed_value = Decimal("0")

    for bond, amount in bonds_with_amounts:
        if bond.maturity_date is None or bond.yield_to_maturity is None:
            continue
        years = max((bond.maturity_date - asof).days / 365.25, 0.0)
        tenor = _bucket_tenor(years)

        rate_shock_pct = float(scenario.rate_shocks.get(tenor, 0.0)) / 100.0
        # Credit-spread shocks apply only to credit-risky issuers. Sovereign /
        # central-bank / government bonds are risk-free and must not absorb a
        # credit spread shock.
        is_gov = bool(getattr(bond, "is_government", False))
        credit_shock_pct = 0.0 if is_gov else scenario.credit_spread_shock_bps / 10000.0

        try:
            duration = duration_report(
                bond,
                asof=asof,
                ytm_override=float(bond.yield_to_maturity),
            ).modified_duration
        except Exception:
            # Дюрация не считается (экзотические параметры) — грубая оценка
            # по сроку: 0.75 года на каждый год до погашения.
            duration = max((bond.maturity_date - asof).days / 365.25, 0.5) * 0.75

        # Linear duration term plus a convexity correction for large shocks
        # (±100bp/±200bp), where the straight-line approximation is materially
        # off. Convexity is approximated from modified duration (zero-coupon
        # bound: convexity ≈ duration²), which is conservative for coupon bonds.
        total_shock = rate_shock_pct + credit_shock_pct
        convexity = duration * duration
        price_change_pct = -duration * total_shock + 0.5 * convexity * total_shock * total_shock
        base_price = float(bond.price if bond.price is not None else 100.0)
        new_price = base_price * (1.0 + price_change_pct)

        fx_impact = 1.0
        if scenario.fx_shock_pct != 0 and str(bond.currency).upper() != base_currency.upper():
            fx_impact = 1.0 + scenario.fx_shock_pct / 100.0

        cur_value = amount * Decimal(str(new_price / 100.0)) * Decimal(str(fx_impact))
        baseline_value = amount * Decimal(str(base_price / 100.0))

        by_position[bond.internal_id] = cur_value - baseline_value
        by_tenor[tenor] = by_tenor.get(tenor, Decimal("0")) + (cur_value - baseline_value)
        portfolio_value += baseline_value
        stressed_value += cur_value

    pnl = stressed_value - portfolio_value
    pct = float(pnl / portfolio_value * 100) if portfolio_value else 0.0

    return StressResult(
        scenario=scenario,
        portfolio_value=portfolio_value.quantize(Decimal("0.01")),
        stressed_value=stressed_value.quantize(Decimal("0.01")),
        pnl=pnl.quantize(Decimal("0.01")),
        pnl_pct=round(pct, 3),
        by_position={k: v.quantize(Decimal("0.01")) for k, v in by_position.items()},
        by_tenor={k: v.quantize(Decimal("0.01")) for k, v in by_tenor.items()},
        asof_date=asof,
    )


def run_all_presets(
    bonds_with_amounts: Iterable[tuple[Bond, Decimal]],
    *,
    base_currency: str = "USD",
) -> dict[str, StressResult]:
    return {
        name: run_stress(scn, bonds_with_amounts, base_currency=base_currency)
        for name, scn in PRESET_SCENARIOS.items()
    }
