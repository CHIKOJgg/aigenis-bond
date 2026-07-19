from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.deps import _get_current_user
from api.auth.schemas import (
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from api.auth.service import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    find_or_create_google_user,
    get_user_by_id,
    login_user,
    register_user,
    reset_password,
)
from scraper.config import get_settings
from scraper.db import session_scope
from scraper.logging import get_logger

logger = get_logger("api.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


async def _get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, session: AsyncSession = Depends(_get_session)):
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    user, error = await register_user(session, req.email.lower().strip(), req.password, req.name.strip())
    if error:
        raise HTTPException(status_code=409, detail=error)
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, session: AsyncSession = Depends(_get_session)):
    user, error = await login_user(session, req.email.lower().strip(), req.password)
    if error:
        raise HTTPException(status_code=401, detail=error)
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, session: AsyncSession = Depends(_get_session)):
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = int(payload["sub"])
    user = await get_user_by_id(session, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/google", response_model=TokenResponse)
async def google_auth(req: GoogleAuthRequest, session: AsyncSession = Depends(_get_session)):
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={req.id_token}")
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google token")
        data = resp.json()
        google_client_id = get_settings().aigenis.google_client_id
        if not google_client_id:
            raise HTTPException(status_code=500, detail="Google login is not configured")
        aud = data.get("aud")
        azp = data.get("azp")
        if aud != google_client_id and azp != google_client_id:
            raise HTTPException(status_code=401, detail="Invalid Google token audience")
        if not data.get("email_verified", False):
            raise HTTPException(status_code=401, detail="Google email is not verified")
        google_id = data["sub"]
        email = data["email"]
        name = req.name or data.get("name", email.split("@")[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Google auth failed: {e}") from e
    user, _ = await find_or_create_google_user(session, google_id, email, name)
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, session: AsyncSession = Depends(_get_session)):
    token = await create_password_reset_token(session, req.email.lower().strip())
    if token:
        from api.notifications.email import send_password_reset_email
        try:
            send_password_reset_email(req.email, token)
        except Exception as exc:
            logger.error("password_reset_email_failed", error=str(exc))
    # Always return success to prevent email enumeration
    return {"message": "If the email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password_endpoint(req: ResetPasswordRequest, session: AsyncSession = Depends(_get_session)):
    success = await reset_password(session, req.token, req.new_password)
    if not success:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    return {"message": "Password has been reset successfully."}


@router.post("/verify-email")
async def verify_email(token: str, session: AsyncSession = Depends(_get_session)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    user_id = int(payload["sub"])
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_verified = True
    await session.commit()
    return {"message": "Email verified successfully."}


@router.get("/me", response_model=UserResponse)
async def get_me(user_id: int = Depends(_get_current_user), session: AsyncSession = Depends(_get_session)):
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    from telegram_bot.subscriptions import effective_tier
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        subscription_tier=effective_tier(user.subscription_tier, user.subscription_expires_at, user.trial_end),
        trial_end=user.trial_end.isoformat() if user.trial_end else None,
        is_active=user.is_active,
        is_verified=user.is_verified,
    )
