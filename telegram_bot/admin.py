"""Admin commands and the global error handler for the Telegram bot."""
from __future__ import annotations

import os

from aiogram import Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, ExceptionTypeFilter
from aiogram.types import ErrorEvent, Message
from loguru import logger
from sqlalchemy import select as sa_select

from scraper import repositories
from scraper.db import session_scope
from scraper.orm import UserPreferencesORM

router = Router()

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
        except Exception as exc:
            logger.warning("broadcast_failed", user_id=uid, error=str(exc))
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


@router.errors(ExceptionTypeFilter(Exception))
async def global_error_handler(event: ErrorEvent):
    logger.exception("bot_handler_error", error=str(event.exception))
    if event.update.message:
        await event.update.message.answer(
            "❌ Внутренняя ошибка. Попробуйте позже или напишите /help.",
        )
