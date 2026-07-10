from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from scraper import repositories
from scraper.db import session_scope
from scraper.models import Bond
from scraper.orm import BondHistoryORM, BondORM

_PAGE_SIZE = 10


def paginate_kb(prefix: str, page: int, total: int) -> InlineKeyboardMarkup | None:
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"page:{prefix}:{page - 1}"))
    if page < total - 1:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"page:{prefix}:{page + 1}"))
    if not buttons:
        return None
    # Always let the user jump back to the main menu from a paginated list.
    home = [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")]
    return InlineKeyboardMarkup(inline_keyboard=[buttons, home])


async def fetch_bonds_by_currency(currency: str) -> list:
    async with session_scope() as session:
        return list(await repositories.bonds.get_by_currency(session, currency))


async def fetch_all_bonds(limit: int = 500):
    async with session_scope() as session:
        res = await session.execute(select(BondORM).limit(limit))
        return list(res.scalars().all())


async def bonds_for_bot():
    async with session_scope() as session:
        res = await session.execute(select(BondORM))
        orm_bonds = list(res.scalars().all())
        return [
            Bond(
                internal_id=b.internal_id,
                name=b.name,
                currency=b.currency,
                yield_to_maturity=b.yield_to_maturity,
                coupon_rate=b.coupon_rate,
                coupon_frequency=b.coupon_frequency,
                maturity_date=b.maturity_date,
                price=b.price,
                issuer=b.issuer,
                status=b.status,
                nominal=b.nominal,
                fetched_at=b.fetched_at,
            )
            for b in orm_bonds
        ]


async def fetch_bonds_with_history() -> tuple[list[dict], dict[str, list[dict]]]:
    async with session_scope() as session:
        bonds_q = await session.execute(select(BondORM))
        history_q = await session.execute(select(BondHistoryORM))
        bonds = list(bonds_q.scalars().all())
        history = list(history_q.scalars().all())
    history_by: dict[str, list[dict]] = {}
    for h in history:
        history_by.setdefault(h.internal_id, []).append(
            {"date": h.date, "price": h.price, "yield": h.yield_, "coupon": h.coupon}
        )
    return (
        [
            {
                "internal_id": b.internal_id,
                "name": b.name,
                "currency": b.currency,
                "yield_to_maturity": b.yield_to_maturity,
                "coupon_rate": b.coupon_rate,
                "maturity_date": b.maturity_date,
                "price": b.price,
                "status": b.status,
                "issuer": b.issuer,
            }
            for b in bonds
        ],
        history_by,
    )


def user_id_from_message(message) -> int:
    return message.from_user.id if message.from_user else 0


def parse_bond_args(message) -> str:
    args = (message.text or "").split(maxsplit=1)
    return args[1].strip() if len(args) > 1 else ""


def parse_funding_rate(message, default: float = 5.0) -> float:
    args = (message.text or "").split()
    if len(args) > 1:
        try:
            return float(args[1])
        except ValueError:
            return default
    return default
