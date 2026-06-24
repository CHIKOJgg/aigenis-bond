"""Команды V2: score, monitor, send-alerts."""

from __future__ import annotations

import asyncio

from monitoring.engine import detect_bond_changes, detect_fx_changes, detect_metal_changes
from scoring.repository import recompute_all
from scraper.db import session_scope


async def cmd_score() -> int:
    async with session_scope() as session:
        n = await recompute_all(session)
    print(f"recomputed scores for {n} bonds")
    return 0


async def cmd_monitor() -> int:
    async with session_scope() as session:
        bond = await detect_bond_changes(session)
        fx = await detect_fx_changes(session)
        met = await detect_metal_changes(session)
    print({"bonds": bond.by_kind, "fx": fx.by_kind, "metals": met.by_kind})
    return 0


def main_score() -> int:
    return asyncio.run(cmd_score())


def main_monitor() -> int:
    return asyncio.run(cmd_monitor())
