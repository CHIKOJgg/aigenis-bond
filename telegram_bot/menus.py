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
    "Почти всё доступно по кнопкам меню — команды вводить необязательно.\n\n"
    "• <b>📊 Обзор</b> — Топ облигаций, валюты, курсы, кривая доходности.\n"
    "• <b>🔬 Аналитика</b> — Relative Value, Duration, Carry, РЕПО, стресс-тесты (Pro).\n"
    "• <b>🤖 Рекомендации</b> — что купить и ML-прогнозы (Pro).\n"
    "• <b>💼 Портфель</b> — прогноз капитала, ребалансировка, сценарии (Pro).\n"
    "• <b>🔍 Облигации</b> — найдите нужную и получите прогноз / duration / РЕПО.\n"
    "• <b>⚙️ Настройки</b> — капитал и доли валют (пресеты одним тапом).\n"
    "• <b>👤 Мой тариф</b> — текущий доступ и сколько дней осталось (/status).\n"
    "• <b>⭐ Подписка</b> — Pro/Enterprise через Telegram Stars.\n\n"
    "Откройте <b>🆘 Как пользоваться</b> в меню для краткой справки по каждому разделу."
)


def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💱 Курсы", callback_data="cmd_rates")],
            [InlineKeyboardButton(text="📊 Обзор рынка", callback_data="menu:overview")],
            [InlineKeyboardButton(text="🔬 Аналитика (Desk)", callback_data="menu:desk")],
            [InlineKeyboardButton(text="🤖 Рекомендации", callback_data="menu:buy")],
            [InlineKeyboardButton(text="💼 Портфель", callback_data="menu:portfolio")],
            [InlineKeyboardButton(text="🔍 Облигации", callback_data="bonds:menu")],
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
                InlineKeyboardButton(text="👤 Мой тариф", callback_data="cmd_status"),
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
        [("♻️ Auto-rebalance", "cmd_rebalance_auto")],
        [("🔍 Выбрать облигацию", "bonds:menu")],
    ],
)

_PORTFOLIO_MENU = _submenu(
    "💼 <b>Портфель</b>\n\nВыберите действие:",
    [
        [("📌 Мои позиции", "positions:menu"), ("📊 Модельный портфель", "cmd_portfolio")],
        [("♻️ Ребалансировка", "cmd_rebalance"), ("📈 Прогноз капитала", "cmd_forecast")],
        [("🌍 Сценарии", "cmd_scenario"), ("👀 Избранное", "cmd_watchlist")],
    ],
)

_HELP_MENU = _submenu(
    "🆘 <b>Справка по разделам</b>\n\nВыберите раздел:",
    [
        [("📊 Обзор", "help:overview"), ("🔬 Аналитика", "help:desk")],
        [("🤖 Рекомендации", "help:buy"), ("💼 Портфель", "help:portfolio")],
        [("⚙️ Настройки", "help:settings"), ("🔔 Алерты", "help:alerts")],
        [("💳 Подписка", "help:stars"), ("🔍 Облигации", "help:bonds")],
    ],
)

_HELP_TEXTS = {
    "overview": (
        "📊 <b>Обзор рынка</b>\n"
        "• 🏆 Топ-10 — лучшие облигации по рейтингу\n"
        "• 💵/🇧🇾 Облигации USD/BYN, 🪙 Металлы\n"
        "• 💱 Курсы валют и драгметаллы\n"
        "• 📈 Кривая доходности, 🆕 Новые облигации"
    ),
    "desk": (
        "🔬 <b>Аналитика (Desk)</b> — тариф Pro/Enterprise\n"
        "• ⚖️ Relative Value — дорого/дёшево относительно кривой\n"
        "• ⏱ Duration — процентный риск (по портфелю или облигации)\n"
        "• 💰 Carry — ранжирование по carry, ⚠️ Стресс-тесты\n"
        "• 🏛 Desk Status — сводные сигналы, 📈 Кривая доходности\n"
        "• 🏦 РЕПО — откройте облигацию → «🔬 Для профи» → «🏦 РЕПО»"
    ),
    "buy": (
        "🤖 <b>Рекомендации</b> — тариф Pro/Enterprise\n"
        "• 🛒 Что купить сейчас (Score + ML)\n"
        "• 🤖 ML-модели, 📈 Прогноз по облигации"
    ),
    "portfolio": (
        "💼 <b>Портфель</b> — тариф Pro/Enterprise\n"
        "• 📌 Мои позиции — ваши реальные облигации и купонный доход\n"
        "• 📊 Модельный портфель — рекомендуемое распределение и прогноз\n"
        "• ♻️ Ребалансировка, 📈 Прогноз капитала, 🌍 Сценарии USD/BYN"
    ),
    "settings": (
        "⚙️ <b>Настройки</b>\n"
        "• Капитал, пополнение, доли валют — пресеты и кнопки одним тапом\n"
        "• Быстрая установка суммы — кнопками в разделе ⚙️ Настройки"
    ),
    "alerts": (
        "🔔 <b>Алерты</b>\n"
        "• Персональные: откройте облигацию → «🔔 Следить за ценой» (Pro)\n"
        "• Уведомим, когда цена упадёт или доходность вырастет до порога\n"
        "• Мои правила, срабатывания и рыночные события: /alerts"
    ),
    "stars": (
        "💳 <b>Подписка</b>\n"
        "• Кнопка ⭐ Подписка или /subscribe\n"
        "• Оплата Telegram Stars (Pro / Enterprise)\n"
        "• Открывает аналитику, рекомендации, портфель, ML и алерты"
    ),
    "bonds": (
        "🔍 <b>Облигации</b>\n"
        "• Кнопка 🔍 Облигации → валюта → облигация\n"
        "• 💡 Стоит купить? — рейтинг и вердикт простыми словами\n"
        "• 💰 Доход — сколько купонов получите (Pro)\n"
        "• 🔔 Следить за ценой — персональные алерты (Pro)\n"
        "• ➕ В портфель — учёт реальной позиции (Pro)\n"
        "• 🔬 Для профи — Duration и РЕПО, ⭐ в избранное"
    ),
}


@router.callback_query(lambda c: c.data and c.data.startswith("help:"))
async def cb_help(callback_query) -> None:
    key = callback_query.data.split(":", 1)[1]
    text = _HELP_TEXTS.get(key, HELP_TEXT)
    await callback_query.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ К справке", callback_data="menu:help")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
            ]
        ),
    )
    await callback_query.answer()


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
        title, kb = _HELP_MENU
        await callback_query.message.edit_text(title, parse_mode=ParseMode.HTML, reply_markup=kb)
    await callback_query.answer()
