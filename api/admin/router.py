from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.deps import _get_current_user
from api.auth.service import get_user_by_id
from scraper.db import session_scope
from scraper.logging import get_logger
from scraper.orm import UserORM

logger = get_logger("api.admin")

router = APIRouter(prefix="/admin", tags=["admin"])

_templates_dir = Path(__file__).parent / "templates"
_templates = Jinja2Templates(directory=str(_templates_dir))


async def _get_session():
    async with session_scope() as session:
        yield session


async def _require_admin(request: Request, session: AsyncSession = Depends(_get_session)) -> UserORM:
    token = request.cookies.get("admin_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    user_id = _verify_admin_token(token)
    if not user_id:
        raise HTTPException(status_code=302, detail="Not authenticated", headers={"Location": "/admin/login"})
    user = await get_user_by_id(session, user_id)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


def _verify_admin_token(token: str) -> int | None:
    from api.auth.service import decode_token
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    return int(payload["sub"])


@router.get("/login")
async def admin_login_page(request: Request):
    return _templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def admin_login(request: Request, session: AsyncSession = Depends(_get_session)):
    form = await request.form()
    email = form.get("email", "")
    password = form.get("password", "")
    from api.auth.service import create_access_token, login_user
    user, error = await login_user(session, email, password)
    if error or not user:
        return _templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"}, status_code=401)
    if user.role != "admin":
        return _templates.TemplateResponse("login.html", {"request": request, "error": "Access denied"}, status_code=403)
    token = create_access_token(user.id)
    resp = RedirectResponse(url="/admin", status_code=302)
    resp.set_cookie(key="admin_token", value=token, httponly=True, max_age=3600)
    return resp


@router.get("")
async def admin_dashboard(request: Request, admin: UserORM = Depends(_require_admin), session: AsyncSession = Depends(_get_session)):
    total_users = (await session.execute(select(func.count(UserORM.id)))).scalar() or 0
    active_users = (await session.execute(select(func.count(UserORM.id)).where(UserORM.is_active == True))).scalar() or 0
    by_tier = await session.execute(
        select(UserORM.subscription_tier, func.count(UserORM.id)).group_by(UserORM.subscription_tier)
    )
    return _templates.TemplateResponse("dashboard.html", {
        "request": request,
        "admin": admin,
        "total_users": total_users,
        "active_users": active_users,
        "by_tier": dict(by_tier.fetchall()),
    })


@router.get("/users")
async def admin_users(request: Request, admin: UserORM = Depends(_require_admin), session: AsyncSession = Depends(_get_session)):
    search = request.query_params.get("search", "")
    page = int(request.query_params.get("page", "1"))
    per_page = 20
    stmt = select(UserORM).order_by(UserORM.created_at.desc())
    if search:
        stmt = stmt.where(UserORM.email.ilike(f"%{search}%") | UserORM.name.ilike(f"%{search}%"))
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    result = await session.execute(stmt)
    users = result.scalars().all()
    total = await session.execute(select(func.count(UserORM.id)))
    return _templates.TemplateResponse("users.html", {
        "request": request,
        "admin": admin,
        "users": users,
        "search": search,
        "page": page,
        "total_pages": max(1, (total.scalar() or 0) // per_page + 1),
    })


@router.post("/users/{user_id}/toggle")
async def admin_toggle_user(user_id: int, admin: UserORM = Depends(_require_admin), session: AsyncSession = Depends(_get_session)):
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    await session.commit()
    return RedirectResponse(url="/admin/users", status_code=302)


@router.post("/users/{user_id}/tier")
async def admin_set_tier(user_id: int, request: Request, admin: UserORM = Depends(_require_admin), session: AsyncSession = Depends(_get_session)):
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    form = await request.form()
    tier = form.get("tier", "free")
    if tier not in ("free", "pro", "enterprise"):
        raise HTTPException(status_code=400, detail="Invalid tier")
    user.subscription_tier = tier
    await session.commit()
    return RedirectResponse(url="/admin/users", status_code=302)
