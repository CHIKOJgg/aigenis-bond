"""Bot Pro-gating: inline buttons must not bypass the subscription gate.

SubscriptionMiddleware only sees messages, so callback bridges must gate
PRO commands themselves. These tests assert that the gating contract holds:
every Pro cmd_* button / page:* callback is wired to the gate.
"""

from __future__ import annotations

import telegram_bot.commands as c
import telegram_bot.middleware as mw


def test_pro_cmds_match_middleware_gate():
    # Every cmd_* callback that is Pro-gated in cb_generic must be listed in
    # PRO_COMMANDS; every Pro command reachable from a button must be gated.
    from telegram_bot.menus import _BUY_MENU, _DESK_MENU, _PORTFOLIO_MENU

    buttons = []
    for _title, kb in (_DESK_MENU, _BUY_MENU, _PORTFOLIO_MENU):
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("cmd_"):
                    buttons.append(btn.callback_data)

    for data in buttons:
        cmd = data.removeprefix("cmd_")
        if cmd in mw.PRO_COMMANDS:
            assert data in c._CMD_HANDLER_NAMES, f"Pro button {data} not dispatched"
        else:
            assert cmd in mw._ALWAYS_ALLOWED, f"button {data} neither Pro nor allowed"

    for data in c._CMD_HANDLER_NAMES:
        cmd = data.removeprefix("cmd_")
        if cmd in mw.PRO_COMMANDS:
            assert cmd in mw.PRO_COMMANDS


def test_all_pro_commands_have_matching_callback_names():
    # Every cmd_* button in the dispatcher must be either Pro-gated or in the
    # always-allowed set; anything else would silently bypass the gate.
    for name in c._CMD_HANDLER_NAMES:
        cmd = name.removeprefix("cmd_")
        assert cmd in mw.PRO_COMMANDS or cmd in mw._ALWAYS_ALLOWED, (
            f"{name} is neither Pro nor always-allowed"
        )


def test_paginate_gates_pro_prefixes():
    # page:carry:* / page:rv:* are Pro; top/usd/byn are free.
    pro_prefixes = {"carry", "rv"}
    free_prefixes = {"top", "usd", "byn"}
    for p in pro_prefixes:
        assert p in mw.PRO_COMMANDS
    for p in free_prefixes:
        assert p not in mw.PRO_COMMANDS


def test_gate_pro_callback_denies_free_user(monkeypatch):
    async def fake_tier(_uid):
        return False

    class FakeMessage:
        async def answer(self, *a, **kw):
            return None

    class FakeQuery:
        def __init__(self) -> None:
            self.from_user = type("U", (), {"id": 1})()
            self.message = FakeMessage()

        async def answer(self, *a, **kw):
            return None

    monkeypatch.setattr(mw, "user_has_pro_tier", fake_tier)
    q = FakeQuery()

    async def run():
        return await mw.gate_pro_callback(q)

    import asyncio

    assert asyncio.run(run()) is False


def test_gate_pro_callback_allows_pro_user(monkeypatch):
    async def fake_tier(_uid):
        return True

    class FakeQuery:
        def __init__(self) -> None:
            self.from_user = type("U", (), {"id": 1})()
            self.message = type("M", (), {})()

        async def answer(self, *a, **kw):
            raise AssertionError("pro user should not be denied")

    monkeypatch.setattr(mw, "user_has_pro_tier", fake_tier)
    q = FakeQuery()

    import asyncio

    assert asyncio.run(mw.gate_pro_callback(q)) is True
