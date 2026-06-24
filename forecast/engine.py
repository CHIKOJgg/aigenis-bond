"""Forecast: прогноз роста капитала."""

from __future__ import annotations

import math
from decimal import Decimal

from scoring.models import ForecastResult


def _monthly_return(annual_pct: float) -> Decimal:
    return Decimal(str((1 + annual_pct / 100) ** (1 / 12) - 1))


def forecast_capital(
    *,
    initial_capital: Decimal,
    monthly_contribution: Decimal,
    expected_annual_return_pct: float,
    horizon_years: int,
    volatility_pct: float = 0.0,
    assumptions: dict[str, str] | None = None,
) -> ForecastResult:
    """Прогноз с учётом ежемесячного пополнения и аннуитета."""
    months = horizon_years * 12
    monthly = _monthly_return(expected_annual_return_pct)

    expected = initial_capital
    for _ in range(months):
        expected = expected * (Decimal("1") + monthly) + monthly_contribution

    if volatility_pct > 0:
        spread = volatility_pct / 100.0 * math.sqrt(horizon_years)
        pessimistic = _annuity(
            initial_capital,
            monthly_contribution,
            max(expected_annual_return_pct - spread * 100, -50),
            months,
        )
        optimistic = _annuity(
            initial_capital,
            monthly_contribution,
            expected_annual_return_pct + spread * 100,
            months,
        )
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
        },
    )


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
