"""Tests for the new value actions in the Telegram bond picker:
plain-language "should I buy?" verdict and coupon income.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from notifications.alerts_repository import list_rules
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, BondORM, UserORM
from telegram_bot.bond_picker import _bond_card_text, _run_bond_action, cb_alert_set
from telegram_bot.subscriptions import get_or_create_user_by_telegram


class _FakeUser:
    def __init__(self, uid: int) -> None:
        self.id = uid


class _FakeMessage:
    def __init__(self) -> None:
        self.last_text: str | None = None

    async def edit_text(self, text, parse_mode=None, reply_markup=None):  # noqa: ARG002
        self.last_text = text


class _FakeCallback:
    def __init__(self, data: str, uid: int) -> None:
        self.data = data
        self.from_user = _FakeUser(uid)
        self.message = _FakeMessage()
        self.answered = False

    async def answer(self, *args, **kwargs):  # noqa: ARG002
        self.answered = True


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


def test_analysis_free_user_locks_details():
    async def run():
        await _seed_bond()
        cb = _FakeCallback("bondact:OP-1:analysis", uid=999999)  # unknown -> free
        await _run_bond_action(cb, "OP-1", "analysis")
        text = cb.message.last_text
        assert "Рейтинг:" in text
        assert "Вердикт:" in text
        assert "Pro" in text  # locked hint
        assert "Почему стоит:" not in text  # details hidden

    _run(run)


def test_analysis_pro_user_shows_details():
    async def run():
        await _seed_bond()
        await _make_pro_user(555)
        cb = _FakeCallback("bondact:OP-1:analysis", uid=555)
        await _run_bond_action(cb, "OP-1", "analysis")
        text = cb.message.last_text
        assert "Вердикт:" in text
        # USD gov bond with 12% yield -> has strengths shown to Pro.
        assert "Почему стоит:" in text

    _run(run)


def test_income_gated_for_free_and_shown_for_pro():
    async def run():
        await _seed_bond()
        await _make_pro_user(777)

        # Free -> paywall.
        cb_free = _FakeCallback("bondact:OP-1:income", uid=888888)
        await _run_bond_action(cb_free, "OP-1", "income")
        assert "Pro" in cb_free.message.last_text

        # Pro -> real income numbers.
        cb_pro = _FakeCallback("bondact:OP-1:income", uid=777)
        await _run_bond_action(cb_pro, "OP-1", "income")
        text = cb_pro.message.last_text
        assert "Купонный доход" in text
        assert "год" in text
        assert "Ближайшие купоны" in text

    _run(run)


def test_bond_card_shows_key_facts():
    async def run():
        await _seed_bond()
        card = await _bond_card_text("OP-1")
        assert "OP-1" in card
        assert "USD" in card
        assert "доходность 12%" in card
        assert "купон 10%" in card
        assert "Рейтинг:" in card

    _run(run)


def test_bond_card_missing_bond_is_graceful():
    async def run():
        card = await _bond_card_text("NOPE-999")
        assert "NOPE-999" in card
        assert "Выберите действие" in card

    _run(run)


def test_watchprice_gated_for_free_and_presets_for_pro():
    async def run():
        await _seed_bond()
        await _make_pro_user(1001)

        cb_free = _FakeCallback("bondact:OP-1:watchprice", uid=222222)
        await _run_bond_action(cb_free, "OP-1", "watchprice")
        assert "Pro" in cb_free.message.last_text

        cb_pro = _FakeCallback("bondact:OP-1:watchprice", uid=1001)
        await _run_bond_action(cb_pro, "OP-1", "watchprice")
        assert "Следить за OP-1" in cb_pro.message.last_text

    _run(run)


def test_alert_set_creates_rule_for_pro():
    async def run():
        await _seed_bond()
        await _make_pro_user(1002)

        cb = _FakeCallback("alertset:OP-1:price:below:95.00", uid=1002)
        await cb_alert_set(cb)
        assert "Алерт создан" in cb.message.last_text

        async with session_scope() as s:
            user = await get_or_create_user_by_telegram(s, 1002)
            rules = await list_rules(s, user.id)
        assert len(rules) == 1
        assert rules[0].internal_id == "OP-1"
        assert rules[0].metric == "price"
        assert rules[0].direction == "below"
        assert rules[0].threshold == Decimal("95.00")

    _run(run)


def test_alert_set_deduplicates_identical_rule():
    async def run():
        await _seed_bond()
        await _make_pro_user(1003)

        cb1 = _FakeCallback("alertset:OP-1:price:below:95.00", uid=1003)
        await cb_alert_set(cb1)
        assert "Алерт создан" in cb1.message.last_text

        cb2 = _FakeCallback("alertset:OP-1:price:below:95.00", uid=1003)
        await cb_alert_set(cb2)
        assert "уже есть" in cb2.message.last_text

        async with session_scope() as s:
            user = await get_or_create_user_by_telegram(s, 1003)
            rules = await list_rules(s, user.id)
        assert len(rules) == 1

    _run(run)


def test_alert_set_blocked_for_free_user():
    async def run():
        await _seed_bond()
        cb = _FakeCallback("alertset:OP-1:price:below:95.00", uid=333333)
        await cb_alert_set(cb)
        # No rule persisted for a free user.
        async with session_scope() as s:
            user = await get_or_create_user_by_telegram(s, 333333)
            rules = await list_rules(s, user.id)
        assert rules == []

    _run(run)
