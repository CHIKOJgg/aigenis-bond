from __future__ import annotations

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleAuthRequest(BaseModel):
    id_token: str
    name: str | None = None


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    subscription_tier: str
    is_active: bool
    is_verified: bool


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
