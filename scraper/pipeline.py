from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from tqdm.asyncio import tqdm

from scoring.repository import recompute_all
from scraper import repositories
from scraper.api.detail import parse_detail_payload
from scraper.api.history import parse_history_payload
from scraper.api.listing import parse_listing_payload
from scraper.client import AigenisClient
from scraper.db import session_scope
from scraper.errors import (
    HistoryUnavailable,
    NotFoundError,
    ParseError,
    ScraperError,
    TransientError,
)
from scraper.logging import get_logger
from scraper.models import Bond, BondDailyAccrual
from scraper.orm import BondORM
from scraper.parsers.xlsx import XlsxParseResult, parse_all
from scraper.validation import validate_detail, validate_listing

logger = get_logger("scraper.pipeline")


async def collect_listing(client: AigenisClient, currencies: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    tasks = [client.fetch_listing(cur) for cur in currencies]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    internal_ids: list[str] = []
    for currency, res in zip(currencies, results, strict=True):
        if isinstance(res, BaseException):
            logger.error("listing_failed", currency=currency, error=str(res))
            continue
        try:
            items = validate_listing(parse_listing_payload(res, currency))
        except ScraperError as e:
            logger.error("listing_parse_failed", currency=currency, error=str(e))
            continue
        for it in items:
            iid = it["internal_id"]
            if iid not in seen:
                seen.add(iid)
                internal_ids.append(iid)
    logger.info("listing_done", total=len(internal_ids))
    return internal_ids


async def collect_details(
    client: AigenisClient,
    internal_ids: list[str],
    *,
    batch_size: int = 50,
) -> tuple[int, int]:
    ok, err = 0, 0
    sem = asyncio.Semaphore(client.settings.max_concurrency)

    async def _one(iid: str) -> tuple[str, str]:
        async with sem:
            try:
                payload = await client.fetch_detail(iid)
                payload = validate_detail(payload)
                bond = parse_detail_payload(payload, iid)
                async with session_scope() as session:
                    await repositories.bonds.upsert_bond(session, bond)
                return iid, "ok"
            except NotFoundError:
                async with session_scope() as session:
                    await repositories.bonds.upsert_bond(
                        session,
                        _delisted_placeholder(iid),
                    )
                return iid, "delisted"
            except (TransientError, ParseError) as e:
                logger.warning("detail_failed", internal_id=iid, error=str(e))
                return iid, "error"
            except Exception:
                logger.exception("detail_unexpected", internal_id=iid)
                return iid, "error"

    async def _runner() -> None:
        nonlocal ok, err
        for i in range(0, len(internal_ids), batch_size):
            chunk = internal_ids[i : i + batch_size]
            results = await tqdm.gather(
                *[_one(iid) for iid in chunk],
                desc=f"details {i}-{i + len(chunk)}",
                total=len(chunk),
            )
            for _, status in results:
                if status in {"ok", "delisted"}:
                    ok += 1
                else:
                    err += 1

    await _runner()
    return ok, err


def _delisted_placeholder(internal_id: str, currency: str = "unknown") -> Bond:
    return Bond(
        internal_id=internal_id,
        name=internal_id,
        currency=currency,
        status="delisted",
        fetched_at=datetime.now(UTC),
    )


async def backfill_history(
    client: AigenisClient,
    internal_ids: list[str],
    *,
    days: int,
    end_date: date | None = None,
) -> tuple[int, int]:
    today = end_date or date.today()
    since_default = today - timedelta(days=days)
    ok, err = 0, 0
    sem = asyncio.Semaphore(client.settings.max_concurrency)

    async def _one(iid: str) -> None:
        nonlocal ok, err
        async with sem:
            async with session_scope() as session:
                last = await repositories.history.last_history_date(session, iid)
            since = (last + timedelta(days=1)) if last else since_default
            if since > today:
                return
            try:
                payload = await client.fetch_history(iid, since, today)
            except HistoryUnavailable:
                return
            except NotFoundError:
                return
            except (TransientError, ParseError) as e:
                logger.warning("history_failed", internal_id=iid, error=str(e))
                err += 1
                return
            except Exception:
                logger.exception("history_unexpected", internal_id=iid)
                err += 1
                return
            rows = parse_history_payload(payload, iid)
            if not rows:
                return
            async with session_scope() as session:
                n = await repositories.history.upsert_history_batch(session, rows)
            ok += n

    await asyncio.gather(*[_one(iid) for iid in internal_ids])
    return ok, err


async def enrich_from_xlsx(xlsx_data: XlsxParseResult | None = None) -> dict[str, int]:
    if xlsx_data is None:
        try:
            xlsx_data = parse_all()
        except Exception as e:
            logger.warning("xlsx_download_failed", error=str(e))
            return {"xlsx_bonds_enriched": 0, "xlsx_accruals_written": 0}

    enriched = 0
    async with session_scope() as session:
        from sqlalchemy import select as sa_select

        result = await session.execute(sa_select(BondORM))
        all_bonds = result.scalars().all()

        for bond_orm in all_bonds:
            issue_num = bond_orm.issue_number
            if issue_num is None:
                continue
            enrichment = xlsx_data.byn_bonds.get(issue_num)
            if enrichment is None:
                continue

            updates = {}
            if bond_orm.nominal is None and enrichment.face_value is not None:
                updates["nominal"] = enrichment.face_value
            if bond_orm.quantity is None and enrichment.quantity is not None:
                updates["quantity"] = enrichment.quantity
            if bond_orm.issue_volume is None and enrichment.issue_volume is not None:
                updates["issue_volume"] = enrichment.issue_volume
            if bond_orm.coupon_rate is None and enrichment.coupon_rate is not None:
                updates["coupon_rate"] = enrichment.coupon_rate
            if bond_orm.start_date is None and enrichment.start_date is not None:
                updates["start_date"] = enrichment.start_date
            if bond_orm.end_date is None and enrichment.maturity_date is not None:
                updates["end_date"] = enrichment.maturity_date
            if bond_orm.term_days is None and enrichment.term_days is not None:
                updates["term_days"] = enrichment.term_days
            if enrichment.indexation_currency:
                updates["indexation_currency"] = enrichment.indexation_currency

            if enrichment.coupon_periods and not bond_orm.coupon_schedule:
                schedule: dict[str, list[str]] = {}
                for p in enrichment.coupon_periods:
                    year = p["start"][:4] if isinstance(p["start"], str) else ""
                    if year:
                        schedule.setdefault(year, []).append(p["start"])
                if schedule:
                    updates["coupon_schedule"] = schedule

            if updates:
                for key, val in updates.items():
                    setattr(bond_orm, key, val)
                enriched += 1

            if enrichment.name and enrichment.name != bond_orm.name:
                readable = enrichment.name.strip()
                if readable.endswith(".xlsx"):
                    readable = readable.rsplit(".", 1)[0]
                from scraper.repositories.bonds import register_xlsx_names, update_bond_name

                register_xlsx_names({bond_orm.internal_id: readable})
                await update_bond_name(session, bond_orm.internal_id, readable)

        # Apply indexed bond names from XLSX
        for iid, enrichment in (xlsx_data.indexed_bonds or {}).items():
            if enrichment.name:
                from scraper.repositories.bonds import register_xlsx_names, update_bond_name

                # Find bond by internal_id like "Оп17" or issue_number
                for bond_orm in all_bonds:
                    if bond_orm.internal_id.lower().replace("-", "").replace(" ", "") == iid.lower():
                        readable = enrichment.name.strip()
                        register_xlsx_names({bond_orm.internal_id: readable})
                        await update_bond_name(session, bond_orm.internal_id, readable)
                        break

        await session.flush()

        accruals_written = 0
        if xlsx_data.daily_accruals:
            issue_to_iid: dict[int, str] = {}
            for bond_orm in all_bonds:
                if bond_orm.issue_number is not None:
                    issue_to_iid[bond_orm.issue_number] = bond_orm.internal_id

            remapped: list[BondDailyAccrual] = []
            for acc in xlsx_data.daily_accruals:
                try:
                    issue_num = int(acc.internal_id)
                except (ValueError, TypeError):
                    continue
                real_iid = issue_to_iid.get(issue_num)
                if real_iid is None:
                    continue
                remapped.append(
                    BondDailyAccrual(
                        internal_id=real_iid,
                        date=acc.date,
                        accrued=acc.accrued,
                        total_value=acc.total_value,
                    )
                )

            if remapped:
                accruals_written = await repositories.history.upsert_accruals_batch(
                    session, remapped
                )

        await session.commit()

    return {"xlsx_bonds_enriched": enriched, "xlsx_accruals_written": accruals_written}


async def run_once(client: AigenisClient, currencies: Iterable[str]) -> dict[str, int]:
    settings = client.settings
    cur_list = list(currencies)
    logger.info("pipeline_start", currencies=cur_list)

    internal_ids = await collect_listing(client, cur_list)
    details_ok, details_err = await collect_details(client, internal_ids)
    history_ok, history_err = await backfill_history(
        client,
        internal_ids,
        days=settings.history_backfill_days,
    )
    xlsx_stats = await enrich_from_xlsx()
    async with session_scope() as session:
        scored = await recompute_all(session)
    summary = {
        "listing_total": len(internal_ids),
        "details_ok": details_ok,
        "details_err": details_err,
        "history_rows": history_ok,
        "history_err": history_err,
        "scored": scored,
        **xlsx_stats,
    }
    logger.info("pipeline_done", **summary)
    return summary
