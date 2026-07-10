"""Telegram-бот: aiogram 3, точка входа."""

from __future__ import annotations

import asyncio
import os
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

# ---------------------------------------------------------------------------
# Re-exports — backward compat for tests (single-module layout → refactored)
# ---------------------------------------------------------------------------
import desk.carry as desk_carry  # noqa: F401
import desk.repo as desk_repo  # noqa: F401
import desk.stress as desk_stress  # noqa: F401
import desk.yield_curve as desk_curve  # noqa: F401
from desk import duration as desk_duration  # noqa: F401
from desk import relative_value as desk_rv  # noqa: F401
from desk.repository import latest_rv_signals, latest_stress_runs  # noqa: F401
from forecast.engine import forecast_horizons  # noqa: F401
from ml.repository import latest_model_version, predictions_for_bond  # noqa: F401
from notifications.fx_repository import latest_fx  # noqa: F401
from notifications.repository import list_recent  # noqa: F401
from portfolio.optimizer import allocate, rebalance  # noqa: F401
from portfolio.positions_repository import list_positions, total_value  # noqa: F401
from portfolio.rebalance import build_plan  # noqa: F401
from portfolio.scenarios import run_all_scenarios  # noqa: F401
from recommendations.engine import recommend_bonds  # noqa: F401
from scoring.engine import score_bond  # noqa: F401
from scoring.repository import get_score, top_scores  # noqa: F401
from scraper import repositories  # noqa: F401
from scraper.db import session_scope  # noqa: F401
from telegram_bot.handlers import (  # noqa: F401
    cmd_alerts,
    cmd_buy,
    cmd_byn,
    cmd_carry,
    cmd_curve,
    cmd_desk,
    cmd_desk_status,
    cmd_duration,
    cmd_forecast,
    cmd_help,
    cmd_metals,
    cmd_ml,
    cmd_new,
    cmd_parse,
    cmd_portfolio,
    cmd_predict,
    cmd_rates,
    cmd_rebalance,
    cmd_rebalance_auto,
    cmd_repo,
    cmd_rv,
    cmd_scenario,
    cmd_set,
    cmd_settings,
    cmd_start,
    cmd_stats,
    cmd_stress,
    cmd_top,
    cmd_unwatch,
    cmd_usd,
    cmd_watch,
    cmd_watchlist,
    router,
)
from telegram_bot.helpers import (  # noqa: F401
    bonds_for_bot as _bonds_for_bot,
)
from telegram_bot.helpers import (  # noqa: F401
    fetch_all_bonds as _fetch_all_bonds,
)
from telegram_bot.helpers import (  # noqa: F401
    fetch_bonds_by_currency as _fetch_bonds_by_currency,
)
from telegram_bot.helpers import (  # noqa: F401
    fetch_bonds_with_history as _fetch_bonds_with_history,
)
from telegram_bot.helpers import (  # noqa: F401
    paginate_kb,
    parse_bond_args,
    parse_funding_rate,
)
from telegram_bot.middleware import (
    ParseLockMiddleware,
    RequestIdMiddleware,
    SubscriptionMiddleware,
    ThrottlingMiddleware,
)
from telegram_bot.preferences_repository import (  # noqa: F401
    add_to_watchlist,
    get_preferences,
    remove_from_watchlist,
    upsert_preferences,
)
from telegram_bot.stars_payments import stars_router
from visualization.charts import (  # noqa: F401
    plot_capital_forecast,
    plot_portfolio_pie,
    plot_yield_distribution,
)


async def main(token: str) -> None:
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    dp.include_router(stars_router)
    dp.message.middleware(ParseLockMiddleware())
    dp.message.middleware(SubscriptionMiddleware())
    dp.message.middleware(ThrottlingMiddleware())
    dp.message.middleware(RequestIdMiddleware())

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: None)
    except NotImplementedError:
        pass

    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        webhook_path = os.getenv("WEBHOOK_PATH", "/webhook")
        await bot.set_webhook(webhook_url + webhook_path)
        from aiohttp import web

        app = web.Application()
        app.router.add_post(webhook_path, lambda r: dp.dispatch(r))
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("WEBHOOK_PORT", "8080"))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("webhook_started", url=webhook_url, port=port)
        await asyncio.Event().wait()
    else:
        try:
            await dp.start_polling(bot, handle_signals=True)
        finally:
            await bot.close()


def _validate_env() -> tuple[str | None, str | None]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    missing: list[str] = []
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not os.getenv("DATABASE_URL"):
        missing.append("DATABASE_URL")
    if missing:
        return None, f"FATAL: missing env vars: {', '.join(missing)}"
    return token, None


def cli() -> int:
    token, error = _validate_env()
    if error:
        print(error)
        return 1
    asyncio.run(main(token))
    return 0


if __name__ == "__main__":
    sys.exit(cli())
