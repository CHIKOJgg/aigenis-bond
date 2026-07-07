from __future__ import annotations

import time
import uuid
from collections import defaultdict

from aiogram.dispatcher.middlewares.base import BaseMiddleware


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
