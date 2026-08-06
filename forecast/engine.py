"""Forecast: прогноз роста капитала (аннуитет + симуляция Монте-Карло).

The deterministic annuity answers "what happens if returns are exactly
average"; the Monte Carlo layer answers the question investors actually ask —
"how much could I have at the end, and how bad could it get?". We simulate
monthly compounding with normal shocks sized by ``volatility_pct`` and report
the 5/25/50/75/95 percentiles plus CVaR_95 (expected shortfall of the worst
5% of outcomes).
"""

from __future__ import annotations

import math
from decimal import Decimal
from statistics import fmean

from scoring.models import ForecastResult

_MC_SEED = 42  # deterministic across runs so charts don't flicker


def _monthly_return(annual_pct: float) -> Decimal:
    return Decimal(str((1 + annual_pct / 100) ** (1 / 12) - 1))


def _annuity(
    initial: Decimal,
    monthly: Decimal,
    annual_pct: float,
    months: int,
) -> Decimal:
    rate = _monthly_return(annual_pct)
    value = initial
    for _ in range(months):
        value = value * (Decimal("1") + rate) + monthly
    return value


def _monte_carlo(
    initial_capital: Decimal,
    monthly_contribution: Decimal,
    expected_annual_return_pct: float,
    volatility_pct: float,
    months: int,
    n_paths: int = 2000,
) -> tuple[list[float], list[float]]:
    """Simulate ``n_paths`` capital paths; return (final values, path means).

    Monthly log-normal shocks: monthly drift is derived from the annual return
    (geometric), monthly sigma from the annual volatility / sqrt(12).
    """
    import random

    rng = random.Random(_MC_SEED)
    mu = math.log1p(expected_annual_return_pct / 100) / 12
    sigma = max(volatility_pct, 0.0) / 100 / math.sqrt(12)
    monthly_c = float(monthly_contribution)
    initial_f = float(initial_capital)

    finals: list[float] = []
    for _ in range(n_paths):
        value = initial_f
        for _ in range(months):
            shock = rng.gauss(mu, sigma)
            value = value * math.exp(shock) + monthly_c
        finals.append(value)
    finals.sort()
    return finals, [fmean(finals)]


def forecast_capital(
    *,
    initial_capital: Decimal,
    monthly_contribution: Decimal,
    expected_annual_return_pct: float,
    horizon_years: int,
    volatility_pct: float = 0.0,
    assumptions: dict[str, str] | None = None,
    n_paths: int = 2000,
) -> ForecastResult:
    """Прогноз с учётом ежемесячного пополнения.

    With ``volatility_pct > 0`` the pessimistic/optimistic bounds come from
    Monte Carlo percentiles (5th/95th) instead of the crude ±1σ rule, and the
    full percentile distribution plus CVaR_95 are returned for charts.
    """
    months = horizon_years * 12
    monthly = _monthly_return(expected_annual_return_pct)

    expected = initial_capital
    for _ in range(months):
        expected = expected * (Decimal("1") + monthly) + monthly_contribution

    mc_percentiles: dict[str, Decimal] = {}
    cvar_95: Decimal | None = None

    if volatility_pct > 0 and months > 0:
        finals, _means = _monte_carlo(
            initial_capital,
            monthly_contribution,
            expected_annual_return_pct,
            volatility_pct,
            months,
            n_paths=max(int(n_paths), 100),
        )

        def _pctile(q: float) -> Decimal:
            idx = min(len(finals) - 1, max(0, round(q * (len(finals) - 1))))
            return Decimal(str(round(finals[idx], 2)))

        mc_percentiles = {
            "p5": _pctile(0.05),
            "p25": _pctile(0.25),
            "p50": _pctile(0.50),
            "p75": _pctile(0.75),
            "p95": _pctile(0.95),
        }
        # CVaR_95: average of the worst 5% of outcomes.
        worst_n = max(1, int(len(finals) * 0.05))
        cvar_95 = Decimal(str(round(fmean(finals[:worst_n]), 2)))
        pessimistic = mc_percentiles["p5"]
        optimistic = mc_percentiles["p95"]
    else:
        pessimistic = expected
        optimistic = expected

    return ForecastResult(
        horizon_years=horizon_years,
        initial_capital=initial_capital,
        monthly_contribution=monthly_contribution,
        expected_capital=expected.quantize(Decimal("0.01")),
        pessimistic_capital=pessimistic.quantize(Decimal("0.01")),
        optimistic_capital=optimistic.quantize(Decimal("0.01")),
        expected_return=expected_annual_return_pct,
        assumptions=assumptions
        or {
            "expected_annual_return_pct": f"{expected_annual_return_pct:.2f}",
            "volatility_pct": f"{volatility_pct:.2f}",
            "method": "monte_carlo" if mc_percentiles else "deterministic",
            "n_paths": str(max(int(n_paths), 100)) if mc_percentiles else "1",
        },
        mc_percentiles=mc_percentiles,
        cvar_95=cvar_95,
    )


def forecast_horizons(
    *,
    initial_capital: Decimal,
    monthly_contribution: Decimal,
    expected_annual_return_pct: float,
    volatility_pct: float = 0.0,
) -> list[ForecastResult]:
    return [
        forecast_capital(
            initial_capital=initial_capital,
            monthly_contribution=monthly_contribution,
            expected_annual_return_pct=expected_annual_return_pct,
            horizon_years=years,
            volatility_pct=volatility_pct,
        )
        for years in (1, 3, 5)
    ]
