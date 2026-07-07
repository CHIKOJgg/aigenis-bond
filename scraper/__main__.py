"""CLI entrypoint: run / once / backfill / health."""

from __future__ import annotations

import argparse
import asyncio
import sys

from scraper.client import AigenisClient
from scraper.commands import main_monitor, main_score
from scraper.commands_v3 import (
    cmd_ml_predict,
    cmd_ml_status,
    cmd_ml_train,
    cmd_rebalance_now,
    cmd_recs,
)
from scraper.commands_v4 import (
    cmd_desk_carry,
    cmd_desk_curve,
    cmd_desk_duration,
    cmd_desk_repo,
    cmd_desk_rv,
    cmd_desk_status,
    cmd_desk_stress,
)
from scraper.config import get_settings
from scraper.health import health as health_cmd
from scraper.logging import configure_logging, get_logger
from scraper.pipeline import backfill_history, run_once

logger = get_logger("scraper.cli")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aigenis-parser")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Запустить планировщик (cron jobs)")

    p_once = sub.add_parser("once", help="Однократный прогон сбора")
    p_once.add_argument(
        "--currency",
        type=str,
        default="",
        help="Список валют через запятую (пусто = все из настроек)",
    )

    p_back = sub.add_parser("backfill", help="Догрузка истории")
    p_back.add_argument("--days", type=int, default=None, help="Глубина в днях")
    p_back.add_argument(
        "--currency",
        type=str,
        default="",
        help="Список валют через запятую (пусто = все)",
    )

    sub.add_parser("score", help="Пересчитать Reward/Risk Score")
    sub.add_parser("monitor", help="Запустить мониторинг и сформировать алерты")

    sub.add_parser(
        "ml-train", help="Обучить ML-модели (регрессия YTM + классификатор buy/hold/wait/avoid)"
    )
    sub.add_parser("ml-predict", help="Сделать прогнозы по всем облигациям")
    sub.add_parser("ml-status", help="Показать текущие версии моделей и метрики")
    sub.add_parser("recs", help="Получить рекомендации к покупке")
    sub.add_parser("rebalance-now", help="Сформировать план ребалансировки (user_id=0)")

    sub.add_parser("desk-curve", help="Построить кривую доходности (Nelson-Siegel)")
    sub.add_parser("desk-rv", help="Relative Value: rich/cheap сигналы")
    p_dur = sub.add_parser("desk-duration", help="Duration-отчёт по облигации или портфелю")
    p_dur.add_argument("--bond", type=str, default="", help="internal_id (пусто = портфель)")
    p_car = sub.add_parser("desk-carry", help="Carry-ранжирование")
    p_car.add_argument("--funding", type=float, default=5.0, help="funding rate %%")
    p_rep = sub.add_parser("desk-repo", help="Сделка РЕПО")
    p_rep.add_argument("--bond", type=str, required=True)
    p_rep.add_argument("--notional", type=float, default=1000.0)
    p_rep.add_argument("--tenor", type=int, default=30, help="tenor_days")
    sub.add_parser("desk-stress", help="Стресс-тестирование (все пресеты)")
    sub.add_parser("desk-status", help="Сводка по desk-данным")

    sub.add_parser("health", help="Health-check")
    return parser


async def _cmd_once(currencies_csv: str) -> int:
    settings = get_settings()
    currencies = (
        [c.strip().upper() for c in currencies_csv.split(",") if c.strip()]
        if currencies_csv
        else settings.aigenis.currencies
    )
    async with AigenisClient(settings.aigenis) as client:
        summary = await run_once(client, currencies)
    print(summary)
    return 0


async def _cmd_backfill(currencies_csv: str, days: int | None) -> int:
    from scraper import repositories
    from scraper.db import session_scope

    settings = get_settings()

    async with session_scope() as session:
        if currencies_csv:
            currencies = [c.strip().upper() for c in currencies_csv.split(",") if c.strip()]
            existing: list[str] = []
            for cur in currencies:
                bonds = await repositories.bonds.get_by_currency(session, cur)
                existing.extend(b.internal_id for b in bonds)
        else:
            existing = list(await repositories.bonds.get_all_internal_ids(session))

    async with AigenisClient(settings.aigenis) as client:
        ok, err = await backfill_history(
            client,
            list(existing),
            days=days or settings.aigenis.history_backfill_days,
        )
    print({"history_rows": ok, "history_err": err})
    return 0


async def _cmd_run() -> int:
    from scraper.scheduler import run_forever

    await run_forever()
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "once":
        return asyncio.run(_cmd_once(args.currency))
    if args.command == "backfill":
        return asyncio.run(_cmd_backfill(args.currency, args.days))
    if args.command == "run":
        return asyncio.run(_cmd_run())
    if args.command == "health":
        return asyncio.run(health_cmd())
    if args.command == "score":
        return main_score()
    if args.command == "monitor":
        return main_monitor()
    if args.command == "ml-train":
        return asyncio.run(cmd_ml_train())
    if args.command == "ml-predict":
        return asyncio.run(cmd_ml_predict())
    if args.command == "ml-status":
        return asyncio.run(cmd_ml_status())
    if args.command == "recs":
        return asyncio.run(cmd_recs())
    if args.command == "rebalance-now":
        return asyncio.run(cmd_rebalance_now())
    if args.command == "desk-curve":
        return asyncio.run(cmd_desk_curve())
    if args.command == "desk-rv":
        return asyncio.run(cmd_desk_rv())
    if args.command == "desk-duration":
        return asyncio.run(cmd_desk_duration(args.bond or None))
    if args.command == "desk-carry":
        return asyncio.run(cmd_desk_carry(args.funding))
    if args.command == "desk-repo":
        return asyncio.run(cmd_desk_repo(args.bond, args.notional, args.tenor))
    if args.command == "desk-stress":
        return asyncio.run(cmd_desk_stress())
    if args.command == "desk-status":
        return asyncio.run(cmd_desk_status())
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
