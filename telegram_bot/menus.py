"""Menu keyboards and section navigation for the Telegram bot.

Pure presentation/navigation: builds the main menu, section submenus and the
`menu:` callback router. Section command handlers live elsewhere; this module
only bridges buttons to them (via lazy imports to avoid import cycles).
"""
from __future__ import annotations

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram_bot.handler_state import PAGE_SIZE  # noqa: F401  (re-exported for callers)

router = Router()

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
            [
                InlineKeyboardButton(text="🏆 Топ-10", callback_data="cmd_top"),
                InlineKeyboardButton(text="💱 Курсы", callback_data="cmd_rates"),
            ],
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


def _home_kb() -> InlineKeyboardMarkup:
    """A single 'back to main menu' button, for appending to any response."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]
    )


async def _show_main_menu(message) -> None:
    await message.answer(MENU_INTRO, parse_mode=ParseMode.HTML, reply_markup=_main_menu_kb())


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
        from telegram_bot.settings import cmd_settings

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
