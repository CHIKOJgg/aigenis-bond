from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.models import Bond
from scraper.orm import BondORM

# Маппинг internal_id → читаемое имя облигации.
# Заполняется из XLSX-данных при enrich_from_xlsx(), плюс хардкоженные
# известные сопоставления на случай, если XLSX недоступен.
BOND_NAME_MAP: dict[str, str] = {
    "OP-30": "iGenis OP30",
    "OP-43": "iGenis OP43",
    "OP-51": "iGenis OP51",
    "OP-17": "Айгенис Оп17",
    "OP-33": "Айгенис Оп33",
    "OP-35": "Айгенис Оп35",
}


def _is_technical_name(name: str) -> bool:
    """Проверяет, похоже ли имя на технический код (без человекочитаемых слов)."""
    if not name:
        return True
    # Только цифры, тире, слеши, подчёркивания
    cleaned = re.sub(r"[0-9\-_/]", "", name).strip()
    # Если после удаления тех.символов осталось < 2 букв — это тех.код
    return len(cleaned) < 2 or (cleaned.isupper() and len(cleaned) < 5)


def _enrich_bond_name(bond: Bond) -> str:
    """Построить читаемое имя облигации из доступных полей."""
    # 1. Если есть прямой маппинг по internal_id
    if bond.internal_id in BOND_NAME_MAP:
        return BOND_NAME_MAP[bond.internal_id]

    # 2. Если имя уже читаемое — оставляем
    if bond.name and not _is_technical_name(bond.name):
        return bond.name

    # 3. Если есть issuer — строим "Issuer #N"
    if bond.issuer and not _is_technical_name(bond.issuer):
        base = bond.issuer.strip()
        if _is_technical_name(base):
            return bond.internal_id
        # Убираем юр.форму для краткости
        base = re.sub(
            r"^\s*(ОАО|ЗАО|ООО|ОДО|ИП|СООО|УП|АО)\s+",
            "",
            base,
        ).strip()
        if bond.issue_number is not None:
            return f"{base} #{bond.issue_number}"
        return base

    # 4. Fallback — делаем internal_id более читаемым
    iid = bond.internal_id
    # MF-LB-USD-0265 → MF LB USD 0265
    iid = iid.replace("-", " ").replace("_", " ")
    # Если короткий номер — "iGenis #N"
    if re.fullmatch(r"\d+", iid):
        return f"Выпуск #{iid}"
    return iid


def _bond_to_orm(bond: Bond) -> dict:
    enriched_name = _enrich_bond_name(bond)
    return {
        "internal_id": bond.internal_id,
        "isin": bond.isin,
        "name": enriched_name,
        "issuer": bond.issuer,
        "issuer_logo": bond.issuer_logo,
        "currency": bond.currency,
        "nominal": bond.nominal,
        "coupon_rate": bond.coupon_rate,
        "coupon_frequency": bond.coupon_frequency,
        "maturity_date": bond.maturity_date,
        "price": bond.price,
        "yield_to_maturity": bond.yield_to_maturity,
        "amortization": bond.amortization,
        "offer_date": bond.offer_date,
        "start_date": bond.start_date,
        "end_date": bond.end_date,
        "registration_number": bond.registration_number,
        "issue_volume": bond.issue_volume,
        "issue_number": bond.issue_number,
        "income_method": bond.income_method,
        "in_stock": bond.in_stock,
        "guarantor": bond.guarantor,
        "maturity_term_text": bond.maturity_term_text,
        "coupon_description": bond.coupon_description,
        "coupon_schedule": bond.coupon_schedule,
        "indexation_currency": bond.indexation_currency,
        "exchange_rate_on_start": bond.exchange_rate_on_start,
        "term_days": bond.term_days,
        "quantity": bond.quantity,
        "status": bond.status,
        "raw": bond.raw,
        "fetched_at": bond.fetched_at,
    }


async def upsert_bond(session: AsyncSession, bond: Bond) -> None:
    values = _bond_to_orm(bond)
    stmt = pg_insert(BondORM).values(**values)
    update_cols = {c: stmt.excluded[c] for c in values if c not in {"internal_id"}}
    stmt = stmt.on_conflict_do_update(index_elements=[BondORM.internal_id], set_=update_cols)
    await session.execute(stmt)


async def upsert_bonds_batch(session: AsyncSession, bonds: Iterable[Bond]) -> int:
    rows = [_bond_to_orm(b) for b in bonds]
    if not rows:
        return 0
    stmt = pg_insert(BondORM).values(rows)
    update_cols = {c: stmt.excluded[c] for c in rows[0] if c not in {"internal_id"}}
    stmt = stmt.on_conflict_do_update(index_elements=[BondORM.internal_id], set_=update_cols)
    await session.execute(stmt)
    return len(rows)


async def update_bond_name(session: AsyncSession, internal_id: str, name: str) -> None:
    """Обновить поле name для облигации (используется при обогащении из XLSX)."""
    stmt = (
        pg_insert(BondORM)
        .values(internal_id=internal_id, name=name)
        .on_conflict_do_update(
            index_elements=[BondORM.internal_id],
            set_={"name": name},
        )
    )
    await session.execute(stmt)


def register_xlsx_names(xlsx_names: dict[str, str]) -> None:
    """Зарегистрировать человеческие имена из XLSX в общем маппинге."""
    BOND_NAME_MAP.update(xlsx_names)


async def get_all_internal_ids(session: AsyncSession) -> Sequence[str]:
    result = await session.execute(select(BondORM.internal_id))
    return result.scalars().all()


async def exists(session: AsyncSession, internal_id: str) -> bool:
    result = await session.execute(
        select(BondORM.internal_id).where(BondORM.internal_id == internal_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def get_by_currency(session: AsyncSession, currency: str) -> Sequence[BondORM]:
    result = await session.execute(
        select(BondORM)
        .where(BondORM.currency == currency)
        .order_by(BondORM.yield_to_maturity.desc())
    )
    return result.scalars().all()


async def count_bonds(session: AsyncSession) -> int:
    from sqlalchemy import func as sa_func

    result = await session.execute(select(sa_func.count(BondORM.internal_id)))
    return int(result.scalar_one())


async def latest_fetched_at(session: AsyncSession):
    from sqlalchemy import func as sa_func

    result = await session.execute(select(sa_func.max(BondORM.fetched_at)))
    return result.scalar_one_or_none()
