#!/usr/bin/env python3
"""Seed the ``companies`` table from existing bonds.

For every distinct ``issuer`` in ``bonds`` we upsert a ``CompanyORM`` row with a
heuristic sector (banks / government / oil & gas / etc. derived from the issuer
name) and an empty description. Manual overrides (sector, description,
why_important, website, logo_url) can be supplied via
``scripts/companies_overrides.json``:

    {
      "ОАО 'Белагропромбанк'": {
        "sector": "Банки",
        "description": "Один из крупнейших банков Беларуси...",
        "why_important": "Системно значимый банк, крупный заёмщик на рынке облигаций.",
        "website": "https://example.com"
      }
    }

Usage:
    python scripts/seed_companies.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from scraper.db import session_scope
from scraper.orm import BondORM, CompanyORM

OVERRIDES_PATH = Path(__file__).resolve().parent / "companies_overrides.json"

_SECTOR_RULES: list[tuple[str, str]] = [
    ("банк", "Банки"),
    ("банка", "Банки"),
    ("bank", "Банки"),
    ("гос", "Государство"),
    ("министер", "Государство"),
    ("облисполком", "Государство"),
    ("нефт", "Нефть и газ"),
    ("газ", "Нефть и газ"),
    ("энерг", "Энергетика"),
    ("электр", "Энергетика"),
    ("телеком", "Связь"),
    ("связ", "Связь"),
    ("агро", "Сельское хозяйство"),
    ("молок", "Пищевая промышленность"),
    ("пищ", "Пищевая промышленность"),
    ("строит", "Строительство"),
    ("застрой", "Строительство"),
    ("машин", "Машиностроение"),
    ("хим", "Химия"),
    ("фарм", "Фармацевтика"),
    ("торг", "Ритейл"),
    ("маркет", "Ритейл"),
    ("логист", "Транспорт и логистика"),
    ("авто", "Транспорт и логистика"),
    ("железн", "Транспорт и логистика"),
]


def infer_sector(issuer: str) -> str | None:
    low = (issuer or "").lower()
    for keyword, sector in _SECTOR_RULES:
        if keyword in low:
            return sector
    return None


def load_overrides() -> dict[str, dict]:
    if OVERRIDES_PATH.exists():
        try:
            return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[warn] не удалось прочитать {OVERRIDES_PATH}")
    return {}


async def seed(overrides: dict[str, dict], verbose: bool = False) -> int:
    async with session_scope() as session:
        rows = (await session.execute(select(BondORM.issuer))).scalars().all()
        issuers = sorted({i for i in rows if i})

        existing = (
            await session.execute(select(CompanyORM))
        ).scalars().all()
        by_issuer = {c.issuer: c for c in existing}

        created = 0
        updated = 0
        for issuer in issuers:
            ov = overrides.get(issuer, {})
            sector = ov.get("sector") or infer_sector(issuer)
            comp = by_issuer.get(issuer)
            if comp is None:
                comp = CompanyORM(issuer=issuer)
                session.add(comp)
                created += 1
            else:
                updated += 1

            comp.name = ov.get("name") or issuer
            # не перезаписываем вручную заданные поля пустыми значениями
            if ov.get("sector"):
                comp.sector = ov["sector"]
            elif comp.sector is None:
                comp.sector = sector
            if ov.get("description"):
                comp.description = ov["description"]
            if ov.get("why_important"):
                comp.why_important = ov["why_important"]
            if ov.get("website"):
                comp.website = ov["website"]
            if ov.get("logo_url"):
                comp.logo_url = ov["logo_url"]

            if verbose:
                print(f"  {issuer} -> sector={comp.sector}")

        await session.commit()
        print(f"[ok] companies: создано {created}, обновлено {updated}")
        return created + updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed companies table")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    import asyncio

    overrides = load_overrides()
    if overrides:
        print(f"[info] загружено {len(overrides)} ручных переопределений")
    asyncio.run(seed(overrides, verbose=args.verbose))


if __name__ == "__main__":
    main()
