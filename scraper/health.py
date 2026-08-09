"""Health-check."""

from __future__ import annotations

import json
import sys

from scraper import repositories
from scraper.db import session_scope
from scraper.logging import get_logger

logger = get_logger("scraper.health")


async def health() -> int:
    # Liveness check: exit 0 as long as the process is alive and the DB is
    # reachable. Data readiness ("empty" until the first successful scrape) is
    # reported in the JSON so a fresh deployment is not marked unhealthy for
    # up to ~6h before the first scheduled run.
    try:
        async with session_scope() as session:
            bonds_total = await repositories.bonds.count_bonds(session)
            history_total = await repositories.history.count_history(session)
            last_fetched = await repositories.bonds.latest_fetched_at(session)
    except Exception as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}, ensure_ascii=False))
        return 1

    report = {
        "status": "ok" if bonds_total > 0 else "empty",
        "bonds_total": bonds_total,
        "history_total": history_total,
        "last_fetched_at": last_fetched.isoformat() if last_fetched else None,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    code = asyncio_run(health())
    sys.exit(code)


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


if __name__ == "__main__":  # pragma: no cover - exercised via subprocess test
    main()
