"""Tests for portfolio positions in the Telegram bot (view / add / remove)."""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, BondORM, UserORM
from telegram_bot.handler_state import pending_position
from telegram_bot.positions import (
    cb_pos_add,
    cb_pos_del,
    cb_positions_menu,
    on_position_amount,
)


class _FakeUser:
    def __init__(self, uid: int) -> None:
        self.id = uid


class _FakeMessage:
    def __init__(self, uid: int, text: str | None = None) -> None:
        self.from_user = _FakeUser(uid)
        self.text = text
        self.answers: list[str] = []
        self.last_text: str | None = None

    async def edit_text(self, text, parse_mode=None, reply_markup=None):  # noqa: ARG002
        self.last_text = text

    async def answer(self, text, parse_mode=None, reply_markup=None):  # noqa: ARG002
        self.answers.append(text)
        self.last_text = text


class _FakeCallback:
    def __init__(self, data: str, uid: int) -> None:
        self.data = data
        self.from_user = _FakeUser(uid)
        self.message = _FakeMessage(uid)
        self.alerts: list[str] = []

    async def answer(self, text=None, show_alert=False):  # noqa: ARG002
        if text:
            self.alerts.append(text)


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _run(coro_fn):
    async def wrapper():
        await _ensure_schema()
        try:
            await coro_fn()
        finally:
            pending_position.clear()
            await dispose()

    asyncio.run(wrapper())


async def _seed_bond():
    async with session_scope() as s:
        s.add(
            BondORM(
                internal_id="OP-1",
                name="USD Gov Bond",
                currency="USD",
                yield_to_maturity=12.0,
                coupon_rate=10.0,
                coupon_frequency=2,
                price=100.0,
                status="active",
                issuer="Министерство финансов",
                maturity_date=date.today().replace(year=date.today().year + 2),
                fetched_at=datetime.now(UTC),
            )
        )


async def _seed_byn_bond():
    async with session_scope() as s:
        s.add(
            BondORM(
                internal_id="OP-2",
                name="BYN Gov Bond",
                currency="BYN",
                yield_to_maturity=9.0,
                coupon_rate=8.0,
                coupon_frequency=2,
                price=100.0,
                status="active",
                issuer="Министерство финансов",
                maturity_date=date.today().replace(year=date.today().year + 3),
                fetched_at=datetime.now(UTC),
            )
        )


async def _make_pro_user(telegram_id: int):
    async with session_scope() as s:
        s.add(
            UserORM(
                email=f"tg_{telegram_id}@telegram.local",
                name="Pro",
                telegram_id=telegram_id,
                password_hash="x",
                role="user",
                is_active=True,
                is_verified=False,
                subscription_tier="pro",
                subscription_expires_at=datetime.now(UTC) + timedelta(days=30),
                trial_end=None,
            )
        )


def test_positions_menu_gated_for_free_user():
    async def run():
        await _seed_bond()
        cb = _FakeCallback("positions:menu", uid=999999)
        await cb_positions_menu(cb)
        assert "Pro" in cb.message.last_text

    _run(run)


def test_positions_menu_empty_for_pro():
    async def run():
        await _seed_bond()
        await _make_pro_user(2001)
        cb = _FakeCallback("positions:menu", uid=2001)
        await cb_positions_menu(cb)
        assert "пуст" in cb.message.last_text

    _run(run)


def test_add_position_flow_persists_and_shows_income():
    async def run():
        await _seed_bond()
        await _make_pro_user(2002)

        add_cb = _FakeCallback("pos:add:OP-1", uid=2002)
        await cb_pos_add(add_cb)
        assert pending_position.get(2002) == "OP-1"

        msg = _FakeMessage(2002, text="1000")
        await on_position_amount(msg)
        assert 2002 not in pending_position
        joined = " ".join(msg.answers)
        assert "Добавлено" in joined
        assert "Купонный доход" in joined
        assert "OP-1" in joined

    _run(run)


def test_add_position_rejects_bad_amount():
    async def run():
        await _seed_bond()
        await _make_pro_user(2003)
        pending_position[2003] = "OP-1"
        msg = _FakeMessage(2003, text="abc")
        await on_position_amount(msg)
        assert "Не понял сумму" in " ".join(msg.answers)

    _run(run)


def test_add_position_blocked_for_free_user():
    async def run():
        await _seed_bond()
        cb = _FakeCallback("pos:add:OP-1", uid=444444)
        await cb_pos_add(cb)
        assert 444444 not in pending_position
        assert cb.alerts  # answered with an alert

    _run(run)


def test_mixed_currency_warning():
    async def run():
        await _seed_bond()
        await _seed_byn_bond()
        await _make_pro_user(2005)

        pending_position[2005] = "OP-1"
        await on_position_amount(_FakeMessage(2005, text="1000"))
        pending_position[2005] = "OP-2"
        await on_position_amount(_FakeMessage(2005, text="2000"))

        cb = _FakeCallback("positions:menu", uid=2005)
        await cb_positions_menu(cb)
        assert "разные валюты" in cb.message.last_text
        assert "USD" in cb.message.last_text
        assert "BYN" in cb.message.last_text

    _run(run)


def test_remove_position():
    async def run():
        await _seed_bond()
        await _make_pro_user(2004)

        pending_position[2004] = "OP-1"
        await on_position_amount(_FakeMessage(2004, text="500"))

        del_cb = _FakeCallback("pos:del:OP-1", uid=2004)
        await cb_pos_del(del_cb)
        assert "пуст" in del_cb.message.last_text

    _run(run)
