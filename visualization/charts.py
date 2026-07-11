"""Визуализация для Telegram-бота (PNG в байтах)."""

from __future__ import annotations

import io
from decimal import Decimal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from forecast.engine import forecast_horizons
from scoring.models import ForecastResult, PortfolioAllocation


def _to_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def plot_yield_distribution(yields: list[tuple[str, float]]) -> bytes:
    """Гистограмма YTM по облигациям."""
    names = [n for n, _ in yields]
    values = [v for _, v in yields]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(names[::-1], values[::-1], color="#3b82f6")
    ax.set_xlabel("Yield to maturity, %")
    ax.set_title("Распределение доходности облигаций")
    fig.tight_layout()
    return _to_png(fig)


def plot_portfolio_pie(allocation: PortfolioAllocation) -> bytes:
    labels = list(allocation.items.keys())
    sizes = [float(v) for v in allocation.items.values()]
    if not labels or sum(sizes) <= 0:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
        return _to_png(fig)
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90)
    ax.set_title(f"Портфель: {allocation.strategy}")
    fig.tight_layout()
    return _to_png(fig)


def plot_coupon_history(dates: list, coupons: list[float], title: str = "История купонов") -> bytes:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(dates, coupons, marker="o", color="#10b981")
    ax.set_title(title)
    ax.set_ylabel("Купон, %")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return _to_png(fig)


def plot_capital_forecast(
    *,
    initial_capital: Decimal,
    monthly_contribution: Decimal,
    expected_annual_return_pct: float,
    volatility_pct: float,
) -> bytes:
    results: list[ForecastResult] = forecast_horizons(
        initial_capital=initial_capital,
        monthly_contribution=monthly_contribution,
        expected_annual_return_pct=expected_annual_return_pct,
        volatility_pct=volatility_pct,
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    labels = [f"{r.horizon_years}Y" for r in results]
    pessimistic = [float(r.pessimistic_capital) for r in results]
    expected = [float(r.expected_capital) for r in results]
    optimistic = [float(r.optimistic_capital) for r in results]
    x = range(len(labels))
    ax.plot(x, pessimistic, "--", color="#ef4444", label="Пессимистичный")
    ax.plot(x, expected, "-", color="#10b981", linewidth=2, label="Ожидаемый")
    ax.plot(x, optimistic, "--", color="#3b82f6", label="Оптимистичный")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Капитал")
    ax.set_title("Прогноз роста капитала")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return _to_png(fig)
