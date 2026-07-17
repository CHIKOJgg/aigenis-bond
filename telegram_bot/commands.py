"""Command and message handlers for the Telegram bot.

Houses every `/command` handler plus the generic callback bridges (`cb_paginate`,
`cb_generic`) that dispatch inline buttons to the matching `cmd_*` coroutine.
Shared menu helpers are imported from `telegram_bot.menus`; settings/admin
handlers that are also reachable from inline buttons are imported so the
`globals()`-based dispatch in `cb_generic` can resolve them.
"""
from __future__ import annotations

from decimal import Decimal

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
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
from notifications.alerts_repository import list_events, list_rules
from notifications.fx_repository import latest_fx, latest_metal
from notifications.repository import list_recent
from portfolio.optimizer import allocate, rebalance
from portfolio.positions_repository import list_positions, total_value
from portfolio.rebalance import build_plan
from portfolio.scenarios import run_all_scenarios
from recommendations.engine import recommend_bonds
from scoring.disclaimer import DISCLAIMER_SHORT
from scoring.engine import score_bond
from scoring.repository import get_score, top_scores
from scraper import repositories
from scraper.db import session_scope
from scraper.models import Bond
from scraper.orm import BondORM
from telegram_bot import _cmd_helpers as _ch
from telegram_bot.handler_state import PAGE_SIZE, parse_lock
from telegram_bot.helpers import (
    alert_direction_sign,
    alert_metric_label,
    bonds_for_bot,
    fetch_all_bonds,
    fetch_bonds_by_currency,
    fetch_bonds_with_history,
    fmt_num,
    paginate_kb,
    parse_bond_args,
    parse_funding_rate,
    user_id_from_message,
)
from telegram_bot.menus import _DESK_MENU, _OVERVIEW_MENU, _home_kb, _show_main_menu
from visualization.charts import (
    plot_capital_forecast,
    plot_portfolio_pie,
    plot_yield_distribution,
)

router = Router()

_STRATEGY_RU = {
    "Conservative": "Консервативный",
    "Balanced": "Сбалансированный",
    "Aggressive": "Агрессивный",
    "Metals++": "Металлы+",
}


# ---------------------------------------------------------------------------
# Helpers (see telegram_bot._cmd_helpers)
# ---------------------------------------------------------------------------


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not await _ch.is_unlocked(message):
        await message.answer(
            "👋 <b>Bond Fixed Income Assistant</b>\n\n"
            "⏳ Котировки ещё загружаются. Нажмите кнопку ниже, чтобы обновить "
            "данные по облигациям и курсам валют — это займёт до минуты.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Обновить данные", callback_data="cmd_parse")]
                ]
            ),
        )
        return
    # Data is ready — this is the first real interaction, so create the account
    # and start the trial clock only now (free days must not tick while the user
    # is stuck on the "loading" screen).
    await _show_main_menu_for(message)


async def _show_main_menu_for(message: Message) -> None:
    """Ensure the user row exists (starts the trial) and show the menu + banner."""
    from telegram_bot.subscriptions import get_account_status

    status = await get_account_status(user_id_from_message(message))
    banner = _ch.account_banner(status)
    if banner:
        await message.answer(banner, parse_mode=ParseMode.HTML)
    await _show_main_menu(message)


async def _status_text(telegram_id: int) -> str:
    from telegram_bot.subscriptions import get_account_status

    status = await get_account_status(telegram_id)
    if status.is_trial:
        return (
            "🎁 <b>Пробный период Pro</b>\n"
            f"Осталось: <b>{status.days_left} дн.</b>\n\n"
            "Открыты все функции. Чтобы сохранить доступ после пробного периода — "
            "оформите подписку: /subscribe"
        )
    if status.tier in ("pro", "enterprise"):
        name = "Enterprise" if status.tier == "enterprise" else "Pro"
        left = f"{status.days_left} дн." if status.days_left else "—"
        return (
            f"⭐ <b>Тариф {name}</b>\n"
            f"Активен ещё: <b>{left}</b>\n\n"
            "Продлить можно в любой момент: /subscribe"
        )
    return (
        "🔓 <b>Тариф Free</b>\n\n"
        "Доступны: топ облигаций, курсы, кривая доходности, карточка облигации "
        "с вердиктом.\n"
        "В Pro открываются: аналитика Desk, ML-прогнозы, доход по купонам, "
        "портфель и персональные алерты.\n\n"
        "Оформить Pro: /subscribe"
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    text = await _status_text(user_id_from_message(message))
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=_home_kb())


@router.callback_query(lambda c: c.data == "cmd_status")
async def cb_status(callback_query) -> None:
    uid = callback_query.from_user.id if callback_query.from_user else 0
    text = await _status_text(uid)
    await callback_query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=_home_kb())
    await callback_query.answer()


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


@router.message(Command("parse"))
async def cmd_parse(message: Message) -> None:
    if parse_lock.locked():
        await message.answer("⏳ Парсинг уже запущен другим пользователем. Подождите окончания.")
        return
    async with parse_lock:
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
        except Exception as exc:
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
        await _show_main_menu_for(message)


@router.message(Command("rates"))
async def cmd_rates(message: Message) -> None:
    if not await _ch.is_unlocked(message):
        await message.answer(_ch.locked_message())
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
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


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
# Overview
# ---------------------------------------------------------------------------


@router.message(Command("overview"))
async def cmd_overview(message: Message) -> None:
    title, kb = _OVERVIEW_MENU
    await message.answer(title, parse_mode=ParseMode.HTML, reply_markup=kb)


# ---------------------------------------------------------------------------
# Top / Scores
# ---------------------------------------------------------------------------


@router.message(Command("top"))
async def cmd_top(message: Message, page: int = 0) -> None:
    async with session_scope() as session:
        top = await top_scores(session, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
        if not top and page == 0:
            await message.answer("⏳ Данные ещё загружаются. Откройте /start и нажмите «🔄 Обновить данные».")
            return
        if not top:
            await message.answer("Нет облигаций на этой странице.")
            return
        bonds_map = {b.internal_id: b.name for b in await fetch_all_bonds()}
        lines = [f"<b>🏆 TOP Reward/Risk</b> (стр. {page + 1})\n"]
        for i, s in enumerate(top, page * PAGE_SIZE + 1):
            name_display = bonds_map.get(s.internal_id, "")
            name_part = f" — {name_display}" if name_display else ""
            lines.append(f"{i}. <code>{s.internal_id}</code>{name_part} — Score: {float(s.score):.0f} (0–100, выше — лучше)")
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
        await message.answer(f"Пока нет облигаций в {currency}. Данные обновляются — попробуйте позже.")
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
    total_pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    page_slice = rows[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

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
    await message.answer("\n".join(parts), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


@router.message(Command("new"))
async def cmd_new(message: Message) -> None:
    async with session_scope() as session:
        res = await session.execute(select(BondORM).order_by(desc(BondORM.fetched_at)).limit(10))
        bonds = list(res.scalars().all())
        if not bonds:
            await message.answer(
                "Пока нет свежих облигаций. Нажмите «🔄 Обновить данные» в меню, "
                "чтобы подтянуть котировки.",
                reply_markup=_home_kb(),
            )
            return
        lines = ["<b>🆕 Новые/обновлённые</b>\n"]
        for b in bonds:
            lines.append(f"• <code>{b.internal_id}</code> {b.name}")
        await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


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
        await message.answer(
            "⏳ Котировки ещё загружаются. Нажмите «🔄 Обновить данные» в меню, "
            "чтобы подтянуть свежие цены.",
            parse_mode=ParseMode.HTML,
            reply_markup=_home_kb(),
        )
        return
    alloc = allocate(bonds, prefs, top_n=10)
    forecasts = forecast_horizons(
        initial_capital=prefs.initial_capital,
        monthly_contribution=prefs.monthly_contribution,
        expected_annual_return_pct=max(alloc.expected_return, 0.1),
        volatility_pct=alloc.volatility,
    )
    text = (
        f"<b>📊 Портфель ({_STRATEGY_RU.get(alloc.strategy, alloc.strategy)})</b>\n\n"
        f"Капитал: <b>{fmt_num(prefs.initial_capital)} BYN</b>\n"
        f"Пополнение/мес: <b>{fmt_num(prefs.monthly_contribution)} BYN</b>\n"
        f"Ожидаемая доходность: <b>{alloc.expected_return:.2f}%</b>\n"
        f"Качество риска (Sharpe): <b>{alloc.sharpe:.2f}</b>, "
        f"Sortino: <b>{alloc.sortino:.2f}</b> — чем выше, тем стабильнее\n"
        f"Макс. просадка: <b>{alloc.max_drawdown:.2f}%</b>, риск потери (VaR 95%): "
        f"<b>{alloc.var_95:.2f}%</b>\n\n"
        f"<b>Прогноз капитала (BYN):</b>\n"
    )
    for f in forecasts:
        text += (
            f"  {f.horizon_years} г: {fmt_num(f.expected_capital)} "
            f"(от {fmt_num(f.pessimistic_capital)} до {fmt_num(f.optimistic_capital)})\n"
        )

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=_home_kb())
    png = plot_portfolio_pie(alloc)
    await message.answer_photo(BufferedInputFile(png, filename="portfolio.png"))


@router.message(Command("rebalance"))
async def cmd_rebalance(message: Message) -> None:
    uid = user_id_from_message(message)
    async with session_scope() as session:
        from telegram_bot.preferences_repository import get_preferences
        from telegram_bot.subscriptions import get_or_create_user_by_telegram

        prefs = await get_preferences(session, uid)
        user = await get_or_create_user_by_telegram(session, uid)
        bonds = await fetch_all_bonds()
        positions = await list_positions(session, user.id)
    if not bonds:
        await message.answer(
            "⏳ Котировки ещё загружаются. Нажмите «🔄 Обновить данные» в меню.",
            reply_markup=_home_kb(),
        )
        return
    if positions:
        current = {p.internal_id: p.amount for p in positions}
        source = "вашего портфеля"
    else:
        current = {
            iid: prefs.initial_capital / Decimal("10")
            for iid in [b.internal_id for b in bonds[:10]]
        }
        source = "модельного портфеля (добавьте свои позиции в «📌 Мои позиции»)"
    _target, deltas = rebalance(current, bonds, prefs)
    if not deltas:
        await message.answer("♻️ Ребалансировка не требуется — портфель сбалансирован.")
        return
    bonds_map_rb = {b.internal_id: b.name for b in bonds}
    lines = [f"<b>♻️ Ребалансировка ({source})</b>\n"]
    for iid, d in list(deltas.items())[:20]:
        sign = "+" if d >= 0 else ""
        n = bonds_map_rb.get(iid, "")
        n_part = f" ({n})" if n else ""
        lines.append(f"• <code>{iid}</code>{n_part}: {sign}{d}")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


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
        f"<b>📈 Прогноз капитала (BYN)</b>\n"
        f"Старт: {fmt_num(prefs.initial_capital)} BYN\n"
        f"Пополнение: {fmt_num(prefs.monthly_contribution)} BYN/мес\n"
        f"Ожидаемая доходность: 7% (по умолчанию)\n"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=_home_kb())
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
    lines.append("— изменение стоимости портфеля при шоке курса USD/BYN:")
    for r in results:
        lines.append(
            f"• <b>{r.scenario}</b>: курс → {r.usd_byn_end} ({r.fx_change_pct:+.1f}%), "
            f"стоимость портфеля {r.portfolio_value_change_pct:+.2f}%"
        )
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


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
        await message.answer(
            "🤖 Рекомендации пока формируются — модель обновляется. Загляните чуть позже.",
            reply_markup=_home_kb(),
        )
        return
    lines = ["<b>🛒 Рекомендации (Score + ML)</b>\n"]
    for r in recs:
        ret = f", +{r.predicted_return_pct:.2f}%" if r.predicted_return_pct is not None else ""
        lines.append(
            f"#{r.rank} <code>{r.internal_id}</code> {r.name} — "
            f"<b>{r.decision.upper()}</b> (уверенность {float(r.confidence):.0%}, score {r.score:.0f}{ret})"
        )
    lines.append(f"\n{DISCLAIMER_SHORT}")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


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
            parts.append(f"• <b>{kind}</b>: модель ещё обучается — скоро обновим")
            continue
        metrics = ", ".join(f"{k}={float(v):.3f}" for k, v in mv.metrics.items())
        parts.append(f"• <b>{kind}</b> v{mv.version} ({mv.train_rows} строк)\n  {metrics}")
    await message.answer("\n".join(parts), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


@router.message(Command("predict"))
async def cmd_predict(message: Message) -> None:
    bond_id = parse_bond_args(message)
    if not bond_id:
        await message.answer(
            "Откройте облигацию через 🔍 Облигации и нажмите «📈 ML-прогноз» — "
            "так прогноз подберётся автоматически.",
            reply_markup=_home_kb(),
        )
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
        await message.answer(
            "🔄 Прогнозы обновляются — загляните чуть позже.",
            reply_markup=_home_kb(),
        )
        return
    p = rows[0]
    expl = "\n".join(f"  • {e}" for e in (p.explanation or []))
    text = (
        f"<b>📈 Прогноз {bond_id}</b> ({bond_name})\n"
        f"Решение: <b>{p.decision}</b> (уверенность {float(p.confidence):.0%})\n"
        f"Прогноз доходности (YTM): {float(p.predicted_ytm) if p.predicted_ytm is not None else '—'}\n"
        f"Прогноз доходности: {float(p.predicted_return_pct) if p.predicted_return_pct is not None else '—'}\n"
        f"Объяснение:\n{expl or '—'}\n\n{DISCLAIMER_SHORT}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=_home_kb())


@router.message(Command("rebalance-auto"))
async def cmd_rebalance_auto(message: Message) -> None:
    uid = user_id_from_message(message)
    _bond_dicts, _history = await fetch_bonds_with_history()
    async with session_scope() as session:
        from telegram_bot.preferences_repository import get_preferences
        from telegram_bot.subscriptions import get_or_create_user_by_telegram

        prefs = await get_preferences(session, uid)
        user = await get_or_create_user_by_telegram(session, uid)
        positions = await list_positions(session, user.id)
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
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


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
            await message.answer(
                "Избранное пусто. Откройте 🔍 Облигации и нажмите «⭐ В избранное».",
                reply_markup=_home_kb(),
            )
            return
        from scraper.orm import BondORM
        result_bonds = await session.execute(
            select(BondORM).where(BondORM.internal_id.in_(prefs.watchlist))
        )
        watch_bonds = {b.internal_id: b.name for b in result_bonds.scalars().all()}
        lines = ["<b>👀 Избранное</b>\n"]
        for iid in prefs.watchlist:
            sc = await get_score(session, iid)
            score_text = f"Score {float(sc.score):.0f}" if sc else "нет скора"
            name_display = watch_bonds.get(iid, "")
            name_part = f" ({name_display})" if name_display else ""
            lines.append(f"• <code>{iid}</code>{name_part} — {score_text}")
        await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


@router.message(Command("watch"))
async def cmd_watch(message: Message) -> None:
    iid = parse_bond_args(message)
    if not iid:
        await message.answer(
            "Откройте облигацию через 🔍 Облигации и нажмите «⭐ В избранное».",
            reply_markup=_home_kb(),
        )
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
        f"✅ <code>{iid}</code> ({bond_name}) добавлен в избранное ({len(prefs.watchlist)} шт.)",
        parse_mode=ParseMode.HTML,
        reply_markup=_home_kb(),
    )


@router.message(Command("unwatch"))
async def cmd_unwatch(message: Message) -> None:
    iid = parse_bond_args(message)
    if not iid:
        await message.answer(
            "Откройте облигацию в 🔍 Облигации и нажмите «🗑 Из избранного».",
            reply_markup=_home_kb(),
        )
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
    await message.answer(
        f"❌ <code>{iid}</code> ({bond_name}) убран из избранного", parse_mode=ParseMode.HTML,
        reply_markup=_home_kb(),
    )


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@router.message(Command("alerts"))
async def cmd_alerts(message: Message) -> None:
    from telegram_bot.subscriptions import get_or_create_user_by_telegram

    telegram_id = user_id_from_message(message)
    lines: list[str] = []
    async with session_scope() as session:
        user = await get_or_create_user_by_telegram(session, telegram_id)
        rules = await list_rules(session, user.id)
        events = await list_events(session, user.id, limit=5)
        system = await list_recent(session, limit=5)

    if rules:
        lines.append("<b>🔔 Мои алерты</b>")
        for r in rules:
            sign = alert_direction_sign(r.direction)
            label = alert_metric_label(r.metric)
            lines.append(f"• {r.internal_id}: {label} {sign} {fmt_num(r.threshold)}")
        lines.append("")
    if events:
        lines.append("<b>✅ Сработавшие</b>")
        for e in events:
            lines.append(f"• {e.message}")
        lines.append("")
    if system:
        lines.append("<b>📰 Рыночные события</b>")
        for a in system:
            lines.append(f"• <b>{a.title}</b>\n  {a.message}")

    if not lines:
        lines = [
            "🔔 <b>Алертов пока нет.</b>\n",
            "Откройте любую облигацию (🔍 Облигации) и нажмите "
            "«🔔 Следить за ценой», чтобы получать уведомления.",
        ]
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


# ---------------------------------------------------------------------------
# Desk
# ---------------------------------------------------------------------------


@router.message(Command("desk"))
async def cmd_desk(message: Message) -> None:
    title, kb = _DESK_MENU
    await message.answer(title, parse_mode=ParseMode.HTML, reply_markup=kb)


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
            f"<b>{cur}</b> — наклон кривой: {curve.slope():.2f}% "
            f"(уровень {params.beta0:.2f}, изгиб {params.beta1:.2f}, длинный конец {params.beta2:.2f})"
        )
        for p in curve.points:
            lines.append(f"  {p.tenor}: {p.rate_pct:.2f}%")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


@router.message(Command("rv"))
async def cmd_rv(message: Message, page: int = 0) -> None:
    bonds = await bonds_for_bot()
    signals = desk_rv.relative_value_signals(bonds)
    if not signals:
        await message.answer(
            "Пока нет сигналов Relative Value. Нажмите «🔄 Обновить данные» в меню.",
            reply_markup=_home_kb(),
        )
        return
    total_pages = max(1, (len(signals) + PAGE_SIZE - 1) // PAGE_SIZE)
    page_slice = signals[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    bonds_map_rv = {b.internal_id: b.name for b in bonds}
    lines = [f"<b>⚖️ Relative Value</b> (стр. {page + 1}/{total_pages})\n"]
    for s in page_slice:
        sign = "🟢 BUY" if s.side == "buy" else ("🔴 SELL" if s.side == "sell" else "⚪ HOLD")
        n = bonds_map_rv.get(s.internal_id, "")
        n_part = f" {n}" if n else ""
        lines.append(
            f"{sign} <code>{s.internal_id}</code>{n_part} (отклонение Z={s.z_score:+.2f}, спред {s.spread_pct:+.2f}%)"
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
        title = f"<b>⏱ Duration — {bond.internal_id}</b> ({bond.name})\n"
    else:
        weights = {b.internal_id: 1 / len(bonds) for b in bonds} if bonds else {}
        rep = desk_duration.portfolio_duration(bonds, weights=weights)
        title = "<b>⏱ Duration (Портфель)</b>\n"
    lines = [
        title,
        f"Дюрация Маколея: <b>{rep.macaulay_duration:.2f}</b> (срок в годах)",
        f"Модифицированная дюрация: <b>{rep.modified_duration:.2f}</b> — чувствительность цены к ставке",
        f"Выпуклость: <b>{rep.convexity:.2f}</b>",
        f"DV01: <b>{rep.dv01:.4f}</b> — изменение цены при росте ставки на 0.01 п.п.",
        "<b>Дюрация по срокам:</b>",
    ]
    for tenor, krd in rep.key_rate_durations.items():
        lines.append(f"  {tenor}: {krd:.4f}")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


@router.message(Command("carry"))
async def cmd_carry(message: Message, page: int = 0) -> None:
    funding = parse_funding_rate(message)
    bonds = await bonds_for_bot()
    trades = desk_carry.rank_carry(bonds, funding_rate_pct=funding)
    if not trades:
        await message.answer(
            "Пока нет данных для carry-анализа. Нажмите «🔄 Обновить данные» в меню.",
            reply_markup=_home_kb(),
        )
        return
    total_pages = max(1, (len(trades) + PAGE_SIZE - 1) // PAGE_SIZE)
    page_slice = trades[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    bonds_map_carry = {b.internal_id: b.name for b in bonds}
    lines = [f"<b>💰 Carry — доход от удержания (ставка фондирования {funding}%)</b> (стр. {page + 1}/{total_pages})\n"]
    for t in page_slice:
        sign = "🟢" if t.expected_pnl_pct > 0 else "🔴"
        n = bonds_map_carry.get(t.internal_id, "")
        n_part = f" {n}" if n else ""
        lines.append(
            f"{sign} <code>{t.internal_id}</code>{n_part}: купон {t.coupon_pct:.2f}%, "
            f"доход от схлопывания кривой {t.rolldown_bps:+.1f} п.п., "
            f"прибыль {t.expected_pnl_pct:+.3f}%"
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
        await message.answer(
            "Откройте облигацию в 🔍 Облигации → «🔬 Для профи» → «🏦 РЕПО» — "
            "сделка рассчитается автоматически.",
            reply_markup=_home_kb(),
        )
        return
    internal_id = args[1]
    try:
        notional = float(args[2]) if len(args) > 2 else 1000.0
        tenor = int(args[3]) if len(args) > 3 else 30
    except (ValueError, IndexError):
        await message.answer(
            "Откройте облигацию в 🔍 Облигации → «🔬 Для профи» → «🏦 РЕПО» — "
            "сделка рассчитается автоматически.",
            reply_markup=_home_kb(),
        )
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
        f"Залог: <b>{deal.collateral_value}</b>\n"
        f"Скидка к залогу (haircut): {deal.haircut_pct}%\n"
        f"Кэш выдано: <b>{deal.cash_lent}</b>\n"
        f"Ставка: {deal.repo_rate_pct}%, срок {deal.tenor_days} дн.\n"
        f"Проценты: {deal.accrued_interest}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=_home_kb())


@router.message(Command("stress"))
async def cmd_stress(message: Message) -> None:
    bonds = await bonds_for_bot()
    weights = {b.internal_id: Decimal("1000") for b in bonds}
    lines = ["<b>⚠️ Стресс-тесты (изменение стоимости портфеля)</b>\n"]
    for name, scn in desk_stress.PRESET_SCENARIOS.items():
        res = desk_stress.run_stress(scn, [(b, weights[b.internal_id]) for b in bonds])
        lines.append(f"• <b>{name}</b> ({scn.kind}): {res.pnl_pct:+.3f}% ({float(res.pnl):+.0f})")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())


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
        lines.append(f"  {s.internal_id}{n_part}: отклонение Z={float(s.z_score):+.2f} ({s.side})")
    lines.append("\n<b>Стресс-тесты (недавние):</b>")
    for r in stress_runs:
        lines.append(f"  {r.scenario_name}: изменение стоимости {float(r.pnl_pct):+.3f}%")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=_home_kb())
