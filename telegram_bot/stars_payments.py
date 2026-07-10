"""Telegram Stars payments for bot subscriptions.

Flow: /subscribe -> choose tier -> bot sends an XTR invoice ->
pre_checkout_query (auto-accept) -> successful_payment -> tier granted.
Recurring subscriptions (subscription_period) re-fire successful_payment on
each renewal, so the tier is automatically re-granted.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    PreCheckoutQuery,
)
from loguru import logger

from telegram_bot.subscriptions import (
    STAR_PLANS,
    set_tier_by_telegram,
)

stars_router = Router()

_UNLOCKED_FEATURES = (
    "📊 Обзор рынка, TOP, курсы и базовая кривая доходности — бесплатно.\n"
    "⭐ Pro/Enterprise открывают: Relative Value, duration, carry, РЕПО, "
    "стресс-тесты, рекомендации, портфель, прогнозы ML и алерты."
)


def _subscribe_kb() -> InlineKeyboardMarkup:
    rows = []
    for plan in STAR_PLANS.values():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"⭐ {plan.name} — {plan.stars} Stars",
                    callback_data=f"stars:pay:{plan.tier}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="stars:close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@stars_router.message(F.text == "/subscribe")
async def cmd_subscribe(message) -> None:
    await _show_subscribe(message)


async def _show_subscribe(message) -> None:
    text = (
        "⭐ <b>Подписка через Telegram Stars</b>\n\n"
        f"{_UNLOCKED_FEATURES}\n\n"
        "Выберите тариф. Оплата списывается в Stars, подписка активируется "
        "сразу после оплаты (повторная оплата продлевает доступ)."
    )
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=_subscribe_kb())


@stars_router.callback_query(lambda c: c.data == "stars:menu")
async def cb_stars_menu(callback_query) -> None:
    await callback_query.answer()
    await _show_subscribe(callback_query.message)


@stars_router.callback_query(lambda c: c.data and c.data.startswith("stars:pay:"))
async def cb_stars_pay(callback_query) -> None:
    tier = callback_query.data.split(":", 2)[2]
    plan = STAR_PLANS.get(tier)
    if plan is None:
        await callback_query.answer("Неизвестный тариф", show_alert=True)
        return
    await callback_query.answer()
    try:
        await callback_query.bot.send_invoice(
            chat_id=callback_query.message.chat.id,
            title=f"Подписка {plan.name}",
            description=plan.blurb,
            payload=f"stars_sub:{plan.tier}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"Подписка {plan.name} (30 дней)", amount=plan.stars)],
            start_parameter="subscribe",
        )
    except Exception as exc:
        logger.exception("stars_invoice_failed", error=str(exc))
        await callback_query.message.answer(
            "❌ Не удалось создать счёт на оплату. Попробуйте позже."
        )


@stars_router.callback_query(lambda c: c.data == "stars:close")
async def cb_stars_close(callback_query) -> None:
    await callback_query.answer()
    await callback_query.message.delete()


@stars_router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    # For Stars (XTR) we accept all pre-checkout queries.
    await pre_checkout_query.answer(ok=True)


@stars_router.message(F.successful_payment)
async def on_successful_payment(message) -> None:
    payment = message.successful_payment
    payload = payment.invoice_payload or ""
    if not payload.startswith("stars_sub:"):
        return
    tier = payload.split(":", 1)[1]
    tg_id = message.from_user.id if message.from_user else 0
    await set_tier_by_telegram(tg_id, tier)
    plan = STAR_PLANS.get(tier)
    name = plan.name if plan else tier
    await message.answer(
        f"✅ Спасибо! Подписка <b>{name}</b> активна.\n"
        "Все Pro/Enterprise функции теперь доступны. Откройте меню: /menu",
        parse_mode=ParseMode.HTML,
    )
