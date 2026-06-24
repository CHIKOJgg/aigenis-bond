"""Health-check."""

from __future__ import annotations

import json
import sys

from scraper import repositories
from scraper.db import session_scope
from scraper.logging import get_logger

logger = get_logger("scraper.health")


async def health() -> int:
    async with session_scope() as session:
        bonds_total = await repositories.bonds.count_bonds(session)
        history_total = await repositories.history.count_history(session)
        last_fetched = await repositories.bonds.latest_fetched_at(session)

    report = {
        "status": "ok" if bonds_total > 0 else "empty",
        "bonds_total": bonds_total,
        "history_total": history_total,
        "last_fetched_at": last_fetched.isoformat() if last_fetched else None,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ok" else 1


def main() -> None:
    code = asyncio_run(health())
    sys.exit(code)


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


if __name__ == "__main__":
    main()
