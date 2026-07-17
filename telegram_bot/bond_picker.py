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
from notifications.alerts_repository import create_rule, list_rules
from portfolio.income import annual_income, bond_cashflows
from scoring.disclaimer import DISCLAIMER_SHORT
from scoring.engine import score_bond
from scoring.explain import explain_score
from scoring.repository import get_score, score_from_orm
from scraper.db import session_scope
from scraper.orm import BondORM
from telegram_bot.handler_state import BOND_PAGE
from telegram_bot.helpers import (
    alert_direction_sign,
    alert_metric_label,
    bonds_for_bot,
    fetch_all_bonds,
    fetch_bonds_by_currency,
    fmt_num,
)
from telegram_bot.preferences_repository import add_to_watchlist, remove_from_watchlist
from telegram_bot.subscriptions import (
    get_or_create_user_by_telegram,
    get_tier_by_telegram,
    meets_tier,
)

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
        await callback_query.answer("Данные ещё загружаются. Откройте /start → «Обновить данные».", show_alert=True)
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
    card = await _bond_card_text(iid)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💡 Стоит купить?", callback_data=f"bondact:{iid}:analysis"),
                InlineKeyboardButton(text="💰 Доход", callback_data=f"bondact:{iid}:income"),
            ],
            [
                InlineKeyboardButton(text="🔔 Следить за ценой", callback_data=f"bondact:{iid}:watchprice"),
                InlineKeyboardButton(text="➕ В портфель", callback_data=f"pos:add:{iid}"),
            ],
            [
                InlineKeyboardButton(text="📈 ML-прогноз", callback_data=f"bondact:{iid}:predict"),
                InlineKeyboardButton(text="🔬 Для профи", callback_data=f"bondact:{iid}:protools"),
            ],
            [
                InlineKeyboardButton(text="⭐ В избранное", callback_data=f"bondact:{iid}:watch"),
                InlineKeyboardButton(text="🗑 Из избранного", callback_data=f"bondact:{iid}:unwatch"),
            ],
            [
                InlineKeyboardButton(text="⬅️ К списку", callback_data="bonds:menu"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
            ],
        ]
    )
    await callback_query.message.edit_text(
        card,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    await callback_query.answer()


async def _bond_card_text(iid: str) -> str:
    """Compact, information-first bond card: key facts + rating verdict."""
    bonds = await bonds_for_bot()
    bond = next((b for b in bonds if b.internal_id == iid), None)
    if bond is None:
        async with session_scope() as session:
            name = await _bond_name(session, iid)
        return f"🔍 <b>{iid}</b> — {name}\n\nВыберите действие:"

    async with session_scope() as session:
        orm = await get_score(session, iid)
    score = (
        score_from_orm(orm)
        if orm is not None
        else score_bond(
            internal_id=iid,
            yield_to_maturity=bond.yield_to_maturity,
            currency=bond.currency,
            maturity_date=bond.maturity_date,
            status=bond.status,
            issuer=bond.issuer,
            price=bond.price,
        )
    )
    ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity else None
    explained = explain_score(score, currency=bond.currency, ytm_pct=ytm)

    facts = [f"💱 {bond.currency}"]
    if bond.maturity_date:
        facts.append(f"погашение {bond.maturity_date}")
    price_line = []
    if bond.price:
        price_line.append(f"цена {fmt_num(bond.price)}")
    if bond.yield_to_maturity:
        price_line.append(f"доходность {fmt_num(bond.yield_to_maturity)}%")
    if bond.coupon_rate:
        freq = f" × {bond.coupon_frequency}/год" if bond.coupon_frequency else ""
        price_line.append(f"купон {fmt_num(bond.coupon_rate)}%{freq}")

    lines = [f"🔍 <b>{iid}</b> — {bond.name}", " · ".join(facts)]
    if price_line:
        lines.append(" · ".join(price_line))
    lines.append(f"⭐ Рейтинг: <b>{score.tier}</b> ({score.score:.0f}) — {explained.verdict}")
    lines.append("\nВыберите действие:")
    return "\n".join(lines)


async def _run_bond_action(callback_query, iid: str, action: str) -> None:
    async with session_scope() as session:
        name = await _bond_name(session, iid)

    # Pro-gated actions reached via the bond picker (callbacks, not commands).
    if action in ("predict", "duration", "repo", "income", "watchprice"):
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
                "Прогнозы, доход по купонам, слежение за ценой и другое — "
                "по подписке через Telegram Stars.\n"
                "Нажмите /subscribe, чтобы выбрать тариф.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_kb,
            )
            await callback_query.answer()
            return

    # Alert setup has its own preset keyboard, so it returns early.
    if action == "watchprice":
        await _show_alert_presets(callback_query, iid)
        return

    # Trader tools live behind a dedicated sub-menu to keep the card clean.
    if action == "protools":
        tools_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⏱ Duration", callback_data=f"bondact:{iid}:duration"),
                    InlineKeyboardButton(text="🏦 РЕПО", callback_data=f"bondact:{iid}:repo"),
                ],
                [InlineKeyboardButton(text="⬅️ Назад к облигации", callback_data=f"bond:{iid}")],
            ]
        )
        await callback_query.message.edit_text(
            f"🔬 <b>Инструменты для профи</b> — {iid} ({name})\n\n"
            "Duration (дюрация) и оценка сделки РЕПО. Доступно в подписке Pro.",
            parse_mode=ParseMode.HTML,
            reply_markup=tools_kb,
        )
        await callback_query.answer()
        return

    if action == "analysis":
        bonds = await bonds_for_bot()
        bond = next((b for b in bonds if b.internal_id == iid), None)
        if bond is None:
            text = f"❌ Облигация <code>{iid}</code> не найдена."
        else:
            async with session_scope() as session:
                orm = await get_score(session, iid)
            score = (
                score_from_orm(orm)
                if orm is not None
                else score_bond(
                    internal_id=iid,
                    yield_to_maturity=bond.yield_to_maturity,
                    currency=bond.currency,
                    maturity_date=bond.maturity_date,
                    status=bond.status,
                    issuer=bond.issuer,
                    price=bond.price,
                )
            )
            ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity else None
            explained = explain_score(score, currency=bond.currency, ytm_pct=ytm)
            uid = callback_query.from_user.id if callback_query.from_user else 0
            is_pro = meets_tier(await get_tier_by_telegram(uid), "pro")
            lines = [
                f"💡 <b>{iid}</b> — {bond.name}",
                f"Рейтинг: <b>{score.tier}</b> ({score.score:.0f} баллов)",
                f"Вердикт: <b>{explained.verdict}</b>",
                "",
                explained.summary,
            ]
            if is_pro:
                if explained.strengths:
                    lines.append("\n<b>Почему стоит:</b>")
                    lines += [f"  ✅ {s}" for s in explained.strengths]
                if explained.weaknesses:
                    lines.append("\n<b>На что обратить внимание:</b>")
                    lines += [f"  ⚠️ {w}" for w in explained.weaknesses]
            else:
                lines.append(
                    "\n🔒 Полный разбор «почему покупать или нет» — в подписке Pro.\n"
                    "Нажмите /subscribe, чтобы открыть."
                )
            lines.append(f"\n{DISCLAIMER_SHORT}")
            text = "\n".join(lines)
    elif action == "income":
        bonds = await bonds_for_bot()
        bond = next((b for b in bonds if b.internal_id == iid), None)
        if bond is None:
            text = f"❌ Облигация <code>{iid}</code> не найдена."
        else:
            amount = Decimal("1000")
            ann = annual_income(
                amount_invested=amount, coupon_rate=bond.coupon_rate, price=bond.price
            )
            flows = bond_cashflows(
                internal_id=iid,
                amount_invested=amount,
                coupon_rate=bond.coupon_rate,
                coupon_frequency=bond.coupon_frequency,
                maturity_date=bond.maturity_date,
                price=bond.price,
            )
            coupons = [f for f in flows if f.kind == "coupon"]
            yoc = round(float(ann / amount * 100), 2) if amount > 0 else 0.0
            cur = f" {bond.currency}" if bond.currency else ""
            lines = [
                f"💰 <b>Доход по {iid}</b> — {bond.name}",
                f"При вложении <b>1000{cur}</b>:",
                f"• Купонный доход: <b>~{ann}{cur}/год</b> ({yoc}% на вложенное)",
            ]
            if coupons:
                nxt = coupons[0]
                lines.append(f"• Ближайшая выплата: <b>{nxt.amount}{cur}</b> — {nxt.date}")
                lines.append("\n<b>Ближайшие купоны:</b>")
                lines += [f"  {f.date}: {f.amount}{cur}" for f in coupons[:4]]
            else:
                lines.append("• Купонов нет (дисконтная / бескупонная облигация)")
            text = "\n".join(lines)
    elif action == "predict":
        async with session_scope() as session:
            rows = await predictions_for_bond(session, iid, limit=1)
        if not rows:
            text = "🔄 Прогнозы обновляются — загляните чуть позже."
        else:
            p = rows[0]
            expl = "\n".join(f"  • {e}" for e in (p.explanation or []))
            text = (
                f"<b>📈 Прогноз {iid}</b> ({name})\n"
                f"Решение: <b>{p.decision}</b> (уверенность {float(p.confidence):.0%})\n"
                f"Прогноз доходности (YTM): "
                f"{float(p.predicted_ytm) if p.predicted_ytm is not None else '—'}\n"
                f"Прогноз доходности: "
                f"{float(p.predicted_return_pct) if p.predicted_return_pct is not None else '—'}\n"
                f"Объяснение:\n{expl or '—'}\n\n{DISCLAIMER_SHORT}"
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
                f"Дюрация Маколея: <b>{rep.macaulay_duration:.2f}</b> (срок в годах)",
                f"Модифицированная дюрация: <b>{rep.modified_duration:.2f}</b> — чувствительность цены к ставке",
                f"Выпуклость: <b>{rep.convexity:.2f}</b>",
                f"DV01: <b>{rep.dv01:.4f}</b> — изменение цены при росте ставки на 0.01 п.п.",
                "<b>Дюрация по срокам:</b>",
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
                f"Залог: <b>{deal.collateral_value}</b>\n"
                f"Скидка к залогу (haircut): {deal.haircut_pct}%\n"
                f"Кэш выдано: <b>{deal.cash_lent}</b>\n"
                f"Ставка: {deal.repo_rate_pct}%, срок {deal.tenor_days} дн.\n"
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


# --------------------------------------------------------------------------- #
# Personal price / yield alerts (Pro) — set directly from the bond card.
# --------------------------------------------------------------------------- #
_Q = Decimal("0.01")


async def _show_alert_presets(callback_query, iid: str) -> None:
    """Offer one-tap alert thresholds computed from the bond's live quote."""
    bonds = await bonds_for_bot()
    bond = next((b for b in bonds if b.internal_id == iid), None)
    if bond is None:
        await callback_query.message.edit_text(
            f"❌ Облигация <code>{iid}</code> не найдена.", parse_mode=ParseMode.HTML
        )
        await callback_query.answer()
        return

    def _preset(emoji: str, metric: str, direction: str, value: Decimal, note: str) -> list[InlineKeyboardButton]:
        thr = value.quantize(_Q)
        label = alert_metric_label(metric)
        sign = alert_direction_sign(direction)
        return [
            InlineKeyboardButton(
                text=f"{emoji} {label} {sign} {fmt_num(thr)} ({note})",
                callback_data=f"alertset:{iid}:{metric}:{direction}:{thr}",
            )
        ]

    rows: list[list[InlineKeyboardButton]] = []
    if bond.price:
        rows.append(_preset("📉", "price", "below", bond.price * Decimal("0.95"), "−5%"))
        rows.append(_preset("📉", "price", "below", bond.price * Decimal("0.90"), "−10%"))
    if bond.yield_to_maturity:
        rows.append(_preset("📈", "ytm", "above", bond.yield_to_maturity + Decimal("1"), "+1 п.п."))
        rows.append(_preset("📈", "ytm", "above", bond.yield_to_maturity + Decimal("2"), "+2 п.п."))
    has_presets = bool(rows)
    rows.append([InlineKeyboardButton(text="🔔 Мои алерты", callback_data="cmd_alerts")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад к облигации", callback_data=f"bond:{iid}")])

    hint = (
        "Выберите порог — пришлём уведомление, когда он сработает."
        if has_presets
        else "Нет данных о цене/доходности для порогов."
    )
    await callback_query.message.edit_text(
        f"🔔 <b>Следить за {iid}</b> — {bond.name}\n\n{hint}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback_query.answer()


async def _apply_alert_rule(
    telegram_id: int, iid: str, metric: str, direction: str, threshold: Decimal
) -> str:
    """Create a personal alert rule for a Telegram user; return confirmation."""
    label = alert_metric_label(metric)
    sign = alert_direction_sign(direction)
    headline = f"{label} {iid} {sign} {fmt_num(threshold)}"

    async with session_scope() as session:
        user = await get_or_create_user_by_telegram(session, telegram_id)
        existing = await list_rules(session, user.id)
        already = any(
            r.internal_id == iid and r.metric == metric and r.direction == direction
            and r.threshold == threshold
            for r in existing
        )
        if already:
            return f"ℹ️ Такой алерт уже есть: <b>{headline}</b>."
        await create_rule(
            session,
            user_id=user.id,
            internal_id=iid,
            metric=metric,
            direction=direction,
            threshold=threshold,
            note="Telegram",
        )
    return (
        f"✅ Алерт создан: <b>{headline}</b>.\n"
        "Пришлём уведомление в Telegram, когда порог сработает."
    )


@router.callback_query(lambda c: c.data and c.data.startswith("alertset:"))
async def cb_alert_set(callback_query) -> None:
    uid = callback_query.from_user.id if callback_query.from_user else 0
    if not meets_tier(await get_tier_by_telegram(uid), "pro"):
        await callback_query.answer("Доступно в Pro — /subscribe", show_alert=True)
        return
    try:
        _, iid, metric, direction, thr = callback_query.data.split(":")
        threshold = Decimal(thr)
    except (ValueError, ArithmeticError):
        await callback_query.answer("Некорректный порог", show_alert=True)
        return
    text = await _apply_alert_rule(uid, iid, metric, direction, threshold)
    await callback_query.message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔔 Мои алерты", callback_data="cmd_alerts")],
                [InlineKeyboardButton(text="⬅️ Назад к облигации", callback_data=f"bond:{iid}")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
            ]
        ),
    )
    await callback_query.answer("Алерт создан")
