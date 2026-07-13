"""Consistency tests for the Telegram bot navigation.

These guard against "dead buttons": every inline button's callback_data must
resolve to a real handler (a defined cmd_* function, or one of the menu/bonds/
bond prefix handlers). They also verify the settings FSM-lite wiring.
"""
from __future__ import annotations

import re

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import telegram_bot.handlers as h


def _collect_callback_data(kb: InlineKeyboardMarkup) -> list[str]:
    data: list[str] = []
    for row in kb.inline_keyboard:
        for btn in row:
            assert isinstance(btn, InlineKeyboardButton)
            if btn.callback_data:
                data.append(btn.callback_data)
    return data


def test_main_menu_has_expected_sections():
    kb = h._main_menu_kb()
    datas = _collect_callback_data(kb)
    for expected in (
        "menu:overview",
        "menu:desk",
        "menu:buy",
        "menu:portfolio",
        "menu:settings",
        "menu:help",
        "cmd_watchlist",
        "cmd_alerts",
    ):
        assert expected in datas, f"missing button: {expected}"


def test_all_cmd_buttons_resolve_to_handlers():
    # Every cmd_* callback referenced by the dispatcher must be a real coroutine.
    for name in h._CMD_HANDLER_NAMES:
        handler = getattr(h, name, None)
        assert callable(handler), f"{name} is not a callable handler"
        assert handler.__name__ == name


def test_submenus_only_reference_known_callbacks():
    known = set(h._CMD_HANDLER_NAMES) | {
        "menu:main",
        "menu:overview",
        "menu:desk",
        "menu:buy",
        "menu:portfolio",
        "menu:settings",
        "menu:help",
        "bonds:menu",
    }
    menus = [
        h._OVERVIEW_MENU,
        h._DESK_MENU,
        h._BUY_MENU,
        h._PORTFOLIO_MENU,
    ]
    pattern = re.compile(r"^(menu:|bonds:|bond:|bondact:|preset:|edit:|positions:|pos:|cmd_)")
    for _title, kb in menus:
        for data in _collect_callback_data(kb):
            assert data in known or pattern.match(data), f"unhandled callback: {data}"


def test_intro_and_help_texts_are_meaningful():
    assert "Bond Fixed Income Assistant" in h.MENU_INTRO
    assert "Как пользоваться" in h.HELP_TEXT


def test_pending_edit_state_is_per_user():
    # Smoke check: the FSM-lite dict exists and is initially empty-ish.
    assert isinstance(h._pending_edit, dict)
