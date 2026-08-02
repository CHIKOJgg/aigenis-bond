from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.service import decode_token
from scraper.db import session_scope

_bearer = HTTPBearer(auto_error=False)


async def _get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> int:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    try:
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=401, detail="Invalid token: missing subject")
        return int(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token: malformed subject") from exc


async def _get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session
