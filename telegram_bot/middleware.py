from __future__ import annotations

import time
import uuid
from collections import defaultdict

from aiogram.dispatcher.middlewares.base import BaseMiddleware

from scraper import repositories
from scraper.db import session_scope

# Команды, доступные всегда (до и после парсинга)
ALLOWED_BEFORE_PARSE = {"start", "help", "parse", "rates"}


async def db_has_bonds() -> bool:
    """True, если в БД есть хотя бы одна облигация (признак завершённого парсинга)."""
    async with session_scope() as session:
        count = await repositories.bonds.count_bonds(session)
    return count > 0


def locked_message_text() -> str:
    return (
        "🔒 База облигаций пуста.\n"
        "Сначала запустите парсинг командой /parse (или кнопкой 🚀 Старт парсинга), "
        "после этого станут доступны остальные команды."
    )


class ParseLockMiddleware(BaseMiddleware):
    """Блокирует все команды, кроме разрешённых, пока облигации не загружены в БД.

    Проверка опирается на БД (наличие облигаций), а не на in-memory состояние,
    поэтому корректно работает после перезапуска процесса и между сервисами.
    """

    async def __call__(self, handler, event, data):
        message = event
        text = getattr(message, "text", None)
        if not text or not text.startswith("/"):
            return await handler(event, data)

        cmd = text.split(maxsplit=1)[0].lstrip("/").lower().split("@")[0]
        if cmd in ALLOWED_BEFORE_PARSE:
            return await handler(event, data)

        if await db_has_bonds():
            return await handler(event, data)

        await message.answer(locked_message_text())
        return


class ThrottlingMiddleware(BaseMiddleware):
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
    async def __call__(self, handler, event, data):
        data["request_id"] = uuid.uuid4().hex[:8]
        return await handler(event, data)
