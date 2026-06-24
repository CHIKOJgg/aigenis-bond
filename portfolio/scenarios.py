"""Сценарии USD/BYN: Bull USD / Neutral / Bull BYN / Stress."""

from __future__ import annotations

from decimal import Decimal

from scoring.models import ScenarioName, ScenarioResult

SCENARIO_DELTA: dict[ScenarioName, float] = {
    "Bull USD": 0.15,
    "Neutral": 0.0,
    "Bull BYN": -0.10,
    "Stress": -0.30,
}


def run_scenario(
    scenario: ScenarioName,
    *,
    current_usd_byn: Decimal,
    usd_share: float,
    byn_share: float,
    metals_share: float = 0.0,
    eur_share: float = 0.0,
) -> ScenarioResult:
    """Прогон сценария: считает влияние изменения курса на портфель.

    Допущение: USD-номинал растёт/падает пропорционально изменению USD/BYN
    в BYN-эквиваленте; BYN-номинал — обратно пропорционально; металлы и EUR —
    не зависят от USD/BYN.
    """
    delta = SCENARIO_DELTA[scenario]
    fx_end = current_usd_byn * (Decimal("1") + Decimal(str(delta)))
    fx_change = float((fx_end - current_usd_byn) / current_usd_byn)

    usd_impact = usd_share * fx_change
    byn_impact = byn_share * (-fx_change)
    portfolio_change = usd_impact + byn_impact

    worst: str | None = None
    notes: list[str] = []
    if scenario == "Bull USD":
        notes.append("USD-активы выигрывают, BYN-активы теряют в USD-эквиваленте")
        worst = "BYN"
    elif scenario == "Bull BYN":
        notes.append("BYN-активы выигрывают, USD-нагрузка снижается")
        worst = "USD"
    elif scenario == "Stress":
        notes.append("Стресс-сценарий: резкое ослабление BYN, рост доходностей USD")
        worst = "BYN"
    else:
        notes.append("Нейтральный сценарий: курс стабилен")

    return ScenarioResult(
        scenario=scenario,
        usd_byn_start=current_usd_byn,
        usd_byn_end=fx_end.quantize(Decimal("0.0001")),
        fx_change_pct=round(fx_change * 100, 2),
        portfolio_value_change_pct=round(portfolio_change * 100, 2),
        worst_position=worst,
        notes=notes,
    )


def run_all_scenarios(
    *,
    current_usd_byn: Decimal,
    usd_share: float,
    byn_share: float,
    metals_share: float = 0.0,
    eur_share: float = 0.0,
) -> list[ScenarioResult]:
    return [
        run_scenario(
            name,
            current_usd_byn=current_usd_byn,
            usd_share=usd_share,
            byn_share=byn_share,
            metals_share=metals_share,
            eur_share=eur_share,
        )
        for name in SCENARIO_DELTA
    ]
