from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, ExceptionTypeFilter
from aiogram.types import (
    BufferedInputFile,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger
from sqlalchemy import desc, select

from desk import carry as desk_carry
from desk import duration as desk_duration
from desk import relative_value as desk_rv
from desk import repo as desk_repo
from desk import stress as desk_stress
from desk import yield_curve as desk_curve
from desk.repository import latest_rv_signals, latest_stress_runs
from forecast.engine import forecast_horizons
from ml.repository import latest_model_version, predictions_for_bond
from notifications.fx_repository import latest_fx, latest_metal
from notifications.repository import list_recent
from portfolio.optimizer import allocate, rebalance
from portfolio.positions_repository import list_positions, total_value
from portfolio.rebalance import build_plan
from portfolio.scenarios import run_all_scenarios
from recommendations.engine import recommend_bonds
from scoring.engine import score_bond
from scoring.repository import get_score, top_scores
from scraper import repositories
from scraper.db import session_scope
from scraper.models import Bond
from scraper.orm import BondORM
from telegram_bot.helpers import (
    bonds_for_bot,
    fetch_all_bonds,
    fetch_bonds_by_currency,
    fetch_bonds_with_history,
    paginate_kb,
    parse_bond_args,
    parse_funding_rate,
    user_id_from_message,
)
from telegram_bot.preferences_repository import add_to_watchlist, remove_from_watchlist
from visualization.charts import (
    plot_capital_forecast,
    plot_portfolio_pie,
    plot_yield_distribution,
)

router = Router()
_PAGE_SIZE = 10
_BOND_PAGE = 8
_parse_lock = asyncio.Lock()

# Per-user state for inline settings editing (lightweight FSM, no storage needed)
_pending_edit: dict[int, str] = {}

MENU_INTRO = (
    "👋 <b>Bond Fixed Income Assistant</b>\n\n"
    "🤖 Я помогаю анализировать облигации, подбирать лучшие для покупки, "
    "строить портфель и следить за рынком.\n\n"
    "⬇️ Выберите раздел в меню ниже. Если непонятно, что делать — "
    "нажмите <b>«🆘 Как пользоваться»</b>."
)

HELP_TEXT = (
    "🆘 <b>Как пользоваться ботом</b>\n\n"
    "1️⃣ <b>Данные.</b> Если облигаций ещё нет — нажмите «🚀 Старт парсинга» "
    "(или /parse). Это загрузит облигации и курсы с aigenis.by / НБ РБ.\n"
    "2️⃣ <b>📊 Обзор рынка</b> — TOP облигаций, списки по валютам, курсы, кривая доходности.\n"
    "3️⃣ <b>🔬 Аналитика</b> — Relative Value (дорого/дёшево), duration, carry, РЕПО, стресс-тесты.\n"
    "4️⃣ <b>🤖 Рекомендации</b> — что купить сейчас, ML-прогнозы по облигациям.\n"
    "5️⃣ <b>💼 Портфель</b> — прогноз капитала, ребалансировка, сценарный анализ.\n"
    "6️⃣ <b>⚙️ Настройки</b> — задайте капитал и доли валют (есть готовые пресеты).\n"
    "7️⃣ <b>🔍 Выбрать облигацию</b> — есть в каждом разделе: найдите нужную по валюте/названию "
    "и получите по ней прогноз, duration или добавьте в избранное. ID вводить не нужно!\n\n"
    "💡 Команды также можно вводить вручную: /top, /buy, /predict OP-51, /settings …"
)


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Обзор рынка", callback_data="menu:overview")],
            [InlineKeyboardButton(text="🔬 Аналитика (Desk)", callback_data="menu:desk")],
            [InlineKeyboardButton(text="🤖 Рекомендации", callback_data="menu:buy")],
            [InlineKeyboardButton(text="💼 Портфель", callback_data="menu:portfolio")],
            [
                InlineKeyboardButton(text="👀 Избранное", callback_data="cmd_watchlist"),
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings"),
            ],
            [
                InlineKeyboardButton(text="🔔 Алерты", callback_data="cmd_alerts"),
                InlineKeyboardButton(text="🆘 Как пользоваться", callback_data="menu:help"),
            ],
            [
                InlineKeyboardButton(text="⭐ Подписка", callback_data="stars:menu"),
            ],
        ]
    )


async def _show_main_menu(message) -> None:
    await message.answer(MENU_INTRO, parse_mode=ParseMode.HTML, reply_markup=_main_menu_kb())

# ---------------------------------------------------------------------------
# Callback pagination
# ---------------------------------------------------------------------------


@router.callback_query(lambda c: c.data and c.data.startswith("page:"))
async def cb_paginate(callback_query) -> None:
    parts = callback_query.data.split(":")
    prefix, page_str = parts[1], parts[2]
    page = int(page_str)
    dispatch = {
        "top": cmd_top,
        "usd": cmd_usd,
        "byn": cmd_byn,
        "carry": cmd_carry,
        "rv": cmd_rv,
    }
    handler = dispatch.get(prefix)
    if handler:
        if prefix in ("top", "carry", "rv"):
            await handler(callback_query.message, page=page)
        else:
            await handler(callback_query.message)
    await callback_query.answer()


# ---------------------------------------------------------------------------
# Start / Help
# ---------------------------------------------------------------------------


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    unlocked = await _is_unlocked(message)
    if not unlocked:
        await message.answer(
            "👋 <b>Bond Fixed Income Assistant</b>\n\n"
            "🔒 База облигаций пока пуста.\n"
            "Нажмите <b>🚀 Старт парсинга</b> (или отправьте /parse), чтобы загрузить "
            "облигации и курсы валют с aigenis.by / НБ РБ. После этого откроются все команды.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Старт парсинга", callback_data="cmd_parse")]
                ]
            ),
        )
        return

    await _show_main_menu(message)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await _show_main_menu(message)


# ---------------------------------------------------------------------------
# Parse gate: until parsing is done, user can only run /parse (enforced by
# telegram_bot.middleware.ParseLockMiddleware). Unlock state is derived from
# the DB (presence of bonds), so it survives process restarts.
# ---------------------------------------------------------------------------


def _user_id(message: Message) -> int:
    return message.from_user.id if message.from_user else 0


async def _is_unlocked(message: Message) -> bool:
    from telegram_bot.middleware import db_has_bonds

    return await db_has_bonds()


def _locked_message() -> str:
    from telegram_bot.middleware import locked_message_text

    return locked_message_text()


@router.message(Command("parse"))
async def cmd_parse(message: Message) -> None:
    if _parse_lock.locked():
        await message.answer("⏳ Парсинг уже запущен другим пользователем. Подождите окончания.")
        return
    async with _parse_lock:
        await message.answer(
            "🚀 Запускаю парсинг облигаций с aigenis.by (USD/BYN/EUR/RUB/CNY)…\n"
            "Это может занять несколько минут."
        )
        try:
            from scraper.fx import (
                fetch_and_save_bonds,
                fetch_and_save_metal_prices,
                fetch_and_save_rates,
            )

            summary = await fetch_and_save_bonds()
            rates = await fetch_and_save_rates()
            metals = await fetch_and_save_metal_prices()
        except Exception as exc:  # noqa: BLE001
            logger.exception("parse_failed", error=str(exc))
            await message.answer(f"❌ Ошибка парсинга: {exc}")
            return
        bonds_total = (summary or {}).get("listing_total", 0)
        bonds_ok = (summary or {}).get("details_ok", 0)
        bonds_err = (summary or {}).get("details_err", 0)
        rates_str = ", ".join(f"{k}={format(v, '.4f')}" for k, v in sorted(rates.items()))
        metals_str = ", ".join(f"{k}={format(v, '.2f')}" for k, v in sorted(metals.items()))
        await message.answer(
            "✅ Парсинг завершён.\n"
            f"Облигаций загружено: <b>{bonds_ok}</b> из {bonds_total} "
            f"(ошибок: {bonds_err}).\n"
            f"Курсы валют: {rates_str}\n"
            f"Металлы (BYN/oz): {metals_str}\n\n"
            "Готово! Выберите раздел в меню ниже 👇"
        )
        await _show_main_menu(message)


@router.message(Command("rates"))
async def cmd_rates(message: Message) -> None:
    if not await _is_unlocked(message):
        await message.answer(_locked_message())
        return
    async with session_scope() as session:
        lines = ["<b>💱 Курсы валют (НБ РБ)</b>\n"]
        for pair in ("USD/BYN", "EUR/BYN", "RUB/BYN", "CNY/BYN"):
            fx = await latest_fx(session, pair)
            if fx:
                lines.append(f"• {pair}: <b>{float(fx.rate):.4f}</b>  ({fx.observed_at:%Y-%m-%d})")
            else:
                lines.append(f"• {pair}: — (нет данных)")
        lines.append("\n<b>🪙 Драгметаллы (BYN/oz)</b>")
        for code, title in (("XAU", "Золото"), ("XAG", "Серебро"), ("XPT", "Платина")):
            m = await latest_metal(session, code)
            if m:
                lines.append(f"• {title} ({code}): <b>{float(m.price):.2f}</b>")
            else:
                lines.append(f"• {title} ({code}): — (нет данных)")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Callback bridges
# ---------------------------------------------------------------------------

# Allowed `cmd_*` inline buttons. Handlers are resolved lazily via globals() at
# call time so this set can be defined before the handler functions below.
_CMD_HANDLER_NAMES = {
    "cmd_desk", "cmd_top", "cmd_portfolio", "cmd_curve", "cmd_buy", "cmd_forecast",
    "cmd_rates", "cmd_parse", "cmd_overview", "cmd_usd", "cmd_byn", "cmd_metals",
    "cmd_new", "cmd_rv", "cmd_duration", "cmd_carry", "cmd_stress", "cmd_desk_status",
    "cmd_ml", "cmd_rebalance_auto", "cmd_scenario", "cmd_watchlist", "cmd_alerts",
    "cmd_stats", "cmd_settings",
}


@router.callback_query(lambda c: c.data and c.data in _CMD_HANDLER_NAMES)
async def cb_generic(callback_query) -> None:
    handler = globals().get(callback_query.data)
    if handler is None:
        return
    if callback_query.data == "cmd_parse":
        await callback_query.answer("🚀 Запускаем парсинг…")
    else:
        await callback_query.answer()
    await handler(callback_query.message)


# ---------------------------------------------------------------------------
# Menu navigation (section submenus)
# ---------------------------------------------------------------------------


def _submenu(title: str, buttons: list, back: str = "menu:main") -> tuple[str, InlineKeyboardMarkup]:
    rows = []
    for row in buttons:
        rows.append([InlineKeyboardButton(text=t, callback_data=d) for t, d in row])
    rows.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=back)])
    return title, InlineKeyboardMarkup(inline_keyboard=rows)


_OVERVIEW_MENU = _submenu(
    "📊 <b>Обзор рынка</b>\n\nВыберите действие:",
    [
        [("🏆 TOP облигаций", "cmd_top"), ("💵 Облигации USD", "cmd_usd")],
        [("🇧🇾 Облигации BYN", "cmd_byn"), ("🪙 Металлы", "cmd_metals")],
        [("💱 Курсы валют", "cmd_rates"), ("📈 Кривая доходности", "cmd_curve")],
        [("🆕 Новые облигации", "cmd_new"), ("📊 Статистика", "cmd_stats")],
        [("🔍 Выбрать облигацию", "bonds:menu")],
    ],
)

_DESK_MENU = _submenu(
    "🔬 <b>Аналитика (Fixed Income Desk)</b>\n\nВыберите действие:",
    [
        [("⚖️ Relative Value", "cmd_rv"), ("⏱ Duration", "cmd_duration")],
        [("💰 Carry", "cmd_carry"), ("⚠️ Стресс-тесты", "cmd_stress")],
        [("🏛 Desk Status", "cmd_desk_status"), ("📈 Кривая доходности", "cmd_curve")],
        [("🔍 Выбрать облигацию (РЕПО / отчёты)", "bonds:menu")],
    ],
)

_BUY_MENU = _submenu(
    "🤖 <b>Рекомендации</b>\n\nВыберите действие:",
    [
        [("🛒 Что купить сейчас", "cmd_buy"), ("🤖 ML-модели", "cmd_ml")],
        [("♻️ Auto-rebalance", "cmd_rebalance_auto"), ("📈 Прогноз по облигации", "bonds:menu")],
        [("🔍 Выбрать облигацию", "bonds:menu")],
    ],
)

_PORTFOLIO_MENU = _submenu(
    "💼 <b>Портфель</b>\n\nВыберите действие:",
    [
        [("📊 Мой портфель", "cmd_portfolio"), ("♻️ Ребалансировка", "cmd_rebalance")],
        [("📈 Прогноз капитала", "cmd_forecast"), ("🌍 Сценарии", "cmd_scenario")],
        [("👀 Избранное", "cmd_watchlist"), ("➕ Добавить в избранное", "bonds:menu")],
    ],
)


@router.callback_query(lambda c: c.data and c.data.startswith("menu:"))
async def cb_menu(callback_query) -> None:
    key = callback_query.data.split(":", 1)[1]
    if key == "main":
        await callback_query.message.edit_text(
            MENU_INTRO, parse_mode=ParseMode.HTML, reply_markup=_main_menu_kb()
        )
    elif key == "overview":
        title, kb = _OVERVIEW_MENU
        await callback_query.message.edit_text(title, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif key == "desk":
        title, kb = _DESK_MENU
        await callback_query.message.edit_text(title, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif key == "buy":
        title, kb = _BUY_MENU
        await callback_query.message.edit_text(title, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif key == "portfolio":
        title, kb = _PORTFOLIO_MENU
        await callback_query.message.edit_text(title, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif key == "settings":
        await cmd_settings(callback_query.message)
    elif key == "help":
        await callback_query.message.edit_text(
            HELP_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton("⬅️ Назад в меню", callback_data="menu:main")]]
            ),
        )
    await callback_query.answer()


# ---------------------------------------------------------------------------
# Bond picker: discover bonds without knowing IDs, then act on them
# ---------------------------------------------------------------------------


async def _bond_name(session, iid: str) -> str:
    from sqlalchemy import select as sa_select

    from scraper.orm import BondORM

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
    total_pages = max(1, (len(bonds) + _BOND_PAGE - 1) // _BOND_PAGE)
    page_slice = bonds[page * _BOND_PAGE : (page + 1) * _BOND_PAGE]
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
        from telegram_bot.subscriptions import get_tier_by_telegram, meets_tier

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
        from sqlalchemy import select as sa_select

        from scraper.orm import BondORM

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
        ]
    )
    await callback_query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb)
    await callback_query.answer()


# ---------------------------------------------------------------------------
# Overview (inline keyboard shortcut)
# ---------------------------------------------------------------------------


@router.message(Command("overview"))
async def cmd_overview(message: Message) -> None:
    text = (
        "<b>📊 Обзор рынка</b>\n\n"
        "/top — TOP облигаций по рейтингу\n"
        "/usd — Облигации в USD\n"
        "/byn — Облигации в BYN\n"
        "/metals — Золото / серебро / платина\n"
        "/rates — Курсы валют и металлов\n"
        "/curve — Кривая доходности"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Top / Scores
# ---------------------------------------------------------------------------


@router.message(Command("top"))
async def cmd_top(message: Message, page: int = 0) -> None:
    async with session_scope() as session:
        top = await top_scores(session, limit=_PAGE_SIZE, offset=page * _PAGE_SIZE)
        if not top and page == 0:
            await message.answer("База пуста. Сначала запустите `python -m scraper once`.")
            return
        if not top:
            await message.answer("Нет облигаций на этой странице.")
            return
        bonds_map = {b.internal_id: b.name for b in await fetch_all_bonds()}
        lines = [f"<b>🏆 TOP Reward/Risk</b> (стр. {page + 1})\n"]
        for i, s in enumerate(top, page * _PAGE_SIZE + 1):
            name_display = bonds_map.get(s.internal_id, "")
            name_part = f" — {name_display}" if name_display else ""
            lines.append(f"{i}. <code>{s.internal_id}</code>{name_part} — Score: {float(s.score):.0f}")
        total = page + 1
        await message.answer(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=paginate_kb("top", page, total),
        )


# ---------------------------------------------------------------------------
# Currency views
# ---------------------------------------------------------------------------


async def _currency_view(message: Message, currency: str, title: str, page: int = 0) -> None:
    prefix = currency.lower()
    bonds = await fetch_bonds_by_currency(currency)
    if not bonds:
        await message.answer(f"Нет облигаций в {currency}. Запустите парсер.")
        return
    rows = []
    for b in bonds:
        sc = score_bond(
            internal_id=b.internal_id,
            yield_to_maturity=b.yield_to_maturity,
            currency=b.currency,
            maturity_date=b.maturity_date,
            status=b.status,
            issuer=b.issuer,
            price=b.price,
        )
        ytm = f"{float(b.yield_to_maturity):.2f}%" if b.yield_to_maturity else "—"
        rows.append((b.internal_id, float(sc.score), ytm, b.name))

    rows.sort(key=lambda r: r[1], reverse=True)
    total_pages = max(1, (len(rows) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page_slice = rows[page * _PAGE_SIZE : (page + 1) * _PAGE_SIZE]

    lines = [f"<b>{title}</b> (стр. {page + 1}/{total_pages})\n"]
    for iid, sc, ytm, name in page_slice:
        lines.append(f"• <code>{iid}</code> {name} — Score {sc:.0f}, YTM {ytm}")

    safe_ytm = []
    for iid, _sc, ytm, _name in rows[:15]:
        try:
            val = float(ytm.rstrip("%"))
        except (ValueError, AttributeError):
            val = 0.0
        safe_ytm.append((iid, val))
    png = plot_yield_distribution(safe_ytm)
    await message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=paginate_kb(prefix[:3], page, total_pages),
    )
    await message.answer_photo(BufferedInputFile(png, filename="yields.png"))


@router.message(Command("usd"))
async def cmd_usd(message: Message) -> None:
    await _currency_view(message, "USD", "💵 Облигации в USD")


@router.message(Command("byn"))
async def cmd_byn(message: Message) -> None:
    await _currency_view(message, "BYN", "🇧🇾 Облигации в BYN")


@router.message(Command("metals"))
async def cmd_metals(message: Message) -> None:
    parts: list[str] = []
    for cur, title in (("XAU", "Золото"), ("XAG", "Серебро"), ("XPT", "Платина")):
        bonds = await fetch_bonds_by_currency(cur)
        if not bonds:
            parts.append(f"{title}: нет данных")
            continue
        best = max(
            bonds,
            key=lambda b: float(
                score_bond(
                    internal_id=b.internal_id,
                    yield_to_maturity=b.yield_to_maturity,
                    currency=b.currency,
                    maturity_date=b.maturity_date,
                    status=b.status,
                    issuer=b.issuer,
                    price=b.price,
                ).score
            ),
        )
        s = score_bond(
            internal_id=best.internal_id,
            yield_to_maturity=best.yield_to_maturity,
            currency=best.currency,
            maturity_date=best.maturity_date,
            status=best.status,
            issuer=best.issuer,
            price=best.price,
        )
        parts.append(f"{title}: <code>{best.internal_id}</code> ({best.name}) Score {s.score:.0f}")
    await message.answer("\n".join(parts), parse_mode=ParseMode.HTML)


@router.message(Command("new"))
async def cmd_new(message: Message) -> None:
    async with session_scope() as session:
        res = await session.execute(select(BondORM).order_by(desc(BondORM.fetched_at)).limit(10))
        bonds = list(res.scalars().all())
        if not bonds:
            await message.answer("Нет данных.")
            return
        lines = ["<b>🆕 Новые/обновлённые</b>\n"]
        for b in bonds:
            lines.append(f"• <code>{b.internal_id}</code> {b.name}")
        await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


@router.message(Command("portfolio"))
async def cmd_portfolio(message: Message) -> None:
    uid = user_id_from_message(message)
    async with session_scope() as session:
        from telegram_bot.preferences_repository import get_preferences

        prefs = await get_preferences(session, uid)
        bonds = await fetch_all_bonds()
    if not bonds:
        await message.answer("Нет данных по облигациям. Запустите парсер.")
        return
    alloc = allocate(bonds, prefs, top_n=10)
    forecasts = forecast_horizons(
        initial_capital=prefs.initial_capital,
        monthly_contribution=prefs.monthly_contribution,
        expected_annual_return_pct=max(alloc.expected_return, 0.1),
        volatility_pct=alloc.volatility,
    )
    text = (
        f"<b>📊 Портфель ({alloc.strategy})</b>\n\n"
        f"Капитал: <b>{prefs.initial_capital}</b>\n"
        f"Пополнение/мес: <b>{prefs.monthly_contribution}</b>\n"
        f"Ожидаемая доходность: <b>{alloc.expected_return:.2f}%</b>\n"
        f"Sharpe: <b>{alloc.sharpe:.2f}</b>, Sortino: <b>{alloc.sortino:.2f}</b>\n"
        f"Макс. просадка: <b>{alloc.max_drawdown:.2f}%</b>, VaR 95%: <b>{alloc.var_95:.2f}</b>\n\n"
        f"<b>Прогноз:</b>\n"
    )
    for f in forecasts:
        text += f"  {f.horizon_years}Y: {f.expected_capital} (от {f.pessimistic_capital} до {f.optimistic_capital})\n"

    await message.answer(text, parse_mode=ParseMode.HTML)
    png = plot_portfolio_pie(alloc)
    await message.answer_photo(BufferedInputFile(png, filename="portfolio.png"))


@router.message(Command("rebalance"))
async def cmd_rebalance(message: Message) -> None:
    uid = user_id_from_message(message)
    async with session_scope() as session:
        from telegram_bot.preferences_repository import get_preferences

        prefs = await get_preferences(session, uid)
        bonds = await fetch_all_bonds()
    if not bonds:
        await message.answer("Нет данных.")
        return
    current = {
        iid: prefs.initial_capital / Decimal("10")
        for iid in [b.internal_id for b in bonds[:10]]
    }
    _target, deltas = rebalance(current, bonds, prefs)
    if not deltas:
        await message.answer("Ребалансировка не требуется.")
        return
    bonds_map_rb = {b.internal_id: b.name for b in bonds}
    lines = ["<b>♻️ Ребалансировка</b>\n"]
    for iid, d in list(deltas.items())[:20]:
        sign = "+" if d >= 0 else ""
        n = bonds_map_rb.get(iid, "")
        n_part = f" ({n})" if n else ""
        lines.append(f"• <code>{iid}</code>{n_part}: {sign}{d}")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------


@router.message(Command("forecast"))
async def cmd_forecast(message: Message) -> None:
    uid = user_id_from_message(message)
    async with session_scope() as session:
        from telegram_bot.preferences_repository import get_preferences

        prefs = await get_preferences(session, uid)
    png = plot_capital_forecast(
        initial_capital=prefs.initial_capital,
        monthly_contribution=prefs.monthly_contribution,
        expected_annual_return_pct=7.0,
        volatility_pct=4.0,
    )
    text = (
        f"<b>📈 Прогноз капитала</b>\n"
        f"Старт: {prefs.initial_capital}\n"
        f"Пополнение: {prefs.monthly_contribution}/мес\n"
        f"Ожидаемая доходность: 7% (по умолчанию)\n"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)
    await message.answer_photo(BufferedInputFile(png, filename="forecast.png"))


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@router.message(Command("scenario"))
async def cmd_scenario(message: Message) -> None:
    uid = user_id_from_message(message)
    async with session_scope() as session:
        from notifications.fx_repository import latest_fx
        from telegram_bot.preferences_repository import get_preferences

        prefs = await get_preferences(session, uid)
        fx = await latest_fx(session, "USD/BYN")
    current = fx.rate if fx else Decimal("3.30")
    results = run_all_scenarios(
        current_usd_byn=current,
        usd_share=prefs.share_usd,
        byn_share=prefs.share_byn,
        metals_share=prefs.share_metals,
        eur_share=prefs.share_eur,
    )
    lines = [f"<b>🌍 Сценарии USD/BYN (текущий {current})</b>\n"]
    for r in results:
        lines.append(
            f"• <b>{r.scenario}</b>: курс → {r.usd_byn_end} ({r.fx_change_pct:+.1f}%), "
            f"портфель {r.portfolio_value_change_pct:+.2f}%"
        )
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Buy / Recommendations
# ---------------------------------------------------------------------------


@router.message(Command("buy"))
async def cmd_buy(message: Message) -> None:
    uid = user_id_from_message(message)
    async with session_scope() as session:
        from telegram_bot.preferences_repository import get_preferences

        prefs = await get_preferences(session, uid)
    bond_dicts, history = await fetch_bonds_with_history()
    recs = recommend_bonds(bond_dicts, prefs, history_by_bond=history, top_k=5)
    if not recs:
        await message.answer("Нет рекомендаций. Запустите `python -m scraper ml-train`.")
        return
    lines = ["<b>🛒 Рекомендации (Score + ML)</b>\n"]
    for r in recs:
        ret = f", +{r.predicted_return_pct:.2f}%" if r.predicted_return_pct is not None else ""
        lines.append(
            f"#{r.rank} <code>{r.internal_id}</code> {r.name} — "
            f"<b>{r.decision.upper()}</b> (conf {r.confidence:.2f}, score {r.score:.0f}{ret})"
        )
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# ML
# ---------------------------------------------------------------------------


@router.message(Command("ml"))
async def cmd_ml(message: Message) -> None:
    async with session_scope() as session:
        mv_reg = await latest_model_version(session, "ytm_regression")
        mv_clf = await latest_model_version(session, "buy_classifier")
    parts = ["<b>🤖 ML-модели</b>\n"]
    for kind, mv in (("YTM Regression", mv_reg), ("Buy Classifier", mv_clf)):
        if mv is None:
            parts.append(f"• <b>{kind}</b>: не обучена. Запустите `python -m scraper ml-train`")
            continue
        metrics = ", ".join(f"{k}={float(v):.3f}" for k, v in mv.metrics.items())
        parts.append(f"• <b>{kind}</b> v{mv.version} ({mv.train_rows} строк)\n  {metrics}")
    await message.answer("\n".join(parts), parse_mode=ParseMode.HTML)


@router.message(Command("predict"))
async def cmd_predict(message: Message) -> None:
    bond_id = parse_bond_args(message)
    if not bond_id:
        await message.answer("Использование: /predict OP-51")
        return
    async with session_scope() as session:
        rows = await predictions_for_bond(session, bond_id, limit=1)
        from sqlalchemy import select as sa_select

        from scraper.orm import BondORM

        bond_name = (
            await session.execute(
                sa_select(BondORM.name).where(BondORM.internal_id == bond_id)
            )
        ).scalar_one_or_none() or bond_id
    if not rows:
        await message.answer("Нет прогнозов. Запустите `python -m scraper ml-predict`.")
        return
    p = rows[0]
    expl = "\n".join(f"  • {e}" for e in (p.explanation or []))
    text = (
        f"<b>📈 Прогноз {bond_id}</b> ({bond_name})\n"
        f"Решение: <b>{p.decision}</b> (conf {float(p.confidence):.2f})\n"
        f"Predicted YTM: {float(p.predicted_ytm) if p.predicted_ytm is not None else '—'}\n"
        f"Predicted return: {float(p.predicted_return_pct) if p.predicted_return_pct is not None else '—'}\n"
        f"Объяснение:\n{expl or '—'}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("rebalance-auto"))
async def cmd_rebalance_auto(message: Message) -> None:
    uid = user_id_from_message(message)
    _bond_dicts, _history = await fetch_bonds_with_history()
    async with session_scope() as session:
        from telegram_bot.preferences_repository import get_preferences

        prefs = await get_preferences(session, uid)
        positions = await list_positions(session, uid)
        bonds_q = await repositories.bonds.get_all_internal_ids(session)
        bonds_orm = (
            (await session.execute(select(BondORM).where(BondORM.internal_id.in_(list(bonds_q)))))
            .scalars()
            .all()
        )
        bonds = [
            Bond(
                internal_id=b.internal_id,
                name=b.name,
                currency=b.currency,
                yield_to_maturity=b.yield_to_maturity,
                maturity_date=b.maturity_date,
                status=b.status,
                issuer=b.issuer,
                price=b.price,
                fetched_at=b.fetched_at,
            )
            for b in bonds_orm
        ]
        bonds_map_ar = {b.internal_id: b.name for b in bonds}
        total = total_value(positions) or prefs.initial_capital
        plan = build_plan(
            bonds=bonds,
            prefs=prefs,
            current_positions=positions,
            current_total=total,
        )
    if plan is None:
        await message.answer("✅ Drift ниже порога — ребалансировка не требуется.")
        return
    lines = [
        f"<b>♻️ Auto-rebalance ({plan.strategy})</b>\n",
        f"Max drift: {plan.max_drift_observed:.2%}\n",
    ]
    for a in plan.actions[:20]:
        n = bonds_map_ar.get(a.internal_id, "")
        n_part = f" ({n})" if n else ""
        lines.append(
            f"• <b>{a.side.upper()}</b> {a.internal_id}{n_part}: {a.amount} "
            f"({a.weight_before:.2%} → {a.weight_after:.2%})"
        )
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------


@router.message(Command("watchlist"))
async def cmd_watchlist(message: Message) -> None:
    uid = user_id_from_message(message)
    async with session_scope() as session:
        from telegram_bot.preferences_repository import get_preferences

        prefs = await get_preferences(session, uid)
        if not prefs.watchlist:
            await message.answer("Watchlist пуст. Добавьте: /watch OP-51")
            return
        from scraper.orm import BondORM
        result_bonds = await session.execute(
            select(BondORM).where(BondORM.internal_id.in_(prefs.watchlist))
        )
        watch_bonds = {b.internal_id: b.name for b in result_bonds.scalars().all()}
        lines = ["<b>👀 Watchlist</b>\n"]
        for iid in prefs.watchlist:
            sc = await get_score(session, iid)
            score_text = f"Score {float(sc.score):.0f}" if sc else "нет скора"
            name_display = watch_bonds.get(iid, "")
            name_part = f" ({name_display})" if name_display else ""
            lines.append(f"• <code>{iid}</code>{name_part} — {score_text}")
        await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("watch"))
async def cmd_watch(message: Message) -> None:
    iid = parse_bond_args(message)
    if not iid:
        await message.answer("Использование: /watch OP-51")
        return
    bond_name = iid
    async with session_scope() as session:
        if not await repositories.bonds.exists(session, iid):
            await message.answer(
                f"❌ Облигация <code>{iid}</code> не найдена в БД", parse_mode=ParseMode.HTML
            )
            return
        from sqlalchemy import select as sa_select

        from scraper.orm import BondORM

        result = await session.execute(
            sa_select(BondORM.name).where(BondORM.internal_id == iid)
        )
        bond_name = result.scalar_one_or_none() or iid
    uid = user_id_from_message(message)
    async with session_scope() as session:
        from telegram_bot.preferences_repository import add_to_watchlist

        prefs = await add_to_watchlist(session, uid, iid)
    await message.answer(
        f"✅ <code>{iid}</code> ({bond_name}) добавлен в watchlist ({len(prefs.watchlist)} шт.)",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("unwatch"))
async def cmd_unwatch(message: Message) -> None:
    iid = parse_bond_args(message)
    if not iid:
        await message.answer("Использование: /unwatch OP-51")
        return
    bond_name = iid
    async with session_scope() as session:
        if not await repositories.bonds.exists(session, iid):
            await message.answer(
                f"❌ Облигация <code>{iid}</code> не найдена в БД", parse_mode=ParseMode.HTML
            )
            return
        from sqlalchemy import select as sa_select

        from scraper.orm import BondORM

        result = await session.execute(
            sa_select(BondORM.name).where(BondORM.internal_id == iid)
        )
        bond_name = result.scalar_one_or_none() or iid
    uid = user_id_from_message(message)
    async with session_scope() as session:
        from telegram_bot.preferences_repository import remove_from_watchlist

        await remove_from_watchlist(session, uid, iid)
    await message.answer(f"❌ <code>{iid}</code> ({bond_name}) убран из watchlist", parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@router.message(Command("alerts"))
async def cmd_alerts(message: Message) -> None:
    async with session_scope() as session:
        alerts = await list_recent(session, limit=10)
        if not alerts:
            await message.answer("Алерты отсутствуют.")
            return
        lines = ["<b>🔔 Последние алерты</b>\n"]
        for a in alerts:
            lines.append(f"• <b>{a.title}</b>\n  {a.message}")
        await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Desk
# ---------------------------------------------------------------------------


@router.message(Command("desk"))
async def cmd_desk(message: Message) -> None:
    text = (
        "<b>🔬 Аналитика (Fixed Income Desk)</b>\n\n"
        "Команды:\n"
        "/rv — Relative Value (rich/cheap)\n"
        "/duration [ID] — Duration-отчёт\n"
        "/carry [funding] — Carry-ранжирование\n"
        "/repo ID [notional] [tenor] — Сделка РЕПО\n"
        "/stress — Стресс-тесты (7 сценариев)\n"
        "/desk_status — Последние сигналы"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("curve"))
async def cmd_curve(message: Message) -> None:
    bonds = await bonds_for_bot()
    by_cur: dict[str, list] = {}
    for b in bonds:
        by_cur.setdefault(str(b.currency), []).append(b)

    lines = ["<b>📈 Кривая доходности</b>\n"]
    for cur, bs in by_cur.items():
        curve = desk_curve.curve_from_bonds(bs)
        if not curve.points:
            continue
        params = desk_curve.fit_nelson_siegel(curve.points)
        lines.append(
            f"<b>{cur}</b> — slope {curve.slope():.2f}%, beta0={params.beta0:.2f}, "
            f"beta1={params.beta1:.2f}, beta2={params.beta2:.2f}"
        )
        for p in curve.points:
            lines.append(f"  {p.tenor}: {p.rate_pct:.2f}%")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("rv"))
async def cmd_rv(message: Message, page: int = 0) -> None:
    bonds = await bonds_for_bot()
    signals = desk_rv.relative_value_signals(bonds)
    if not signals:
        await message.answer("Нет данных для Relative Value.")
        return
    total_pages = max(1, (len(signals) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page_slice = signals[page * _PAGE_SIZE : (page + 1) * _PAGE_SIZE]
    bonds_map_rv = {b.internal_id: b.name for b in bonds}
    lines = [f"<b>⚖️ Relative Value</b> (стр. {page + 1}/{total_pages})\n"]
    for s in page_slice:
        sign = "🟢 BUY" if s.side == "buy" else ("🔴 SELL" if s.side == "sell" else "⚪ HOLD")
        n = bonds_map_rv.get(s.internal_id, "")
        n_part = f" {n}" if n else ""
        lines.append(
            f"{sign} <code>{s.internal_id}</code>{n_part} (Z={s.z_score:+.2f}, spread {s.spread_pct:+.2f}%)"
        )
    await message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=paginate_kb("rv", page, total_pages),
    )


@router.message(Command("duration"))
async def cmd_duration(message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)
    bonds = await bonds_for_bot()
    if len(args) > 1:
        bond = next((b for b in bonds if b.internal_id == args[1].strip()), None)
        if bond is None:
            await message.answer(f"Облигация {args[1]} не найдена")
            return
        rep = desk_duration.duration_report(bond)
        title = f"<b>⏱ Duration Report</b> — <code>{bond.internal_id}</code> ({bond.name})\n"
    else:
        weights = {b.internal_id: 1 / len(bonds) for b in bonds} if bonds else {}
        rep = desk_duration.portfolio_duration(bonds, weights=weights)
        title = "<b>⏱ Duration Report (Портфель)</b>\n"
    lines = [
        title,
        f"Macaulay: {rep.macaulay_duration:.3f}",
        f"Modified: {rep.modified_duration:.3f}",
        f"Convexity: {rep.convexity:.3f}",
        f"DV01: {rep.dv01:.4f}\n",
        "<b>Key-rate durations:</b>",
    ]
    for tenor, krd in rep.key_rate_durations.items():
        lines.append(f"  {tenor}: {krd:.4f}")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("carry"))
async def cmd_carry(message: Message, page: int = 0) -> None:
    funding = parse_funding_rate(message)
    bonds = await bonds_for_bot()
    trades = desk_carry.rank_carry(bonds, funding_rate_pct=funding)
    if not trades:
        await message.answer("Нет данных для carry-анализа")
        return
    total_pages = max(1, (len(trades) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page_slice = trades[page * _PAGE_SIZE : (page + 1) * _PAGE_SIZE]
    bonds_map_carry = {b.internal_id: b.name for b in bonds}
    lines = [f"<b>💰 Carry (funding {funding}%)</b> (стр. {page + 1}/{total_pages})\n"]
    for t in page_slice:
        sign = "🟢" if t.expected_pnl_pct > 0 else "🔴"
        n = bonds_map_carry.get(t.internal_id, "")
        n_part = f" {n}" if n else ""
        lines.append(
            f"{sign} <code>{t.internal_id}</code>{n_part}: купон {t.coupon_pct:.2f}%, "
            f"rolldown {t.rolldown_bps:+.1f}bp, P&L {t.expected_pnl_pct:+.3f}%"
        )
    await message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=paginate_kb("carry", page, total_pages),
    )


@router.message(Command("repo"))
async def cmd_repo(message: Message) -> None:
    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer("Использование: /repo OP-51 [notional=1000] [tenor_days=30]")
        return
    internal_id = args[1]
    try:
        notional = float(args[2]) if len(args) > 2 else 1000.0
        tenor = int(args[3]) if len(args) > 3 else 30
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Использование: /repo OP-51 [notional=1000] [tenor_days=30]")
        return
    bonds = await bonds_for_bot()
    bond = next((b for b in bonds if b.internal_id == internal_id), None)
    if bond is None:
        await message.answer(f"Облигация {internal_id} не найдена")
        return
    haircut = desk_repo.haircut_by_issuer(bond.issuer)
    deal = desk_repo.repo_deal(
        bond,
        notional=Decimal(str(notional)),
        haircut_pct=haircut,
        repo_rate_pct=5.0,
        tenor_days=tenor,
    )
    text = (
        f"<b>🏦 РЕПО {internal_id}</b> ({bond.name})\n"
        f"Залог: {deal.collateral_value}\n"
        f"Haircut: {deal.haircut_pct}%\n"
        f"Кэш выдано: {deal.cash_lent}\n"
        f"Ставка: {deal.repo_rate_pct}%, тенор {deal.tenor_days}d\n"
        f"Проценты: {deal.accrued_interest}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("stress"))
async def cmd_stress(message: Message) -> None:
    bonds = await bonds_for_bot()
    weights = {b.internal_id: Decimal("1000") for b in bonds}
    lines = ["<b>⚠️ Stress-тесты (Δ P&L)</b>\n"]
    for name, scn in desk_stress.PRESET_SCENARIOS.items():
        res = desk_stress.run_stress(scn, [(b, weights[b.internal_id]) for b in bonds])
        lines.append(f"• <b>{name}</b> ({scn.kind}): {res.pnl_pct:+.3f}% ({float(res.pnl):+.0f})")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Desk Status
# ---------------------------------------------------------------------------


@router.message(Command("desk_status"))
async def cmd_desk_status(message: Message) -> None:
    async with session_scope() as session:
        rv = await latest_rv_signals(session, limit=5)
        stress_runs = await latest_stress_runs(session, limit=3)
    bonds = await fetch_all_bonds()
    desk_bonds_map = {b.internal_id: b.name for b in bonds}
    lines = ["<b>🏛 Desk Status</b>\n"]
    lines.append("<b>RV (top-5):</b>")
    for s in rv:
        n = desk_bonds_map.get(s.internal_id, "")
        n_part = f" ({n})" if n else ""
        lines.append(f"  {s.internal_id}{n_part}: Z={float(s.z_score):+.2f} ({s.side})")
    lines.append("\n<b>Stress (recent):</b>")
    for r in stress_runs:
        lines.append(f"  {r.scenario_name}: P&L {float(r.pnl_pct):+.3f}%")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Settings / Presets
# ---------------------------------------------------------------------------

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
                [InlineKeyboardButton(text="⚙️ К настройкам", callback_data="menu:settings")]
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
        _pending_edit.pop(callback_query.from_user.id if callback_query.from_user else 0, None)
        await callback_query.answer("Отменено")
        await cmd_settings(callback_query.message)
        return
    uid = callback_query.from_user.id if callback_query.from_user else 0
    _pending_edit[uid] = field
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
    _pending_edit.pop(user_id_from_message(message), None)
    await message.answer("✅ Режим ввода отменён.")


@router.message(lambda m: user_id_from_message(m) in _pending_edit)
async def cb_pending_edit(message: Message) -> None:
    uid = user_id_from_message(message)
    field = _pending_edit.pop(uid)
    if (message.text or "").strip().startswith("/"):
        await message.answer("✏️ Режим ввода отменён — команда не применена. Повторите её.")
        return
    ok, text = await apply_setting(uid, field, (message.text or "").strip())
    await message.answer(text, parse_mode=ParseMode.HTML)


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
    ok, text = await apply_setting(uid, field, val_str)
    await message.answer(text, parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

import os as _os

_ADMIN_IDS = {int(v) for v in _os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if v.strip()}


def _is_admin(message: Message) -> bool:
    uid = message.from_user.id if message.from_user else 0
    return uid in _ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message):
        return
    text = (
        "<b>🔧 Admin panel</b>\n\n"
        "/broadcast <text> — отправить всем\n"
        "/admin users — статистика\n"
        "/admin errors — последние ошибки"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message) -> None:
    if not _is_admin(message):
        return
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /broadcast <text>")
        return
    async with session_scope() as session:
        from sqlalchemy import select as sa_select

        from scraper.orm import UserPreferencesORM

        result = await session.execute(sa_select(UserPreferencesORM.user_id).distinct())
        user_ids = [row[0] for row in result.fetchall()]
    if not user_ids:
        await message.answer("Нет пользователей для рассылки.")
        return
    text_to_send = args[1]
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(chat_id=uid, text=f"📢 {text_to_send}")
            sent += 1
        except Exception:
            failed += 1
    await message.answer(f"📢 Разослано: {sent} успешно, {failed} с ошибками.")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    async with session_scope() as session:
        count = await repositories.bonds.count_bonds(session)
        latest = await repositories.bonds.latest_fetched_at(session)
    lines = [
        "<b>📊 Статистика системы</b>\n",
        f"Облигаций в БД: <b>{count}</b>",
        f"Последнее обновление: <b>{latest or 'никогда'}</b>",
    ]
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------


@router.errors(ExceptionTypeFilter(Exception))
async def global_error_handler(event: ErrorEvent):
    logger.exception("bot_handler_error", error=str(event.exception))
    if event.update.message:
        await event.update.message.answer(
            "❌ Внутренняя ошибка. Попробуйте позже или напишите /help.",
        )
