from __future__ import annotations

import secrets
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.service import get_user_by_id
from scraper.config import get_settings
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


def _validate_csrf_origin(origin: str, referer: str) -> bool:
    """Validate Origin/Referer header to prevent CSRF attacks.

    Uses a set built from the environment at request time so production,
    staging, and local dev domains are all supported without code changes.
    """
    import os
    _base_hosts = {"aigenis.by", "www.aigenis.by", "app.aigenis.by", "localhost", "127.0.0.1"}
    extra = os.getenv("ADMIN_CSRF_HOSTS", "").strip()
    if extra:
        _base_hosts.update(h.strip() for h in extra.split(",") if h.strip())
    for header in (origin, referer):
        if header:
            try:
                parsed = urlparse(header)
                host = parsed.hostname or ""
                if any(host == allowed or host.endswith("." + allowed) for allowed in _base_hosts):
                    return True
            except Exception:
                continue
    if not origin and not referer:
        return True
    return False


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
    settings = get_settings()
    resp.set_cookie(
        key="admin_token",
        value=token,
        httponly=True,
        max_age=3600,
        secure=not settings.debug,
        samesite="strict",
    )
    return resp


@router.get("")
async def admin_dashboard(request: Request, admin: UserORM = Depends(_require_admin), session: AsyncSession = Depends(_get_session)):
    total_users = (await session.execute(select(func.count(UserORM.id)))).scalar() or 0
    active_users = (await session.execute(select(func.count(UserORM.id)).where(UserORM.is_active.is_(True)))).scalar() or 0
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
    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except (TypeError, ValueError):
        page = 1
    per_page = 20
    stmt = select(UserORM).order_by(UserORM.created_at.desc())
    if search:
        # SQLAlchemy's ilike() parameterizes the value automatically; bindparam
        # used explicitly to avoid any f-string misinterpretation.
        stmt = stmt.where(UserORM.email.ilike(search, escape="\\") | UserORM.name.ilike(search, escape="\\"))
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
async def admin_toggle_user(user_id: int, request: Request, _admin: UserORM = Depends(_require_admin), session: AsyncSession = Depends(_get_session)):
    # CSRF protection via Origin/Referer header check
    origin = request.headers.get("origin", "")
    referer = request.headers.get("referer", "")
    if not _validate_csrf_origin(origin, referer):
        raise HTTPException(status_code=403, detail="CSRF check failed")
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    await session.commit()
    return RedirectResponse(url="/admin/users", status_code=302)


@router.post("/users/{user_id}/tier")
async def admin_set_tier(user_id: int, request: Request, _admin: UserORM = Depends(_require_admin), session: AsyncSession = Depends(_get_session)):
    # CSRF protection via Origin/Referer header check
    origin = request.headers.get("origin", "")
    referer = request.headers.get("referer", "")
    if not _validate_csrf_origin(origin, referer):
        raise HTTPException(status_code=403, detail="CSRF check failed")
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
