"""Тесты Telegram-бота: проверка всех command handler'ов."""

from __future__ import annotations

from dataclasses import dataclass, field

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import telegram_bot.bot as bot_mod


@dataclass
class FakeMessage:
    """Заглушка для aiogram.types.Message."""

    text: str | None = None
    from_user: object | None = None
    answers: list[dict[str, Any]] = field(default_factory=list)

    async def answer(self, text="", **kwargs):
        self.answers.append({"text": text, **kwargs})
        return type("Msg", (), {})()

    async def answer_photo(self, *args, **kwargs):
        pass


@pytest.fixture
def msg():
    return FakeMessage(text="/start", from_user=type("U", (), {"id": 0, "full_name": "Test"})())


def _make_result(scalars_return=None):
    """Создаёт цепочку session.execute().scalars().all() для AsyncMock."""

    class FakeScalars:
        def all(self):
            return scalars_return or []

        def first(self):
            return (scalars_return or [None])[0]

    class FakeResult:
        def scalars(self):
            return FakeScalars()

        def scalar_one_or_none(self):
            return None

        def scalar_one(self):
            return None

    return FakeResult()


@pytest.fixture(autouse=True)
def _patch_db():
    with patch("telegram_bot.handlers.session_scope") as mock_scope:
        mock_session = AsyncMock()
        mock_session.execute.return_value = _make_result([])
        mock_scope.return_value.__aenter__.return_value = mock_session
        yield mock_session


@pytest.fixture(autouse=True)
def _patch_repositories():
    defaults = [
        patch("telegram_bot.handlers.top_scores", AsyncMock(return_value=[])),
        patch("telegram_bot.handlers.repositories.bonds.get_by_currency", AsyncMock(return_value=[])),
        patch(
            "telegram_bot.handlers.repositories.bonds.get_all_internal_ids",
            AsyncMock(return_value=set()),
        ),
        patch("telegram_bot.handlers.repositories.bonds.exists", AsyncMock(return_value=True)),
        patch(
            "telegram_bot.preferences_repository.get_preferences",
            AsyncMock(
                return_value=type(
                    "P",
                    (),
                    {
                        "user_id": 0,
                        "initial_capital": Decimal("10000"),
                        "monthly_contribution": Decimal("500"),
                        "usd_byn_forecast": Decimal("3.30"),
                        "share_usd": 0.5,
                        "share_byn": 0.3,
                        "share_metals": 0.2,
                        "share_eur": 0.0,
                        "strategy": "Balanced",
                        "watchlist": [],
                    },
                )()
            ),
        ),
        patch("telegram_bot.handlers.score_bond", return_value=type("S", (), {"score": 75.0})()),
        patch("telegram_bot.handlers.plot_yield_distribution", return_value=b"png"),
        patch("telegram_bot.handlers.get_score", AsyncMock(return_value=None)),
        patch(
            "telegram_bot.preferences_repository.add_to_watchlist",
            AsyncMock(return_value=type("P", (), {"watchlist": ["OP-51"]})()),
        ),
        patch("telegram_bot.preferences_repository.remove_from_watchlist", AsyncMock()),
        patch("telegram_bot.handlers.list_recent", AsyncMock(return_value=[])),
        patch("telegram_bot.handlers.latest_model_version", AsyncMock(return_value=None)),
        patch("telegram_bot.handlers.predictions_for_bond", AsyncMock(return_value=[])),
        patch("telegram_bot.handlers.list_positions", AsyncMock(return_value=[])),
        patch("telegram_bot.handlers.total_value", return_value=Decimal("0")),
        patch("telegram_bot.handlers.build_plan", return_value=None),
        patch(
            "telegram_bot.handlers.allocate",
            return_value=type(
                "A",
                (),
                {
                    "expected_return": 8.0,
                    "volatility": 4.0,
                    "sharpe": 1.5,
                    "sortino": 2.0,
                    "max_drawdown": -15.0,
                    "var_95": -5.0,
                    "strategy": "Balanced",
                },
            )(),
        ),
        patch("telegram_bot.handlers.forecast_horizons", return_value=[]),
        patch("telegram_bot.handlers.plot_portfolio_pie", return_value=b"png"),
        patch("telegram_bot.handlers.plot_capital_forecast", return_value=b"png"),
        patch(
            "notifications.fx_repository.latest_fx",
            AsyncMock(return_value=type("F", (), {"rate": Decimal("3.30")})()),
        ),
        patch("telegram_bot.handlers.run_all_scenarios", return_value=[]),
        patch("telegram_bot.handlers.recommend_bonds", return_value=[]),
        patch("telegram_bot.handlers.rebalance", return_value=({}, {})),
        patch(
            "telegram_bot.handlers.desk_curve.curve_from_bonds",
            return_value=type("C", (), {"points": [], "slope": lambda: 0.0})(),
        ),
        patch(
            "telegram_bot.handlers.desk_curve.fit_nelson_siegel",
            return_value=type("P", (), {"beta0": 0, "beta1": 0, "beta2": 0})(),
        ),
        patch("telegram_bot.handlers.desk_rv.relative_value_signals", return_value=[]),
        patch(
            "telegram_bot.handlers.desk_duration.duration_report",
            return_value=type(
                "R",
                (),
                {
                    "macaulay_duration": 3.5,
                    "modified_duration": 3.4,
                    "convexity": 15.0,
                    "dv01": 0.05,
                    "key_rate_durations": {},
                },
            )(),
        ),
        patch(
            "telegram_bot.handlers.desk_duration.portfolio_duration",
            return_value=type(
                "R",
                (),
                {
                    "macaulay_duration": 3.5,
                    "modified_duration": 3.4,
                    "convexity": 15.0,
                    "dv01": 0.05,
                    "key_rate_durations": {},
                },
            )(),
        ),
        patch("telegram_bot.handlers.desk_carry.rank_carry", return_value=[]),
        patch("telegram_bot.handlers.desk_repo.haircut_by_issuer", return_value=0.05),
        patch(
            "telegram_bot.handlers.desk_repo.repo_deal",
            return_value=type(
                "D",
                (),
                {
                    "collateral_value": 950,
                    "haircut_pct": 5,
                    "cash_lent": 950,
                    "repo_rate_pct": 5.0,
                    "tenor_days": 30,
                    "accrued_interest": 3.95,
                },
            )(),
        ),
        patch("telegram_bot.handlers.desk_stress.PRESET_SCENARIOS", {}),
        patch(
            "telegram_bot.handlers.desk_stress.run_stress",
            return_value=type("R", (), {"pnl_pct": -0.5, "pnl": -50})(),
        ),
        patch("telegram_bot.handlers.latest_rv_signals", AsyncMock(return_value=[])),
        patch("telegram_bot.handlers.latest_stress_runs", AsyncMock(return_value=[])),
        patch("telegram_bot.handlers.fetch_bonds_by_currency", AsyncMock(return_value=[])),
        patch("telegram_bot.handlers.fetch_all_bonds", AsyncMock(return_value=[])),
        patch("telegram_bot.handlers.fetch_bonds_with_history", AsyncMock(return_value=([], {}))),
        patch("telegram_bot.handlers.bonds_for_bot", AsyncMock(return_value=[])),
        patch("telegram_bot.handlers.repositories.bonds.count_bonds", AsyncMock(return_value=42)),
        patch(
            "telegram_bot.handlers.repositories.bonds.latest_fetched_at", AsyncMock(return_value=None)
        ),
    ]
    for p in defaults:
        p.start()
    yield
    for p in defaults:
        p.stop()


# ─── Тесты ─────────────────────────────────────────────────────────────────


class TestBotCore:
    async def test_start(self, msg) -> None:
        await bot_mod.cmd_start(msg)
        assert "Bond Fixed Income Assistant" in msg.answers[0]["text"]

    async def test_help(self, msg) -> None:
        await bot_mod.cmd_help(msg)
        assert len(msg.answers) == 1

    async def test_desk(self, msg) -> None:
        await bot_mod.cmd_desk(msg)
        assert "Mini Fixed Income Desk" in msg.answers[0]["text"]


class TestBotTop:
    async def test_top_empty(self, msg) -> None:
        await bot_mod.cmd_top(msg)
        assert "пуста" in msg.answers[0]["text"]

    async def test_top_with_data(self, msg) -> None:
        fake = type("S", (), {"internal_id": "OP-51", "score": Decimal("85.0")})
        with patch("telegram_bot.handlers.top_scores", AsyncMock(return_value=[fake])):
            await bot_mod.cmd_top(msg)
        assert "OP-51" in msg.answers[0]["text"]

    async def test_top_multiple(self, msg) -> None:
        scores = [
            type("S", (), {"internal_id": f"OP-{i}", "score": Decimal(str(100 - i * 5))})
            for i in range(5)
        ]
        with patch("telegram_bot.handlers.top_scores", AsyncMock(return_value=scores)):
            await bot_mod.cmd_top(msg)
        for i in range(5):
            assert f"OP-{i}" in msg.answers[0]["text"]


class TestBotCurrency:
    async def test_usd_empty(self, msg) -> None:
        await bot_mod.cmd_usd(msg)
        assert "Нет облигаций в USD" in msg.answers[0]["text"]

    async def test_byn(self, msg) -> None:
        await bot_mod.cmd_byn(msg)
        assert len(msg.answers) == 1

    async def test_metals(self, msg) -> None:
        await bot_mod.cmd_metals(msg)
        assert len(msg.answers) == 1

    async def test_new_empty(self, msg) -> None:
        await bot_mod.cmd_new(msg)
        assert len(msg.answers) == 1


class TestBotPortfolio:
    async def test_portfolio_no_bonds(self, msg) -> None:
        await bot_mod.cmd_portfolio(msg)
        assert "нет данных" in msg.answers[0]["text"].lower()

    async def test_rebalance(self, msg) -> None:
        await bot_mod.cmd_rebalance(msg)
        assert len(msg.answers) == 1

    async def test_forecast(self, msg) -> None:
        await bot_mod.cmd_forecast(msg)
        assert len(msg.answers) >= 1

    async def test_scenario(self, msg) -> None:
        await bot_mod.cmd_scenario(msg)
        assert "Сценарии" in msg.answers[0]["text"]


class TestBotBuyML:
    async def test_buy_empty(self, msg) -> None:
        await bot_mod.cmd_buy(msg)
        assert len(msg.answers) == 1

    async def test_ml_no_models(self, msg) -> None:
        await bot_mod.cmd_ml(msg)
        assert "ML-модели" in msg.answers[0]["text"]

    async def test_predict_no_id(self, msg) -> None:
        msg.text = "/predict"
        await bot_mod.cmd_predict(msg)
        assert "Использование" in msg.answers[0]["text"]


class TestBotWatchlist:
    async def test_watchlist_empty(self, msg) -> None:
        await bot_mod.cmd_watchlist(msg)
        assert "Watchlist пуст" in msg.answers[0]["text"]

    async def test_watch_no_id(self, msg) -> None:
        msg.text = "/watch"
        await bot_mod.cmd_watch(msg)
        assert "Использование" in msg.answers[0]["text"]

    async def test_watch_not_found(self, msg) -> None:
        msg.text = "/watch OP-99"
        with patch("telegram_bot.handlers.repositories.bonds.exists", AsyncMock(return_value=False)):
            await bot_mod.cmd_watch(msg)
        assert "не найдена" in msg.answers[0]["text"]

    async def test_unwatch_not_found(self, msg) -> None:
        msg.text = "/unwatch OP-99"
        with patch("telegram_bot.handlers.repositories.bonds.exists", AsyncMock(return_value=False)):
            await bot_mod.cmd_unwatch(msg)
        assert "не найдена" in msg.answers[0]["text"]

    async def test_watch_success(self, msg) -> None:
        msg.text = "/watch OP-51"
        await bot_mod.cmd_watch(msg)
        assert "OP-51" in msg.answers[0]["text"]

    async def test_unwatch_no_id(self, msg) -> None:
        msg.text = "/unwatch"
        await bot_mod.cmd_unwatch(msg)
        assert "Использование" in msg.answers[0]["text"]

    async def test_unwatch_success(self, msg) -> None:
        msg.text = "/unwatch OP-51"
        await bot_mod.cmd_unwatch(msg)
        assert "OP-51" in msg.answers[0]["text"]

    async def test_watchlist_with_items(self, msg) -> None:
        prefs = type(
            "P",
            (),
            {
                "watchlist": ["OP-51", "OP-47"],
                "user_id": 0,
                "initial_capital": Decimal("10000"),
                "monthly_contribution": Decimal("500"),
                "usd_byn_forecast": Decimal("3.30"),
                "share_usd": 0.5,
                "share_byn": 0.3,
                "share_metals": 0.2,
                "share_eur": 0.0,
                "strategy": "Balanced",
            },
        )
        with (
            patch("telegram_bot.preferences_repository.get_preferences", AsyncMock(return_value=prefs)),
            patch(
                "telegram_bot.handlers.get_score",
                AsyncMock(return_value=type("S", (), {"score": Decimal("85.0")})()),
            ),
        ):
            await bot_mod.cmd_watchlist(msg)
        assert "OP-51" in msg.answers[0]["text"]
        assert "OP-47" in msg.answers[0]["text"]


class TestBotAlerts:
    async def test_alerts_empty(self, msg) -> None:
        await bot_mod.cmd_alerts(msg)
        assert "Алерты" in msg.answers[0]["text"]

    async def test_alerts_with_data(self, msg) -> None:
        alert = type("A", (), {"title": "New Bond", "message": "OP-51 появилась"})
        with patch("telegram_bot.handlers.list_recent", AsyncMock(return_value=[alert])):
            await bot_mod.cmd_alerts(msg)
        assert "New Bond" in msg.answers[0]["text"]


class TestBotDesk:
    async def test_curve(self, msg) -> None:
        await bot_mod.cmd_curve(msg)
        assert len(msg.answers) == 1

    async def test_rv(self, msg) -> None:
        await bot_mod.cmd_rv(msg)
        assert len(msg.answers) == 1

    async def test_duration(self, msg) -> None:
        await bot_mod.cmd_duration(msg)
        assert "Duration Report" in msg.answers[0]["text"]

    async def test_duration_not_found(self, msg) -> None:
        msg.text = "/duration OP-99"
        await bot_mod.cmd_duration(msg)
        assert "не найдена" in msg.answers[0]["text"]

    async def test_carry(self, msg) -> None:
        await bot_mod.cmd_carry(msg)
        assert len(msg.answers) == 1

    async def test_repo_no_id(self, msg) -> None:
        msg.text = "/repo"
        await bot_mod.cmd_repo(msg)
        assert "Использование" in msg.answers[0]["text"]

    async def test_repo_not_found(self, msg) -> None:
        msg.text = "/repo OP-99"
        await bot_mod.cmd_repo(msg)
        assert "не найдена" in msg.answers[0]["text"]

    async def test_stress(self, msg) -> None:
        await bot_mod.cmd_stress(msg)
        assert len(msg.answers) == 1

    async def test_desk_status(self, msg) -> None:
        await bot_mod.cmd_desk_status(msg)
        assert "Desk Status" in msg.answers[0]["text"]


class TestBotRebalanceAuto:
    async def test_no_drift(self, msg) -> None:
        await bot_mod.cmd_rebalance_auto(msg)
        assert "Drift ниже порога" in msg.answers[0]["text"]


class TestBotPredict:
    async def test_predict_no_result(self, msg) -> None:
        msg.text = "/predict OP-51"
        await bot_mod.cmd_predict(msg)
        assert "Нет прогнозов" in msg.answers[0]["text"]

    async def test_predict_result(self, msg) -> None:
        msg.text = "/predict OP-51"
        pred = type(
            "P",
            (),
            {
                "internal_id": "OP-51",
                "decision": "buy",
                "confidence": 0.85,
                "predicted_ytm": 6.5,
                "predicted_return_pct": 1.2,
                "explanation": ["YTM выше среднего"],
            },
        )
        with patch("telegram_bot.handlers.predictions_for_bond", AsyncMock(return_value=[pred])):
            await bot_mod.cmd_predict(msg)
        assert "Прогноз OP-51" in msg.answers[0]["text"]
        assert "buy" in msg.answers[0]["text"]


class TestBotStats:
    async def test_stats(self, msg) -> None:
        await bot_mod.cmd_stats(msg)
        assert "Статистика" in msg.answers[0]["text"]


class TestBotSettings:
    async def test_settings_shows_prefs(self, msg) -> None:
        await bot_mod.cmd_settings(msg)
        assert "Настройки портфеля" in msg.answers[0]["text"]

    async def test_set_capital(self, msg) -> None:
        msg.text = "/set capital 50000"
        with patch("telegram_bot.preferences_repository.upsert_preferences", AsyncMock()):
            await bot_mod.cmd_set(msg)
        assert "capital" in msg.answers[0]["text"]

    async def test_set_contribution(self, msg) -> None:
        msg.text = "/set contribution 2000"
        with patch("telegram_bot.preferences_repository.upsert_preferences", AsyncMock()):
            await bot_mod.cmd_set(msg)
        assert "contribution" in msg.answers[0]["text"]

    async def test_set_strategy(self, msg) -> None:
        msg.text = "/set strategy Aggressive"
        with patch("telegram_bot.preferences_repository.upsert_preferences", AsyncMock()):
            await bot_mod.cmd_set(msg)
        assert "strategy" in msg.answers[0]["text"]

    async def test_set_share(self, msg) -> None:
        msg.text = "/set share_usd 0.5"
        with patch("telegram_bot.preferences_repository.upsert_preferences", AsyncMock()):
            await bot_mod.cmd_set(msg)
        assert "share_usd" in msg.answers[0]["text"]

    async def test_set_share_warns_on_sum_mismatch(self, msg) -> None:
        msg.text = "/set share_usd 0.8"
        with patch("telegram_bot.preferences_repository.upsert_preferences", AsyncMock()):
            await bot_mod.cmd_set(msg)
        assert "100%" in msg.answers[0]["text"]

    async def test_set_no_args(self, msg) -> None:
        msg.text = "/set"
        await bot_mod.cmd_set(msg)
        assert "Использование" in msg.answers[0]["text"]

    async def test_set_invalid_field(self, msg) -> None:
        msg.text = "/set foo bar"
        with patch("telegram_bot.preferences_repository.upsert_preferences", AsyncMock()):
            await bot_mod.cmd_set(msg)
        assert "Неизвестное поле" in msg.answers[0]["text"]

    async def test_set_invalid_value(self, msg) -> None:
        msg.text = "/set capital abc"
        with patch("telegram_bot.preferences_repository.upsert_preferences", AsyncMock()):
            await bot_mod.cmd_set(msg)
        assert "Ошибка" in msg.answers[0]["text"]
