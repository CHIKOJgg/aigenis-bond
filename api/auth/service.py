from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.logging import get_logger
from scraper.orm import UserORM

logger = get_logger("api.auth")

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expire, "type": "access"}, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire, "type": "refresh"}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


async def register_user(session: AsyncSession, email: str, password: str, name: str) -> tuple[UserORM, str | None]:
    result = await session.execute(select(UserORM).where(UserORM.email == email))
    if result.scalar_one_or_none():
        return None, "Email already registered"
    user = UserORM(email=email, password_hash=hash_password(password), name=name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, None


async def login_user(session: AsyncSession, email: str, password: str) -> tuple[UserORM | None, str | None]:
    result = await session.execute(select(UserORM).where(UserORM.email == email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash:
        return None, "Invalid email or password"
    if not verify_password(password, user.password_hash):
        return None, "Invalid email or password"
    if not user.is_active:
        return None, "Account is disabled"
    return user, None


async def find_or_create_google_user(session: AsyncSession, google_id: str, email: str, name: str) -> tuple[UserORM, bool]:
    result = await session.execute(select(UserORM).where(UserORM.google_id == google_id))
    user = result.scalar_one_or_none()
    if user:
        return user, False
    result = await session.execute(select(UserORM).where(UserORM.email == email))
    existing = result.scalar_one_or_none()
    if existing:
        existing.google_id = google_id
        if not existing.is_verified:
            existing.is_verified = True
        await session.commit()
        await session.refresh(existing)
        return existing, False
    user = UserORM(
        email=email,
        name=name,
        google_id=google_id,
        is_verified=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, True


async def get_user_by_id(session: AsyncSession, user_id: int) -> UserORM | None:
    result = await session.execute(select(UserORM).where(UserORM.id == user_id))
    return result.scalar_one_or_none()
