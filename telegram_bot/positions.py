"""Portfolio positions in the Telegram bot (Pro).

Lets a user track what they actually hold: view holdings with coupon income,
add a position from a bond card (amount entered as a text reply) and remove it.
Positions are keyed by ``users.id`` (shared with the web app), resolved from the
Telegram id via :func:`get_or_create_user_by_telegram`.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from portfolio.income import portfolio_income
from portfolio.positions_repository import (
    list_positions,
    remove_position,
    upsert_position,
)
from scraper.db import session_scope
from telegram_bot.handler_state import pending_position
from telegram_bot.helpers import bonds_for_bot, fmt_num, user_id_from_message
from telegram_bot.subscriptions import (
    get_or_create_user_by_telegram,
    get_tier_by_telegram,
    meets_tier,
)

router = Router()


async def _is_pro(telegram_id: int) -> bool:
    return meets_tier(await get_tier_by_telegram(telegram_id), "pro")


def _pro_upsell() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "⭐ <b>Мой портфель — функция Pro.</b>\n\n"
        "Ведите реальные позиции, следите за купонным доходом и доходностью "
        "на вложенное. Оформите подписку через Telegram Stars: /subscribe"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")]]
    )
    return text, kb


async def _positions_view(telegram_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Build the 'my positions' message: holdings, income, per-position removal."""
    bonds = {b.internal_id: b for b in await bonds_for_bot()}
    async with session_scope() as session:
        user = await get_or_create_user_by_telegram(session, telegram_id)
        positions = await list_positions(session, user.id)

    if not positions:
        text = (
            "💼 <b>Мой портфель пуст.</b>\n\n"
            "Откройте облигацию (🔍 Облигации) и нажмите «➕ В портфель», "
            "чтобы добавить свою позицию и видеть купонный доход."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔍 К облигациям", callback_data="bonds:menu")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
            ]
        )
        return text, kb

    holdings = []
    for p in positions:
        b = bonds.get(p.internal_id)
        holdings.append(
            {
                "internal_id": p.internal_id,
                "amount": p.amount,
                "name": b.name if b else p.internal_id,
                "currency": b.currency if b else None,
                "coupon_rate": b.coupon_rate if b else None,
                "coupon_frequency": b.coupon_frequency if b else None,
                "maturity_date": b.maturity_date if b else None,
                "price": b.price if b else None,
            }
        )

    inc = portfolio_income(holdings)
    currencies = {h["currency"] for h in holdings if h["currency"]}
    lines = ["💼 <b>Мой портфель</b>\n"]
    for h in holdings:
        cur = f" {h['currency']}" if h["currency"] else ""
        lines.append(
            f"• <code>{h['internal_id']}</code> {h['name']} — "
            f"<b>{fmt_num(h['amount'])}{cur}</b>"
        )
    lines.append("")
    lines.append(f"Вложено: <b>{fmt_num(inc['total_invested'])}</b>")
    lines.append(
        f"Купонный доход: <b>~{fmt_num(inc['annual_income'])}/год</b> "
        f"({inc['yield_on_cost']}% на вложенное)"
    )
    nxt = inc.get("next_payment")
    if nxt:
        lines.append(f"Ближайшая выплата: <b>{fmt_num(nxt['amount'])}</b> — {nxt['date']}")
    if len(currencies) > 1:
        lines.append(
            "\n⚠️ В портфеле разные валюты — итоговые суммы сложены без конвертации."
        )

    rows = [
        [
            InlineKeyboardButton(
                text=f"🗑 Убрать {p.internal_id}", callback_data=f"pos:del:{p.internal_id}"
            )
        ]
        for p in positions
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить", callback_data="bonds:menu")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("positions"))
async def cmd_positions(message: Message) -> None:
    uid = user_id_from_message(message)
    if not await _is_pro(uid):
        text, kb = _pro_upsell()
        await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    text, kb = await _positions_view(uid)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(lambda c: c.data == "positions:menu")
async def cb_positions_menu(callback_query) -> None:
    uid = callback_query.from_user.id if callback_query.from_user else 0
    if not await _is_pro(uid):
        text, kb = _pro_upsell()
        await callback_query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        await callback_query.answer()
        return
    text, kb = await _positions_view(uid)
    await callback_query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("pos:add:"))
async def cb_pos_add(callback_query) -> None:
    uid = callback_query.from_user.id if callback_query.from_user else 0
    iid = callback_query.data.split(":", 2)[2]
    if not await _is_pro(uid):
        await callback_query.answer("Мой портфель доступен в Pro — /subscribe", show_alert=True)
        return
    pending_position[uid] = iid
    await callback_query.message.edit_text(
        f"➕ <b>Добавить {iid} в портфель</b>\n\n"
        "Отправьте сумму вложения одним сообщением (например: <code>1000</code>).\n"
        "Или нажмите «❌ Отмена».",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="pos:cancel")]]
        ),
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data == "pos:cancel")
async def cb_pos_cancel(callback_query) -> None:
    uid = callback_query.from_user.id if callback_query.from_user else 0
    pending_position.pop(uid, None)
    await callback_query.answer("Отменено")
    text, kb = await _positions_view(uid)
    await callback_query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith("pos:del:"))
async def cb_pos_del(callback_query) -> None:
    uid = callback_query.from_user.id if callback_query.from_user else 0
    iid = callback_query.data.split(":", 2)[2]
    if not await _is_pro(uid):
        await callback_query.answer("Доступно в Pro — /subscribe", show_alert=True)
        return
    async with session_scope() as session:
        user = await get_or_create_user_by_telegram(session, uid)
        await remove_position(session, user.id, iid)
    text, kb = await _positions_view(uid)
    await callback_query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback_query.answer(f"Убрано: {iid}")


@router.message(lambda m: user_id_from_message(m) in pending_position)
async def on_position_amount(message: Message) -> None:
    uid = user_id_from_message(message)
    iid = pending_position.pop(uid)
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        await message.answer("✏️ Ввод отменён — команда не применена. Повторите её.")
        return
    try:
        amount = Decimal(raw.replace(",", ".").replace(" ", ""))
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer("❌ Не понял сумму. Введите число, например 1000. Повторите: /positions")
        return
    async with session_scope() as session:
        user = await get_or_create_user_by_telegram(session, uid)
        await upsert_position(session, user.id, iid, amount)
    text, kb = await _positions_view(uid)
    await message.answer(
        f"✅ Добавлено: <b>{iid}</b> на <b>{fmt_num(amount)}</b>.",
        parse_mode=ParseMode.HTML,
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)
