"""Telegram-бот: aiogram 3, команды /start /top /portfolio /forecast и др."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.dispatcher.middlewares.base import BaseMiddleware
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
from monitoring.engine import detect_bond_changes, detect_fx_changes, detect_metal_changes
from notifications.fx_repository import latest_fx
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
from scraper.orm import BondHistoryORM, BondORM
from telegram_bot.preferences_repository import (
    add_to_watchlist,
    get_preferences,
    remove_from_watchlist,
    upsert_preferences,
)
from visualization.charts import (
    plot_capital_forecast,
    plot_portfolio_pie,
    plot_yield_distribution,
)


class ThrottlingMiddleware(BaseMiddleware):
    """Limits user requests to N per interval."""

    def __init__(self, rate: int = 3, per_seconds: int = 1) -> None:
        self.rate = rate
        self.per_seconds = per_seconds
        self._users: dict[int, list[float]] = defaultdict(list)

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user is not None:
            now = time.monotonic()
            uid = user.id
            timestamps = self._users[uid]
            cutoff = now - self.per_seconds
            timestamps[:] = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= self.rate:
                return
            timestamps.append(now)
        return await handler(event, data)


class RequestIdMiddleware(BaseMiddleware):
    """Adds request_id to handlers data for tracing."""

    async def __call__(self, handler, event, data):
        data["request_id"] = uuid.uuid4().hex[:8]
        return await handler(event, data)


router = Router()
_PAGE_SIZE = 10


def _paginate_kb(prefix: str, page: int, total: int) -> InlineKeyboardMarkup | None:
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"page:{prefix}:{page - 1}"))
    if page < total - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"page:{prefix}:{page + 1}"))
    if not buttons:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


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
        await handler(callback_query.message, page=page)


async def _fetch_bonds_by_currency(currency: str) -> list:
    async with session_scope() as session:
        return list(await repositories.bonds.get_by_currency(session, currency))


async def _fetch_all_bonds(limit: int = 500):
    async with session_scope() as session:
        res = await session.execute(select(BondORM).limit(limit))
        return list(res.scalars().all())


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    text = (
        "👋 <b>Bond Fixed Income Assistant</b>\n\n"
        "V4 — Mini Fixed Income Desk:\n"
        "/desk — меню desk\n"
        "/curve — кривая доходности (NS)\n"
        "/rv — Relative Value (rich/cheap)\n"
        "/duration [ID] — duration-отчёт\n"
        "/carry [funding] — carry-ранжирование\n"
        "/repo ID — сделка РЕПО\n"
        "/stress — стресс-тесты (7 пресетов)\n\n"
        "V3 — ML:\n"
        "/ml — статус моделей\n"
        "/predict ID — прогноз\n"
        "/buy — рекомендации\n"
        "/rebalance-auto — drift-детект\n\n"
        "V2 — Portfolio:\n"
        "/top — TOP Reward/Risk\n"
        "/usd /byn /metals /new\n"
        "/portfolio /rebalance /forecast /scenario\n"
        "/watchlist /watch ID /unwatch ID\n\n"
        "Сервис:\n"
        "/alerts — последние алерты\n"
        "/help — список команд"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏛 Desk", callback_data="cmd_desk"),
                InlineKeyboardButton(text="🏆 Top", callback_data="cmd_top"),
            ],
            [
                InlineKeyboardButton(text="💼 Portfolio", callback_data="cmd_portfolio"),
                InlineKeyboardButton(text="📊 Curve", callback_data="cmd_curve"),
            ],
            [
                InlineKeyboardButton(text="🛒 Buy", callback_data="cmd_buy"),
                InlineKeyboardButton(text="📈 Forecast", callback_data="cmd_forecast"),
            ],
        ]
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=kb)


@router.callback_query(lambda c: c.data == "cmd_desk")
async def cb_desk(callback_query) -> None:
    await cmd_desk(callback_query.message)


@router.callback_query(lambda c: c.data == "cmd_top")
async def cb_top(callback_query) -> None:
    await cmd_top(callback_query.message)


@router.callback_query(lambda c: c.data == "cmd_portfolio")
async def cb_portfolio(callback_query) -> None:
    await cmd_portfolio(callback_query.message)


@router.callback_query(lambda c: c.data == "cmd_curve")
async def cb_curve(callback_query) -> None:
    await cmd_curve(callback_query.message)


@router.callback_query(lambda c: c.data == "cmd_buy")
async def cb_buy(callback_query) -> None:
    await cmd_buy(callback_query.message)


@router.callback_query(lambda c: c.data == "cmd_forecast")
async def cb_forecast(callback_query) -> None:
    await cmd_forecast(callback_query.message)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await cmd_start(message)


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
        lines = [f"<b>🏆 TOP Reward/Risk</b> (стр. {page + 1})\n"]
        for i, s in enumerate(top, page * _PAGE_SIZE + 1):
            lines.append(f"{i}. <code>{s.internal_id}</code> — Score: {float(s.score):.0f}")
        total = page + 1 if len(top) == _PAGE_SIZE else page + 1
        await message.answer(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=_paginate_kb("top", page, total),
        )


async def _currency_view(message: Message, currency: str, title: str, page: int = 0) -> None:
    prefix = currency.lower()
    bonds = await _fetch_bonds_by_currency(currency)
    if not bonds:
        await message.answer(f"Нет облигаций в {currency}. Запустите парсер.")
        return
    rows = []
    for b in bonds:
        score = score_bond(
            internal_id=b.internal_id,
            yield_to_maturity=b.yield_to_maturity,
            currency=b.currency,
            maturity_date=b.maturity_date,
            status=b.status,
            issuer=b.issuer,
            price=b.price,
        )
        ytm = f"{float(b.yield_to_maturity):.2f}%" if b.yield_to_maturity else "—"
        rows.append((b.internal_id, float(score.score), ytm, b.name))

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
        except ValueError, AttributeError:
            val = 0.0
        safe_ytm.append((iid, val))
    png = plot_yield_distribution(safe_ytm)
    await message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=_paginate_kb(prefix[:3], page, total_pages),
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
    for cur, title in (("XAU", "🥇 Золото"), ("XAG", "🥈 Серебро"), ("XPT", "⚪ Платина")):
        bonds = await _fetch_bonds_by_currency(cur)
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
        parts.append(f"{title}: <code>{best.internal_id}</code> Score {s.score:.0f}")
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


@router.message(Command("portfolio"))
async def cmd_portfolio(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
        bonds = await _fetch_all_bonds()
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
    user_id = message.from_user.id if message.from_user else 0
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
        bonds = await _fetch_all_bonds()
    if not bonds:
        await message.answer("Нет данных.")
        return
    current = {
        iid: prefs.initial_capital / Decimal("10") for iid in [b.internal_id for b in bonds[:10]]
    }
    target, deltas = rebalance(current, bonds, prefs)
    if not deltas:
        await message.answer("Ребалансировка не требуется.")
        return
    lines = ["<b>♻️ Ребалансировка</b>\n"]
    for iid, d in list(deltas.items())[:20]:
        sign = "+" if d >= 0 else ""
        lines.append(f"• <code>{iid}</code>: {sign}{d}")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("forecast"))
async def cmd_forecast(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
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


@router.message(Command("scenario"))
async def cmd_scenario(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
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


@router.message(Command("buy"))
async def cmd_buy(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
    bond_dicts, history = await _fetch_bonds_with_history()
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


async def _fetch_bonds_with_history() -> tuple[list[dict], dict[str, list[dict]]]:
    async with session_scope() as session:
        bonds_q = await session.execute(select(BondORM))
        history_q = await session.execute(select(BondHistoryORM))
        bonds = list(bonds_q.scalars().all())
        history = list(history_q.scalars().all())
    history_by: dict[str, list[dict]] = {}
    for h in history:
        history_by.setdefault(h.internal_id, []).append(
            {"date": h.date, "price": h.price, "yield": h.yield_, "coupon": h.coupon}
        )
    return (
        [
            {
                "internal_id": b.internal_id,
                "name": b.name,
                "currency": b.currency,
                "yield_to_maturity": b.yield_to_maturity,
                "coupon_rate": b.coupon_rate,
                "maturity_date": b.maturity_date,
                "price": b.price,
                "status": b.status,
                "issuer": b.issuer,
            }
            for b in bonds
        ],
        history_by,
    )


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
    args = (message.text or "").split(maxsplit=1)
    bond_id = args[1].strip() if len(args) > 1 else ""
    if not bond_id:
        await message.answer("Использование: /predict OP-51")
        return
    async with session_scope() as session:
        rows = await predictions_for_bond(session, bond_id, limit=1)
    if not rows:
        await message.answer("Нет прогнозов. Запустите `python -m scraper ml-predict`.")
        return
    p = rows[0]
    expl = "\n".join(f"  • {e}" for e in (p.explanation or []))
    text = (
        f"<b>📈 Прогноз {p.internal_id}</b>\n"
        f"Решение: <b>{p.decision}</b> (conf {float(p.confidence):.2f})\n"
        f"Predicted YTM: {float(p.predicted_ytm) if p.predicted_ytm is not None else '—'}\n"
        f"Predicted return: {float(p.predicted_return_pct) if p.predicted_return_pct is not None else '—'}\n"
        f"Объяснение:\n{expl or '—'}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("rebalance-auto"))
async def cmd_rebalance_auto(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    bond_dicts, history = await _fetch_bonds_with_history()
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
        positions = await list_positions(session, user_id)
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
        lines.append(
            f"• <b>{a.side.upper()}</b> {a.internal_id}: {a.amount} "
            f"({a.weight_before:.2%} → {a.weight_after:.2%})"
        )
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("watchlist"))
async def cmd_watchlist(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
        if not prefs.watchlist:
            await message.answer("Watchlist пуст. Добавьте: /watch OP-51")
            return
        lines = ["<b>👀 Watchlist</b>\n"]
        for iid in prefs.watchlist:
            sc = await get_score(session, iid)
            score_text = f"Score {float(sc.score):.0f}" if sc else "нет скора"
            lines.append(f"• <code>{iid}</code> — {score_text}")
        await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("watch"))
async def cmd_watch(message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /watch OP-51")
        return
    iid = args[1].strip()
    async with session_scope() as session:
        if not await repositories.bonds.exists(session, iid):
            await message.answer(
                f"❌ Облигация <code>{iid}</code> не найдена в БД", parse_mode=ParseMode.HTML
            )
            return
    user_id = message.from_user.id if message.from_user else 0
    async with session_scope() as session:
        prefs = await add_to_watchlist(session, user_id, iid)
    await message.answer(
        f"✅ <code>{iid}</code> добавлен в watchlist ({len(prefs.watchlist)} шт.)",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("unwatch"))
async def cmd_unwatch(message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /unwatch OP-51")
        return
    iid = args[1].strip()
    async with session_scope() as session:
        if not await repositories.bonds.exists(session, iid):
            await message.answer(
                f"❌ Облигация <code>{iid}</code> не найдена в БД", parse_mode=ParseMode.HTML
            )
            return
    user_id = message.from_user.id if message.from_user else 0
    async with session_scope() as session:
        await remove_from_watchlist(session, user_id, iid)
    await message.answer(f"❌ <code>{iid}</code> убран из watchlist", parse_mode=ParseMode.HTML)


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


@router.message(Command("desk"))
async def cmd_desk(message: Message) -> None:
    text = (
        "<b>🏛 Mini Fixed Income Desk</b>\n\n"
        "Команды:\n"
        "/curve — кривая доходности (Nelson-Siegel)\n"
        "/rv — Relative Value (rich/cheap)\n"
        "/duration [ID] — duration-отчёт\n"
        "/carry [funding] — carry-ранжирование\n"
        "/repo ID [notional] [tenor] — сделка РЕПО\n"
        "/stress — стресс-тесты (7 пресетов)\n"
        "/desk_status — последние сигналы"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


async def _bonds_for_bot():
    async with session_scope() as session:
        res = await session.execute(select(BondORM))
        orm_bonds = list(res.scalars().all())
        return [
            Bond(
                internal_id=b.internal_id,
                name=b.name,
                currency=b.currency,
                yield_to_maturity=b.yield_to_maturity,
                coupon_rate=b.coupon_rate,
                coupon_frequency=b.coupon_frequency,
                maturity_date=b.maturity_date,
                price=b.price,
                issuer=b.issuer,
                status=b.status,
                nominal=b.nominal,
                fetched_at=b.fetched_at,
            )
            for b in orm_bonds
        ]


@router.message(Command("curve"))
async def cmd_curve(message: Message) -> None:
    bonds = await _bonds_for_bot()
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
            f"<b>{cur}</b> — slope {curve.slope():.2f}%, β0={params.beta0:.2f}, β1={params.beta1:.2f}, β2={params.beta2:.2f}"
        )
        for p in curve.points:
            lines.append(f"  {p.tenor}: {p.rate_pct:.2f}%")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@router.message(Command("rv"))
async def cmd_rv(message: Message, page: int = 0) -> None:
    bonds = await _bonds_for_bot()
    signals = desk_rv.relative_value_signals(bonds)
    if not signals:
        await message.answer("Нет данных для Relative Value.")
        return
    total_pages = max(1, (len(signals) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page_slice = signals[page * _PAGE_SIZE : (page + 1) * _PAGE_SIZE]
    lines = [f"<b>⚖️ Relative Value</b> (стр. {page + 1}/{total_pages})\n"]
    for s in page_slice:
        sign = "🟢 BUY" if s.side == "buy" else ("🔴 SELL" if s.side == "sell" else "⚪ HOLD")
        lines.append(
            f"{sign} <code>{s.internal_id}</code> (Z={s.z_score:+.2f}, spread {s.spread_pct:+.2f}%)"
        )
    await message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=_paginate_kb("rv", page, total_pages),
    )


@router.message(Command("duration"))
async def cmd_duration(message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)
    bonds = await _bonds_for_bot()
    if len(args) > 1:
        bond = next((b for b in bonds if b.internal_id == args[1].strip()), None)
        if bond is None:
            await message.answer(f"Облигация {args[1]} не найдена")
            return
        rep = desk_duration.duration_report(bond)
    else:
        weights = {b.internal_id: 1 / len(bonds) for b in bonds} if bonds else {}
        rep = desk_duration.portfolio_duration(bonds, weights=weights)
    lines = [
        "<b>⏱ Duration Report</b>\n",
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
    args = (message.text or "").split()
    funding = 5.0
    if len(args) > 1:
        try:
            funding = float(args[1])
        except ValueError:
            funding = 5.0
    bonds = await _bonds_for_bot()
    trades = desk_carry.rank_carry(bonds, funding_rate_pct=funding)
    if not trades:
        await message.answer("Нет данных для carry-анализа")
        return
    total_pages = max(1, (len(trades) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page_slice = trades[page * _PAGE_SIZE : (page + 1) * _PAGE_SIZE]
    lines = [f"<b>💰 Carry (funding {funding}%)</b> (стр. {page + 1}/{total_pages})\n"]
    for t in page_slice:
        sign = "🟢" if t.expected_pnl_pct > 0 else "🔴"
        lines.append(
            f"{sign} <code>{t.internal_id}</code>: купон {t.coupon_pct:.2f}%, "
            f"rolldown {t.rolldown_bps:+.1f}bp, P&L {t.expected_pnl_pct:+.3f}%"
        )
    await message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=_paginate_kb("carry", page, total_pages),
    )


@router.message(Command("repo"))
async def cmd_repo(message: Message) -> None:
    args = (message.text or "").split()
    if len(args) < 2:
        await message.answer("Использование: /repo OP-51 [notional=1000] [tenor_days=30]")
        return
    internal_id = args[1]
    notional = float(args[2]) if len(args) > 2 else 1000.0
    tenor = int(args[3]) if len(args) > 3 else 30
    bonds = await _bonds_for_bot()
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
        f"<b>🏦 РЕПО {internal_id}</b>\n"
        f"Залог: {deal.collateral_value}\n"
        f"Haircut: {deal.haircut_pct}%\n"
        f"Кэш выдано: {deal.cash_lent}\n"
        f"Ставка: {deal.repo_rate_pct}%, тенор {deal.tenor_days}d\n"
        f"Проценты: {deal.accrued_interest}"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("stress"))
async def cmd_stress(message: Message) -> None:
    bonds = await _bonds_for_bot()
    weights = {b.internal_id: Decimal("1000") for b in bonds}
    lines = ["<b>⚠️ Stress-тесты (Δ P&L)</b>\n"]
    for name, scn in desk_stress.PRESET_SCENARIOS.items():
        res = desk_stress.run_stress(scn, [(b, weights[b.internal_id]) for b in bonds])
        lines.append(f"• <b>{name}</b> ({scn.kind}): {res.pnl_pct:+.3f}% ({float(res.pnl):+.0f})")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


_PRESETS = {
    "Conserv": (0.3, 0.5, 0.1, 0.1),
    "Balanced": (0.5, 0.3, 0.2, 0.0),
    "Aggressv": (0.7, 0.1, 0.1, 0.1),
    "Metals++": (0.2, 0.1, 0.6, 0.1),
}


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
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
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    label = callback_query.data.split(":", 1)[1]
    shares = _PRESETS[label]
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
        prefs.share_usd = shares[0]
        prefs.share_byn = shares[1]
        prefs.share_metals = shares[2]
        prefs.share_eur = shares[3]
        prefs.strategy = label  # type: ignore[assignment]
        await upsert_preferences(session, prefs)
    await callback_query.message.edit_text(
        f"✅ Применён пресет <b>{label}</b>: "
        f"USD {shares[0]:.0%}, BYN {shares[1]:.0%}, "
        f"Metals {shares[2]:.0%}, EUR {shares[3]:.0%}",
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("edit:"))
async def cb_edit(callback_query) -> None:
    field = callback_query.data.split(":", 1)[1]
    hints = {
        "capital": "Используйте: /set capital 50000",
        "contribution": "Используйте: /set contribution 2000",
    }
    text = hints.get(field, f"Используйте /set {field} <значение>")
    await callback_query.message.edit_text(text, parse_mode=ParseMode.HTML)


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
    user_id = message.from_user.id if message.from_user else 0
    async with session_scope() as session:
        prefs = await get_preferences(session, user_id)
        try:
            if field == "capital":
                prefs.initial_capital = Decimal(val_str.replace(",", ""))
            elif field == "contribution":
                prefs.monthly_contribution = Decimal(val_str.replace(",", ""))
            elif field == "strategy":
                prefs.strategy = val_str.capitalize()  # type: ignore[assignment]
            elif field in ("share_usd", "share_byn", "share_metals", "share_eur"):
                setattr(prefs, field, float(val_str))
                total = prefs.share_usd + prefs.share_byn + prefs.share_metals + prefs.share_eur
                if abs(total - 1.0) > 0.01:
                    await message.answer(f"⚠️ Сумма долей {total:.0%}, рекомендуется 100%")
                    return
            else:
                await message.answer(f"Неизвестное поле: {field}")
                return
            await upsert_preferences(session, prefs)
        except (ValueError, InvalidOperation) as exc:
            await message.answer(f"Ошибка: {exc}")
            return
    await message.answer(f"✅ <b>{field}</b> = {val_str}", parse_mode=ParseMode.HTML)


_ADMIN_IDS = {int(v) for v in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if v.strip()}


def _is_admin(message: Message) -> bool:
    uid = message.from_user.id if message.from_user else 0
    return uid in _ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message):
        return
    text = (
        "<b>🔧 Admin panel</b>\n\n"
        "/broadcast &lt;text&gt; — отправить всем\n"
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
        result = await session.execute(select(BondORM.internal_id).limit(1))
        users = list(result.scalars().all())  # stub — нет таблицы users
    await message.answer(f"📢 Сообщение отправлено {len(users)} пользователям (stub)")


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


@router.message(Command("desk_status"))
async def cmd_desk_status(message: Message) -> None:
    async with session_scope() as session:
        rv = await latest_rv_signals(session, limit=5)
        stress_runs = await latest_stress_runs(session, limit=3)
    lines = ["<b>🏛 Desk Status</b>\n"]
    lines.append("<b>RV (top-5):</b>")
    for s in rv:
        lines.append(f"  {s.internal_id}: Z={float(s.z_score):+.2f} ({s.side})")
    lines.append("\n<b>Stress (recent):</b>")
    for r in stress_runs:
        lines.append(f"  {r.scenario_name}: P&L {float(r.pnl_pct):+.3f}%")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


async def _run_monitoring(session) -> str:
    bond = await detect_bond_changes(session)
    fx = await detect_fx_changes(session)
    met = await detect_metal_changes(session)
    return (
        f"Мониторинг выполнен: bonds={bond.new_alerts}, fx={fx.new_alerts}, metals={met.new_alerts}"
    )


@router.errors(ExceptionTypeFilter(Exception))
async def global_error_handler(event: ErrorEvent):
    logger.exception("bot_handler_error", update=event.update, error=str(event.exception))
    if event.update.message:
        await event.update.message.answer(
            "❌ Внутренняя ошибка. Попробуйте позже или напишите /help.",
        )


async def main(token: str) -> None:
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    dp.message.middleware(ThrottlingMiddleware())
    dp.message.middleware(RequestIdMiddleware())

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: None)
    except NotImplementedError:
        pass

    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        webhook_path = os.getenv("WEBHOOK_PATH", "/webhook")
        await bot.set_webhook(webhook_url + webhook_path)
        from aiohttp import web

        app = web.Application()
        app.router.add_post(webhook_path, lambda r: dp.dispatch(r))
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("WEBHOOK_PORT", "8080"))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("webhook_started", url=webhook_url, port=port)
        await asyncio.Event().wait()
    else:
        try:
            await dp.start_polling(bot, handle_signals=True)
        finally:
            await bot.close()


def _validate_env() -> tuple[str | None, str | None]:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    missing: list[str] = []
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not os.getenv("DATABASE_URL"):
        missing.append("DATABASE_URL")
    if missing:
        return None, f"FATAL: missing env vars: {', '.join(missing)}"
    return token, None


def cli() -> int:
    token, error = _validate_env()
    if error:
        print(error)
        return 1
    asyncio.run(main(token))  # type: ignore[arg-type]
    return 0


if __name__ == "__main__":
    sys.exit(cli())
