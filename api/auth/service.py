from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.logging import get_logger
from scraper.orm import PartnerKeyORM, UserORM

logger = get_logger("api.auth")

_DEV_DEFAULT_SECRET = "dev-insecure-secret-do-not-use-in-production"


def _resolve_jwt_secret() -> str:
    """Resolve the JWT signing secret.

    In production a real secret *must* be provided via ``JWT_SECRET_KEY`` — an
    empty/placeholder secret makes every token forgeable, so we refuse to start.
    In development/test the app falls back to an insecure default so local runs
    and the test-suite still work without configuration.
    """
    secret = (os.getenv("JWT_SECRET_KEY") or "").strip()
    if secret:
        return secret
    env = (os.getenv("AIGENIS_ENVIRONMENT") or "development").lower()
    if env in ("production", "prod"):
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Generate one (e.g. `python scripts/generate_secrets.py "
            "--write-env`) and set it before running in production — a missing secret makes auth forgeable."
        )
    return _DEV_DEFAULT_SECRET


def is_jwt_secret_weak() -> bool:
    """True when the active secret is the insecure dev fallback / placeholder."""
    return SECRET_KEY in ("", "change-me-in-production", _DEV_DEFAULT_SECRET)


SECRET_KEY = _resolve_jwt_secret()
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expire, "type": "access"}, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire, "type": "refresh"}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "7"))


async def register_user(
    session: AsyncSession,
    email: str,
    password: str,
    name: str,
    referral_code: str | None = None,
) -> tuple[UserORM, str | None]:
    result = await session.execute(select(UserORM).where(UserORM.email == email))
    if result.scalar_one_or_none():
        return None, "Email already registered"
    user = UserORM(
        email=email,
        password_hash=hash_password(password),
        name=name,
        trial_end=datetime.now(UTC) + timedelta(days=TRIAL_DAYS),
    )
    if referral_code:
        referrer = await _resolve_referrer(session, referral_code)
        if referrer is not None and referrer.id != user.id:
            user.referred_by = referrer.id
            # Reward the referrer with bonus trial days (no-op if expired/paid window logic below).
            await _grant_referral_bonus(session, referrer)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    # Send welcome + verification emails if SMTP is configured (non-blocking).
    try:
        from api.notifications.email import send_verification_email, send_welcome_email

        send_welcome_email(email, name)
        verify_token = create_access_token(user.id)
        send_verification_email(email, verify_token)
    except Exception as exc:
        logger.warning("welcome_email_failed", email=email, error=str(exc))
    return user, None


async def _resolve_referrer(session: AsyncSession, referral_code: str) -> UserORM | None:
    """Resolve a referrer from a user id, telegram id, or partner referral code."""
    code = referral_code.strip()
    if not code:
        return None
    # Try user id / telegram id (numeric) first.
    if code.isdigit():
        uid = int(code)
        user = (
            await session.execute(select(UserORM).where(UserORM.id == uid))
        ).scalar_one_or_none()
        if user:
            return user
        user = (
            await session.execute(select(UserORM).where(UserORM.telegram_id == uid))
        ).scalar_one_or_none()
        if user:
            return user
    # Try partner referral code.
    partner = (
        await session.execute(
            select(PartnerKeyORM).where(PartnerKeyORM.referral_code == code, PartnerKeyORM.active.is_(True))
        )
    ).scalar_one_or_none()
    if partner and partner.owner_user_id:
        return (
            await session.execute(select(UserORM).where(UserORM.id == partner.owner_user_id))
        ).scalar_one_or_none()
    return None


async def _grant_referral_bonus(session: AsyncSession, referrer: UserORM) -> None:
    bonus_days = int(os.getenv("REFERRAL_BONUS_DAYS", "3"))
    if bonus_days <= 0:
        return
    now = datetime.now(UTC)
    # Extend trial if still in trial; otherwise extend paid window if present.
    base = referrer.trial_end
    if base is None or base <= now:
        base = referrer.subscription_expires_at
    if base is None or base <= now:
        base = now
    if referrer.trial_end and referrer.trial_end > now:
        referrer.trial_end = referrer.trial_end + timedelta(days=bonus_days)
    elif referrer.subscription_expires_at and referrer.subscription_expires_at > now:
        referrer.subscription_expires_at = referrer.subscription_expires_at + timedelta(days=bonus_days)
    else:
        referrer.trial_end = now + timedelta(days=bonus_days)


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
        trial_end=datetime.now(UTC) + timedelta(days=TRIAL_DAYS),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, True


async def get_user_by_id(session: AsyncSession, user_id: int) -> UserORM | None:
    result = await session.execute(select(UserORM).where(UserORM.id == user_id))
    return result.scalar_one_or_none()


async def create_password_reset_token(session: AsyncSession, email: str) -> str | None:
    """Generate a password reset token for the given email.
    Returns the token, or None if email not found."""
    result = await session.execute(select(UserORM).where(UserORM.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return None
    token = create_access_token(user.id)
    # Store a hash of the token so it can only be used once. bcrypt refuses to
    # hash inputs longer than 72 bytes; JWTs can exceed that, so truncate.
    user.password_reset_token = hash_password(token[:72])
    await session.commit()
    return token


async def reset_password(session: AsyncSession, token: str, new_password: str) -> bool:
    """Reset password using a valid reset token.
    Returns True if successful, False if token is invalid/expired."""
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return False
    user_id = int(payload["sub"])
    result = await session.execute(select(UserORM).where(UserORM.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.password_reset_token:
        return False
    # bcrypt hashes at most the first 72 bytes, so compare against the same
    # truncated token that was stored.
    if not verify_password(token[:72], user.password_reset_token):
        return False
    user.password_hash = hash_password(new_password)
    user.password_reset_token = None
    await session.commit()
    return True
