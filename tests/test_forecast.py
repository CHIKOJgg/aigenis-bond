"""Тесты forecast: прогноз капитала."""

from __future__ import annotations

from decimal import Decimal

from forecast.engine import forecast_capital, forecast_horizons


def test_forecast_horizons_count() -> None:
    results = forecast_horizons(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("500"),
        expected_annual_return_pct=7.0,
        volatility_pct=2.0,
    )
    assert [r.horizon_years for r in results] == [1, 3, 5]


def test_forecast_growth() -> None:
    r1 = forecast_capital(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("0"),
        expected_annual_return_pct=7.0,
        horizon_years=1,
    )
    r5 = forecast_capital(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("0"),
        expected_annual_return_pct=7.0,
        horizon_years=5,
    )
    assert r5.expected_capital > r1.expected_capital


def test_forecast_with_contributions() -> None:
    r = forecast_capital(
        initial_capital=Decimal("0"),
        monthly_contribution=Decimal("100"),
        expected_annual_return_pct=0.0,
        horizon_years=1,
    )
    assert r.expected_capital == Decimal("1200.00")


def test_forecast_pessimistic_below_expected() -> None:
    r = forecast_capital(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("100"),
        expected_annual_return_pct=8.0,
        horizon_years=3,
        volatility_pct=3.0,
    )
    assert r.pessimistic_capital < r.expected_capital < r.optimistic_capital
