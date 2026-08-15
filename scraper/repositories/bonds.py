from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.db import upsert_row
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
        # pragma: no cover - provably unreachable: _is_technical_name only
        # strips whitespace and removes [0-9\-_/], so the result is identical
        # for `x` and `x.strip()` — the outer guard already excludes this case
        if _is_technical_name(base):  # pragma: no cover
            return bond.internal_id  # pragma: no cover
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
        # Первичный источник — белорусская площадка: рынок проставляется
        # явно, чтобы не зависеть от server_default="bcse".
        "market": bond.market or "bcse",
    }


async def upsert_bond(session: AsyncSession, bond: Bond, *, merge_missing: bool = True) -> None:
    """Upsert a bond, by default preserving DB values the fresh payload lacks.

    Detail payloads are often partial (a section failed to parse, or a
    field is absent in the feed, e.g. ``coupon_rate`` not disclosed for
    indexed bonds). Without merging, ``None`` fields would wipe previously
    known values on every run. Pass ``merge_missing=False`` for a full
    overwrite (used by sources that always send complete records).
    """
    values = _bond_to_orm(bond)
    if merge_missing:
        existing = (
            await session.execute(select(BondORM).where(BondORM.internal_id == bond.internal_id))
        ).scalar_one_or_none()
        if existing is not None:
            for key, val in values.items():
                if val is None:
                    values[key] = getattr(existing, key)
    await upsert_row(
        session,
        BondORM,
        index_elements=["internal_id"],
        values=values,
    )


async def upsert_bonds_batch(session: AsyncSession, bonds: Iterable[Bond]) -> int:
    rows = [_bond_to_orm(b) for b in bonds]
    if not rows:
        return 0
    for values in rows:
        await upsert_row(
            session,
            BondORM,
            index_elements=["internal_id"],
            values=values,
        )
    return len(rows)


async def update_bond_name(session: AsyncSession, internal_id: str, name: str) -> None:
    """Обновить поле name для облигации (используется при обогащении из XLSX).

    Update-only: никогда не создаёт строку частично. INSERT с одним полем
    нарушал NOT NULL на обязательных колонках (currency и др.), когда бонд
    ещё не был вставлен полным пайплайном (или шёл параллельный прогон).
    """
    await session.execute(
        update(BondORM).where(BondORM.internal_id == internal_id).values(name=name)
    )


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
