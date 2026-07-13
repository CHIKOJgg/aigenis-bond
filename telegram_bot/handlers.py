"""Telegram bot handlers — aggregator module.

Historically every handler lived in this single file. To keep the 1500+ line
module maintainable it was split into focused modules:

* ``telegram_bot.commands``  — all ``/command`` handlers + generic/pagination bridges
* ``telegram_bot.menus``     — main menu, section submenus, ``menu:`` navigation
* ``telegram_bot.bond_picker`` — ``bonds:`` / ``bond:`` / ``bondact:`` callbacks
* ``telegram_bot.settings``  — portfolio preferences (FSM-lite)
* ``telegram_bot.admin``     — admin commands + global error handler

This module wires those sub-routers into a single ``router`` and re-exports the
names the test-suite and ``telegram_bot.bot`` import, so external behavior is
unchanged.
"""
from __future__ import annotations

from aiogram import Router

from telegram_bot import admin, bond_picker, commands, menus, positions, settings

router = Router()
router.include_router(commands.router)
router.include_router(menus.router)
router.include_router(bond_picker.router)
router.include_router(settings.router)
router.include_router(positions.router)
router.include_router(admin.router)

# --- Re-exports so existing imports keep working ---------------------------
# These names are only re-exported (not referenced in this module body), so the
# F401 noqa is required to stop the auto-fixer from removing them.
from telegram_bot.admin import cmd_stats  # noqa: E402,F401
from telegram_bot.commands import (  # noqa: E402,F401
    _CMD_HANDLER_NAMES,
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
    cmd_overview,
    cmd_parse,
    cmd_portfolio,
    cmd_predict,
    cmd_rates,
    cmd_rebalance,
    cmd_rebalance_auto,
    cmd_repo,
    cmd_rv,
    cmd_scenario,
    cmd_start,
    cmd_stress,
    cmd_top,
    cmd_unwatch,
    cmd_usd,
    cmd_watch,
    cmd_watchlist,
)
from telegram_bot.handler_state import pending_edit as _pending_edit  # noqa: E402,F401
from telegram_bot.menus import (  # noqa: E402,F401
    _BUY_MENU,
    _DESK_MENU,
    _OVERVIEW_MENU,
    _PORTFOLIO_MENU,
    HELP_TEXT,
    MENU_INTRO,
    _main_menu_kb,
)
from telegram_bot.settings import cmd_set, cmd_settings  # noqa: E402,F401
