"""Репозиторий пользовательских настроек."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from scoring.models import UserPreferences
from scraper.orm import UserPreferencesORM


def _to_orm(prefs: UserPreferences) -> dict:
    return {
        "user_id": prefs.user_id,
        "initial_capital": prefs.initial_capital,
        "monthly_contribution": prefs.monthly_contribution,
        "usd_byn_forecast": prefs.usd_byn_forecast,
        "share_usd": Decimal(str(prefs.share_usd)),
        "share_byn": Decimal(str(prefs.share_byn)),
        "share_metals": Decimal(str(prefs.share_metals)),
        "share_eur": Decimal(str(prefs.share_eur)),
        "strategy": prefs.strategy,
        "watchlist": prefs.watchlist,
    }


def _from_orm(orm: UserPreferencesORM) -> UserPreferences:
    return UserPreferences(
        user_id=orm.user_id,
        initial_capital=orm.initial_capital,
        monthly_contribution=orm.monthly_contribution,
        usd_byn_forecast=orm.usd_byn_forecast,
        share_usd=float(orm.share_usd),
        share_byn=float(orm.share_byn),
        share_metals=float(orm.share_metals),
        share_eur=float(orm.share_eur),
        strategy=orm.strategy,  # type: ignore[arg-type]
        watchlist=list(orm.watchlist or []),
    )


async def upsert_preferences(session: AsyncSession, prefs: UserPreferences) -> None:
    values = _to_orm(prefs)
    stmt = pg_insert(UserPreferencesORM).values(**values)
    update_cols = {c: stmt.excluded[c] for c in values if c != "user_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=[UserPreferencesORM.user_id], set_=update_cols
    )
    await session.execute(stmt)


async def get_preferences(session: AsyncSession, user_id: int) -> UserPreferences:
    result = await session.execute(
        select(UserPreferencesORM).where(UserPreferencesORM.user_id == user_id)
    )
    orm = result.scalar_one_or_none()
    if orm is None:
        return UserPreferences(user_id=user_id)
    return _from_orm(orm)


async def add_to_watchlist(session: AsyncSession, user_id: int, internal_id: str) -> UserPreferences:
    prefs = await get_preferences(session, user_id)
    if internal_id not in prefs.watchlist:
        prefs.watchlist.append(internal_id)
        await upsert_preferences(session, prefs)
    return prefs


async def remove_from_watchlist(
    session: AsyncSession, user_id: int, internal_id: str
) -> UserPreferences:
    prefs = await get_preferences(session, user_id)
    if internal_id in prefs.watchlist:
        prefs.watchlist = [w for w in prefs.watchlist if w != internal_id]
        await upsert_preferences(session, prefs)
    return prefs
