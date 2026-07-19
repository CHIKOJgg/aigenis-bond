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
        name="Parallel +100bp",
        description="Параллельный сдвиг кривой доходности вверх на 100bp",
        rate_shocks={"1Y": 1.0, "5Y": 1.0, "10Y": 1.0, "30Y": 1.0},
    ),
    "parallel_-100bp": StressScenario(
        kind="parallel",
        name="Parallel -100bp",
        description="Параллельный сдвиг кривой доходности вниз на 100bp",
        rate_shocks={"1Y": -1.0, "5Y": -1.0, "10Y": -1.0, "30Y": -1.0},
    ),
    "steepener_+50_+150": StressScenario(
        kind="steepener",
        name="Steepener",
        description="Короткие ставки +50bp, длинные +150bp",
        rate_shocks={"1Y": 0.5, "5Y": 1.0, "10Y": 1.3, "30Y": 1.5},
    ),
    "flattener_+150_+50": StressScenario(
        kind="flattener",
        name="Flattener",
        description="Короткие ставки +150bp, длинные +50bp",
        rate_shocks={"1Y": 1.5, "5Y": 1.0, "10Y": 0.7, "30Y": 0.5},
    ),
    "inversion_+200_-50": StressScenario(
        kind="inversion",
        name="Inversion",
        description="Короткие +200bp, длинные -50bp (инверсия)",
        rate_shocks={"1Y": 2.0, "5Y": 1.0, "10Y": 0.0, "30Y": -0.5},
    ),
    "credit_shock_+150bp": StressScenario(
        kind="credit_shock",
        name="Credit shock",
        description="Кредитные спреды +150bp",
        credit_spread_shock_bps=150.0,
    ),
    "fx_shock_-20%": StressScenario(
        kind="fx_shock",
        name="FX shock -20%",
        description="Основная валюта -20% к BYN",
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

        duration = duration_report(
            bond,
            asof=asof,
            ytm_override=float(bond.yield_to_maturity),
        ).modified_duration

        price_change_pct = -duration * rate_shock_pct - duration * credit_shock_pct
        new_price = float(bond.price or 100) * (1 + price_change_pct)

        fx_impact = 1.0
        if scenario.fx_shock_pct != 0 and str(bond.currency).upper() != base_currency.upper():
            fx_impact = 1 + scenario.fx_shock_pct / 100

        cur_value = amount * Decimal(str(new_price / 100)) * Decimal(str(fx_impact))
        # Baseline must reflect the bond's actual market price (not par), so an
        # unshocked position shows ~zero P&L regardless of price != 100.
        base_price = float(bond.price or 100)
        baseline_value = amount * Decimal(str(base_price / 100))

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
