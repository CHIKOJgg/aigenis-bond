from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=100)
    referral_code: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class GoogleAuthRequest(BaseModel):
    id_token: str
    name: str | None = None


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    subscription_tier: str
    trial_end: str | None = None
    is_active: bool
    is_verified: bool


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
