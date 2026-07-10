"""Bond picker: discover bonds without knowing IDs, then act on them.

Handles the `bonds:`, `bond:` and `bondact:` callback families and the pro-gated
predict/duration/repo actions. Tier enforcement reuses the subscription helpers.
"""
from __future__ import annotations

from decimal import Decimal

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select as sa_select

from desk import duration as desk_duration
from desk import repo as desk_repo
from ml.repository import predictions_for_bond
from scraper.db import session_scope
from scraper.orm import BondORM
from telegram_bot.handler_state import BOND_PAGE
from telegram_bot.helpers import (
    fetch_all_bonds,
    fetch_bonds_by_currency,
)
from telegram_bot.preferences_repository import add_to_watchlist, remove_from_watchlist
from telegram_bot.subscriptions import get_tier_by_telegram, meets_tier

router = Router()


async def _bond_name(session, iid: str) -> str:
    return (
        await session.execute(sa_select(BondORM.name).where(BondORM.internal_id == iid))
    ).scalar_one_or_none() or iid


@router.callback_query(lambda c: c.data == "bonds:menu")
async def cb_bonds_menu(callback_query) -> None:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💵 USD", callback_data="bonds:list:usd:0"),
                InlineKeyboardButton(text="🇧🇾 BYN", callback_data="bonds:list:byn:0"),
            ],
            [
                InlineKeyboardButton(text="🪙 Золото", callback_data="bonds:list:xau:0"),
                InlineKeyboardButton(text="🪙 Серебро", callback_data="bonds:list:xag:0"),
            ],
            [InlineKeyboardButton(text="📋 Все облигации", callback_data="bonds:list:all:0")],
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="menu:main")],
        ]
    )
    await callback_query.message.edit_text(
        "🔍 <b>Выбор облигации</b>\n\nСначала выберите валюту, затем нужную облигацию из списка.",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    await callback_query.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("bonds:list:"))
async def cb_bonds_list(callback_query) -> None:
    _, _, key, page_s = callback_query.data.split(":")
    page = int(page_s)
    if key == "all":
        bonds = await fetch_all_bonds()
    else:
        bonds = await fetch_bonds_by_currency(key.upper())
    if not bonds:
        await callback_query.answer("Нет облигаций. Сначала запустите /parse", show_alert=True)
        return
    total_pages = max(1, (len(bonds) + BOND_PAGE - 1) // BOND_PAGE)
    page_slice = bonds[page * BOND_PAGE : (page + 1) * BOND_PAGE]
    rows = []
    for b in page_slice:
        label = f"{b.internal_id} — {(b.name or '')[:22]}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"bond:{b.internal_id}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"bonds:list:{key}:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"bonds:list:{key}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅️ Назад к валютам", callback_data="bonds:menu")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    text = f"🔍 <b>Облигации ({key.upper()})</b> — стр. {page + 1}/{total_pages}\nВыберите облигацию:"
    await callback_query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback_query.answer()


@router.callback_query(lambda c: c.data and (c.data.startswith("bond:") or c.data.startswith("bondact:")))
async def cb_bond(callback_query) -> None:
    data = callback_query.data
    if data.startswith("bondact:"):
        _, iid, action = data.split(":", 2)
        await _run_bond_action(callback_query, iid, action)
        return

    iid = data.split(":", 1)[1]
    async with session_scope() as session:
        name = await _bond_name(session, iid)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Прогноз", callback_data=f"bondact:{iid}:predict"),
                InlineKeyboardButton(text="⏱ Duration", callback_data=f"bondact:{iid}:duration"),
            ],
            [
                InlineKeyboardButton(text="🏦 РЕПО", callback_data=f"bondact:{iid}:repo"),
                InlineKeyboardButton(text="⭐ В избранное", callback_data=f"bondact:{iid}:watch"),
            ],
            [
                InlineKeyboardButton(text="🗑 Из избранного", callback_data=f"bondact:{iid}:unwatch"),
                InlineKeyboardButton(text="⬅️ К списку", callback_data="bonds:menu"),
            ],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )
    await callback_query.message.edit_text(
        f"🔍 <b>{iid}</b> — {name}\n\nЧто сделать с этой облигацией?",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    await callback_query.answer()


async def _run_bond_action(callback_query, iid: str, action: str) -> None:
    async with session_scope() as session:
        name = await _bond_name(session, iid)

    # Pro-gated actions reached via the bond picker (callbacks, not commands).
    if action in ("predict", "duration", "repo"):
        uid = callback_query.from_user.id if callback_query.from_user else 0
        tier = await get_tier_by_telegram(uid)
        if not meets_tier(tier, "pro"):
            back_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад к облигации", callback_data=f"bond:{iid}")],
                ]
            )
            await callback_query.message.edit_text(
                "⭐ <b>Эта функция доступна в подписке Pro / Enterprise.</b>\n\n"
                "Откройте прогнозы, duration и РЕПО по подписке через Telegram Stars.\n"
                "Нажмите /subscribe, чтобы выбрать тариф.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_kb,
            )
            await callback_query.answer()
            return

    if action == "predict":
        async with session_scope() as session:
            rows = await predictions_for_bond(session, iid, limit=1)
        if not rows:
            text = f"❌ По <code>{iid}</code> нет прогнозов. Сначала обучите ML-модель (/ml)."
        else:
            p = rows[0]
            expl = "\n".join(f"  • {e}" for e in (p.explanation or []))
            text = (
                f"<b>📈 Прогноз {iid}</b> ({name})\n"
                f"Решение: <b>{p.decision}</b> (conf {float(p.confidence):.2f})\n"
                f"Predicted YTM: {float(p.predicted_ytm) if p.predicted_ytm is not None else '—'}\n"
                f"Predicted return: {float(p.predicted_return_pct) if p.predicted_return_pct is not None else '—'}\n"
                f"Объяснение:\n{expl or '—'}"
            )
    elif action == "duration":
        from telegram_bot.helpers import bonds_for_bot

        bonds = await bonds_for_bot()
        bond = next((b for b in bonds if b.internal_id == iid), None)
        if bond is None:
            text = f"❌ Облигация <code>{iid}</code> не найдена."
        else:
            rep = desk_duration.duration_report(bond)
            lines = [
                f"<b>⏱ Duration — {iid}</b> ({bond.name})\n",
                f"Macaulay: {rep.macaulay_duration:.3f}",
                f"Modified: {rep.modified_duration:.3f}",
                f"Convexity: {rep.convexity:.3f}",
                f"DV01: {rep.dv01:.4f}\n",
                "<b>Key-rate durations:</b>",
            ]
            for tenor, krd in rep.key_rate_durations.items():
                lines.append(f"  {tenor}: {krd:.4f}")
            text = "\n".join(lines)
    elif action == "repo":
        from telegram_bot.helpers import bonds_for_bot

        bonds = await bonds_for_bot()
        bond = next((b for b in bonds if b.internal_id == iid), None)
        if bond is None:
            text = f"❌ Облигация <code>{iid}</code> не найдена."
        else:
            haircut = desk_repo.haircut_by_issuer(bond.issuer)
            deal = desk_repo.repo_deal(
                bond, notional=Decimal("1000"), haircut_pct=haircut, repo_rate_pct=5.0, tenor_days=30
            )
            text = (
                f"<b>🏦 РЕПО {iid}</b> ({bond.name})\n"
                f"Залог: {deal.collateral_value}\n"
                f"Haircut: {deal.haircut_pct}%\n"
                f"Кэш выдано: {deal.cash_lent}\n"
                f"Ставка: {deal.repo_rate_pct}%, тенор {deal.tenor_days}d\n"
                f"Проценты: {deal.accrued_interest}"
            )
    elif action in ("watch", "unwatch"):
        uid = callback_query.from_user.id if callback_query.from_user else 0
        async with session_scope() as session:
            if action == "watch":
                prefs = await add_to_watchlist(session, uid, iid)
                text = f"✅ <code>{iid}</code> ({name}) добавлен в избранное ({len(prefs.watchlist)} шт.)"
            else:
                await remove_from_watchlist(session, uid, iid)
                text = f"❌ <code>{iid}</code> ({name}) убран из избранного"
    else:
        text = "❌ Неизвестное действие."

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к облигации", callback_data=f"bond:{iid}")],
            [InlineKeyboardButton(text="🔍 К списку облигаций", callback_data="bonds:menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )
    await callback_query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb)
    await callback_query.answer()
