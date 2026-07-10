"""Settings / preset handlers for the Telegram bot.

Implements a lightweight FSM-lite for editing portfolio preferences via inline
buttons and text replies. Shared per-user edit state lives in
`telegram_bot.handler_state`.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from scraper.db import session_scope
from telegram_bot.handler_state import pending_edit
from telegram_bot.helpers import user_id_from_message
from telegram_bot.menus import _home_kb

router = Router()

_PRESETS = {
    "Conserv": (0.3, 0.5, 0.1, 0.1),
    "Balanced": (0.5, 0.3, 0.2, 0.0),
    "Aggressv": (0.7, 0.1, 0.1, 0.1),
    "Metals++": (0.2, 0.1, 0.6, 0.1),
}


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    uid = user_id_from_message(message)
    async with session_scope() as session:
        from telegram_bot.preferences_repository import get_preferences

        prefs = await get_preferences(session, uid)
    shares = (
        f"USD: {prefs.share_usd:.0%}, BYN: {prefs.share_byn:.0%}, "
        f"Metals: {prefs.share_metals:.0%}, EUR: {prefs.share_eur:.0%}"
    )
    text = (
        f"<b>⚙️ Настройки портфеля</b>\n\n"
        f"Капитал: <code>{prefs.initial_capital}</code>\n"
        f"Пополнение/мес: <code>{prefs.monthly_contribution}</code>\n"
        f"Прогноз USD/BYN: <code>{prefs.usd_byn_forecast}</code>\n"
        f"Доли: {shares}\n"
        f"Стратегия: <b>{prefs.strategy}</b>\n\n"
        f"Выберите пресет распределения или используйте /set:"
    )
    rows = []
    for label, (usd, byn, metals, eur) in _PRESETS.items():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{label} ({usd:.0%}/{byn:.0%}/{metals:.0%}/{eur:.0%})",
                    callback_data=f"preset:{label}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(text="Капитал", callback_data="edit:capital"),
            InlineKeyboardButton(text="Пополнение", callback_data="edit:contribution"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="1k", callback_data="setcap:1000"),
            InlineKeyboardButton(text="10k", callback_data="setcap:10000"),
            InlineKeyboardButton(text="50k", callback_data="setcap:50000"),
            InlineKeyboardButton(text="100k", callback_data="setcap:100000"),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    )
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith("preset:"))
async def cb_preset(callback_query) -> None:
    uid = callback_query.from_user.id if callback_query.from_user else 0
    label = callback_query.data.split(":", 1)[1]
    shares = _PRESETS[label]
    async with session_scope() as session:
        from telegram_bot.preferences_repository import get_preferences, upsert_preferences

        prefs = await get_preferences(session, uid)
        prefs.share_usd = shares[0]
        prefs.share_byn = shares[1]
        prefs.share_metals = shares[2]
        prefs.share_eur = shares[3]
        prefs.strategy = label
        await upsert_preferences(session, prefs)
    await callback_query.message.edit_text(
        f"✅ Применён пресет <b>{label}</b>: "
        f"USD {shares[0]:.0%}, BYN {shares[1]:.0%}, "
        f"Metals {shares[2]:.0%}, EUR {shares[3]:.0%}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ К настройкам", callback_data="menu:settings")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
            ]
        ),
    )
    await callback_query.answer()


_EDIT_HINTS = {
    "capital": ("капитал (например: 50000)", "число, напр. 50000"),
    "contribution": ("пополнение в месяц (например: 2000)", "число, напр. 2000"),
}


@router.callback_query(lambda c: c.data and c.data.startswith("edit:"))
async def cb_edit(callback_query) -> None:
    field = callback_query.data.split(":", 1)[1]
    if field == "cancel":
        pending_edit.pop(callback_query.from_user.id if callback_query.from_user else 0, None)
        await callback_query.answer("Отменено")
        await cmd_settings(callback_query.message)
        return
    uid = callback_query.from_user.id if callback_query.from_user else 0
    pending_edit[uid] = field
    label, example = _EDIT_HINTS.get(field, (field, "значение"))
    await callback_query.message.edit_text(
        f"✏️ <b>Введите {label}</b> и отправьте сообщением.\n"
        f"Пример: <code>{example}</code>\n"
        "Или нажмите «❌ Отмена».",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="edit:cancel")]
            ]
        ),
    )
    await callback_query.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    pending_edit.pop(user_id_from_message(message), None)
    await message.answer("✅ Режим ввода отменён.")


@router.callback_query(lambda c: c.data and c.data.startswith("setcap:"))
async def cb_setcap(callback_query) -> None:
    uid = callback_query.from_user.id if callback_query.from_user else 0
    val = callback_query.data.split(":", 1)[1]
    _ok, text = await apply_setting(uid, "capital", val)
    await callback_query.message.answer(text, parse_mode=ParseMode.HTML, reply_markup=_home_kb())
    await callback_query.answer()


@router.message(lambda m: user_id_from_message(m) in pending_edit)
async def cb_pending_edit(message: Message) -> None:
    uid = user_id_from_message(message)
    field = pending_edit.pop(uid)
    if (message.text or "").strip().startswith("/"):
        await message.answer("✏️ Режим ввода отменён — команда не применена. Повторите её.")
        return
    _ok, text = await apply_setting(uid, field, (message.text or "").strip())
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=_home_kb())


async def apply_setting(uid: int, field: str, val_str: str) -> tuple[bool, str]:
    from telegram_bot.preferences_repository import get_preferences, upsert_preferences

    async with session_scope() as session:
        prefs = await get_preferences(session, uid)
        try:
            if field == "capital":
                prefs.initial_capital = Decimal(val_str.replace(",", "").replace(" ", ""))
            elif field == "contribution":
                prefs.monthly_contribution = Decimal(val_str.replace(",", "").replace(" ", ""))
            elif field == "strategy":
                prefs.strategy = val_str.capitalize()
            elif field in ("share_usd", "share_byn", "share_metals", "share_eur"):
                setattr(prefs, field, float(val_str))
                total = prefs.share_usd + prefs.share_byn + prefs.share_metals + prefs.share_eur
                if abs(total - 1.0) > 0.01:
                    return False, f"⚠️ Сумма долей {total:.0%}, рекомендуется 100%"
            else:
                return False, f"Неизвестное поле: {field}"
            await upsert_preferences(session, prefs)
        except (ValueError, InvalidOperation) as exc:
            return False, f"❌ Ошибка: {exc}"
    return True, f"✅ <b>{field}</b> = {val_str}"


@router.message(Command("set"))
async def cmd_set(message: Message) -> None:
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "Использование: /set <field> <value>\n\n"
            "Поля: capital, contribution, strategy (Aggressive/Balanced/Conservative), "
            "share_usd, share_byn, share_metals, share_eur (0.0–1.0)"
        )
        return
    field, val_str = args[1].lower(), args[2]
    uid = user_id_from_message(message)
    _ok, text = await apply_setting(uid, field, val_str)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=_home_kb())
