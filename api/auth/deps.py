from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.service import decode_token, get_user_by_id
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
    return int(payload["sub"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


async def get_current_user_db(
    user_id: int = Depends(_get_current_user),
    session: AsyncSession = Depends(_get_session),
) -> object:
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
