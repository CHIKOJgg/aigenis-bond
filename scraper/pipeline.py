from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from tqdm.asyncio import tqdm

from scoring.repository import recompute_all
from scraper import repositories
from scraper.db import session_scope
from scraper.errors import (
    HistoryUnavailable,
    NotFoundError,
    ParseError,
    ScraperError,
    TransientError,
)
from scraper.lineage import record_snapshot_lineage
from scraper.logging import get_logger
from scraper.models import Bond, BondDailyAccrual
from scraper.moex import MoexClient
from scraper.orm import BondORM
from scraper.validation import validate_detail, validate_listing

if TYPE_CHECKING:
    from scraper.sources.aigenis.client import AigenisClient

logger = get_logger("scraper.pipeline")


def _d(value: object) -> Decimal | None:
    """Coerce a fallback quote value to Decimal, tolerating strings/None."""
    from decimal import Decimal, InvalidOperation

    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


async def collect_listing(client: AigenisClient, currencies: Iterable[str]) -> list[str]:
    from scraper.api.listing import parse_listing_payload

    seen: set[str] = set()
    # Clear the internal_id→api_id map ONCE before launching the concurrent
    # listing tasks. ``_api_fetch_listing`` must NOT clear it itself (that would
    # race between currencies and drop each other's entries).
    client._id_by_internal.clear()
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
    from scraper.api.detail import parse_detail_payload

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
                        await _delisted_placeholder(iid),
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


async def _delisted_placeholder(iid: str) -> Bond:
    """Mark a bond as delisted, preserving its last known currency/name.

    A bare placeholder would wipe the currency to ``"unknown"``, which breaks
    currency filters (API, bot /usd /byn, widget) for delisted bonds.
    """
    known_currency: str | None = None
    known_name: str | None = None
    try:
        async with session_scope() as session:
            existing = (
                await session.execute(select(BondORM).where(BondORM.internal_id == iid))
            ).scalar_one_or_none()
            if existing:
                known_currency = existing.currency
                known_name = existing.name
    except Exception:
        logger.exception("delisted_lookup_failed", internal_id=iid)
    return Bond(
        internal_id=iid,
        name=known_name or iid,
        currency=known_currency or "USD",
        status="delisted",
        fetched_at=datetime.now(UTC),
    )


async def backfill_history(
    client,
    internal_ids: list[str],
    *,
    days: int,
    end_date: date | None = None,
) -> tuple[int, int]:
    from scraper.api.history import parse_history_payload

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


async def enrich_from_xlsx(xlsx_data=None) -> dict[str, int]:
    from scraper.parsers.xlsx import parse_all

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
                    if (
                        bond_orm.internal_id.lower().replace("-", "").replace(" ", "")
                        == iid.lower()
                    ):
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


async def run_once_moex(client: MoexClient, currencies: Iterable[str]) -> dict[str, int]:
    """MOEX-native pipeline path (no aigenis.by parsers involved).

    Fetches bonds directly as ``Bond`` models and upserts them, then backfills
    daily price/YTM history (via the MOEX ``history`` block) and the coupon
    calendar (via bondization) for the top-N bonds per currency.
    """
    if not isinstance(client, MoexClient):
        raise TypeError("run_once_moex requires a MoexClient")

    cur_list = list(currencies)
    # MOEX's home market is RUB corporates (the largest segment). The shared
    # currency config may omit RUB (it targets the paid aigenis.by source), so
    # always include it when running the MOEX pipeline.
    if "RUB" not in [c.upper() for c in cur_list]:
        logger.info("moex_adding_rub_home_market")
        cur_list = ["RUB", *cur_list]
    logger.info("moex_pipeline_start", currencies=cur_list)

    saved = 0
    async with session_scope() as session:
        for cur in cur_list:
            bonds = await client.fetch_bonds(cur)
            if not bonds:
                logger.info("moex_no_bonds", currency=cur)
                continue
            for b in bonds:
                existing = (
                    await session.execute(
                        select(BondORM).where(BondORM.internal_id == b.internal_id)
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        BondORM(
                            internal_id=b.internal_id,
                            name=b.name,
                            issuer=b.issuer,
                            currency=b.currency,
                            nominal=b.nominal,
                            coupon_rate=b.coupon_rate,
                            coupon_frequency=b.coupon_frequency,
                            maturity_date=b.maturity_date,
                            price=b.price,
                            yield_to_maturity=b.yield_to_maturity,
                            isin=b.isin,
                            status=b.status,
                            is_government=b.is_government,
                            fetched_at=datetime.now(UTC),
                        )
                    )
                else:
                    existing.name = b.name or existing.name
                    existing.issuer = b.issuer or existing.issuer
                    existing.currency = b.currency or existing.currency
                    existing.nominal = b.nominal or existing.nominal
                    existing.coupon_rate = (
                        b.coupon_rate if b.coupon_rate is not None else existing.coupon_rate
                    )
                    existing.coupon_frequency = b.coupon_frequency or existing.coupon_frequency
                    existing.maturity_date = b.maturity_date or existing.maturity_date
                    existing.price = b.price if b.price is not None else existing.price
                    existing.yield_to_maturity = b.yield_to_maturity
                    existing.isin = b.isin or existing.isin
                    existing.status = b.status or existing.status
                    existing.is_government = (
                        b.is_government if b.is_government else existing.is_government
                    )
                    existing.fetched_at = datetime.now(UTC)
                saved += 1
            await session.commit()

    # Score newly-fetched bonds.
    xlsx_stats = await enrich_from_xlsx()
    async with session_scope() as session:
        scored = await recompute_all(session)

    # History backfill (best-effort): daily close+YTM candles from MOEX for a
    # bounded sample so charts/accruals work without the paid source.
    history_rows = 0
    history_err = 0
    cap = int(os.getenv("MOEX_HISTORY_SAMPLE", "200"))
    sample_ids = []
    async with session_scope() as session:
        for cur in cur_list:
            rows = (
                (
                    await session.execute(
                        select(BondORM.internal_id)
                        .where(BondORM.currency == cur.upper())
                        .order_by(BondORM.yield_to_maturity.desc())
                        .limit(cap)
                    )
                )
                .scalars()
                .all()
            )
            sample_ids.extend(rows)
    for iid in sample_ids:
        try:
            hist = await client.fetch_history(iid, _days=30)
            if hist:
                async with session_scope() as session:
                    history_rows += await repositories.history.upsert_history_batch(session, hist)
        except Exception:
            history_err += 1

    # Coupon calendar backfill (best-effort) from MOEX bondization.
    coupon_bonds = 0
    coupon_err = 0
    for iid in sample_ids:
        try:
            coupons = await client.fetch_coupons(iid)
            if coupons:
                schedule = _build_coupon_schedule(coupons)
                async with session_scope() as session:
                    orm = (
                        await session.execute(select(BondORM).where(BondORM.internal_id == iid))
                    ).scalar_one_or_none()
                    if orm is not None:
                        orm.coupon_schedule = schedule
                        coupon_bonds += 1
        except Exception:
            coupon_err += 1

    summary = {
        "listing_total": saved,
        "details_ok": saved,
        "details_err": 0,
        "history_rows": history_rows,
        "history_err": history_err,
        "coupon_bonds": coupon_bonds,
        "coupon_err": coupon_err,
        "scored": scored,
        **xlsx_stats,
        "moex_mode": True,
    }
    logger.info("moex_pipeline_done", **summary)
    return summary


def _build_coupon_schedule(coupons: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Group MOEX coupon rows ({date, coupon}) into a year -> [iso dates] map."""
    sched: dict[str, list[str]] = {}
    for c in coupons:
        d = c.get("date")
        if not d:
            continue
        sched.setdefault(d.strftime("%Y"), []).append(d.isoformat())
    for y in sched:
        sched[y].sort()
    return sched


_stock_consecutive_failures = 0


def _bump_stock_failures() -> None:
    global _stock_consecutive_failures
    _stock_consecutive_failures += 1


def _reset_stock_failures() -> None:
    global _stock_consecutive_failures
    _stock_consecutive_failures = 0


async def run_once_moex_stocks(boards: list[str] | None = None) -> dict[str, int]:
    """MOEX stock pipeline: fetch stocks, upsert, backfill history.

    Fully independent of the bond pipeline — uses ``MoexStockClient``
    and the ``stocks`` / ``stock_history`` tables. Gated by
    ``settings.stock.enabled``; after ``settings.stock.error_budget``
    consecutive failed runs the pipeline stops hammering MOEX until a
    successful run resets the counter.
    """
    from scraper.config import get_settings
    from scraper.moex_stocks import MoexStockClient

    settings = get_settings()
    stock_cfg = getattr(settings, "stock", None)
    if stock_cfg is not None and not stock_cfg.enabled:
        logger.info("moex_stocks_disabled")
        return {"stocks_saved": 0, "history_rows": 0, "history_err": 0, "skipped": 1}

    client = MoexStockClient(settings)
    if boards:
        client._boards = boards

    logger.info("moex_stocks_pipeline_start", boards=client._boards)

    saved = 0
    async with client:
        try:
            stocks = await client.fetch_stocks()
        except Exception as exc:
            logger.warning("moex_stocks_fetch_failed", error=str(exc))
            stocks = []
        if not stocks:
            _bump_stock_failures()
            budget = stock_cfg.error_budget if stock_cfg is not None else 3
            if _stock_consecutive_failures >= budget:
                logger.error(
                    "moex_stocks_error_budget_exceeded", failures=_stock_consecutive_failures
                )
            logger.info("moex_stocks_no_stocks")
            return {"stocks_saved": 0, "history_rows": 0, "history_err": 0, "fetch_failed": 1}

        _reset_stock_failures()

        async with session_scope() as session:
            saved = await repositories.stocks.upsert_stocks_batch(session, stocks)
            await session.commit()

        # History backfill (best-effort): top-N stocks by value_traded,
        # trimmed to the configured retention window.
        history_rows = 0
        history_err = 0
        cap = int(os.getenv("MOEX_STOCK_HISTORY_SAMPLE", "100"))
        days = stock_cfg.history_backfill_days if stock_cfg is not None else 730
        cutoff = date.today() - timedelta(days=days)
        sample_ids = []
        async with session_scope() as session:
            all_ids = await repositories.stocks.get_all_stock_internal_ids(session)
            sample_ids = list(all_ids[:cap])

        for iid in sample_ids:
            try:
                hist = await client.fetch_stock_history(iid, _days=30)
                if hist:
                    hist = [h for h in hist if h.date >= cutoff]
                    if hist:
                        async with session_scope() as session:
                            history_rows += await repositories.stocks.upsert_stock_history_batch(
                                session, hist
                            )
            except Exception:
                history_err += 1

    summary = {
        "stocks_saved": saved,
        "history_rows": history_rows,
        "history_err": history_err,
        "moex_stocks_mode": True,
    }
    logger.info("moex_stocks_pipeline_done", **summary)
    return summary


async def run_once(client, currencies: Iterable[str]) -> dict[str, int]:
    settings = client.settings
    cur_list = list(currencies)
    ingestion_run = f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"
    logger.info("pipeline_start", currencies=cur_list, ingestion_run=ingestion_run)

    # Graceful degradation: if the primary source is unavailable (e.g. no paid
    # credentials), do not crash the whole pipeline. Serve stale DB data and let
    # the fallback source (if configured) backfill where possible.
    try:
        internal_ids = await collect_listing(client, cur_list)
    except Exception as exc:
        logger.warning("listing_failed_serving_stale", error=str(exc))
        from scraper.fallback_source import fetch_fallback_bonds

        internal_ids = []
        saved_fb = 0
        async with session_scope() as session:
            for cur in cur_list:
                fb = await fetch_fallback_bonds(cur)
                if not fb:
                    continue
                logger.info("fallback_bonds_fetched", currency=cur, count=len(fb))
                for b in fb:
                    iid = b.get("internal_id")
                    if not iid:
                        continue
                    existing = (
                        await session.execute(select(BondORM).where(BondORM.internal_id == iid))
                    ).scalar_one_or_none()
                    maturity = None
                    if b.get("maturity_date"):
                        try:
                            maturity = datetime.fromisoformat(b["maturity_date"]).date()
                        except (ValueError, TypeError):
                            maturity = None
                    if existing is None:
                        session.add(
                            BondORM(
                                internal_id=iid,
                                name=b.get("name") or iid,
                                issuer=b.get("issuer"),
                                currency=b.get("currency", "RUB"),
                                price=_d(b.get("price")),
                                yield_to_maturity=_d(b.get("yield_to_maturity")),
                                maturity_date=maturity,
                                status=b.get("status", "active"),
                                fetched_at=datetime.now(UTC),
                            )
                        )
                    else:
                        existing.price = _d(b.get("price"))
                        existing.yield_to_maturity = _d(b.get("yield_to_maturity"))
                        existing.fetched_at = datetime.now(UTC)
                    saved_fb += 1
                await session.commit()
        # Keep existing bonds scored; details/history skipped in stale mode.
        xlsx_stats = await enrich_from_xlsx()
        async with session_scope() as session:
            scored = await recompute_all(session)
        summary = {
            "listing_total": 0,
            "details_ok": 0,
            "details_err": 0,
            "history_rows": 0,
            "history_err": 0,
            "scored": scored,
            **xlsx_stats,
            "stale_mode": True,
        }
        async with session_scope() as session:
            await record_snapshot_lineage(
                session,
                source="fallback",
                ingestion_run=ingestion_run,
                quality_status="critical",
                rows_processed=saved_fb,
                extra={"stale_mode": True},
            )
        logger.info("pipeline_done_stale", **summary)
        return summary
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
    async with session_scope() as session:
        await record_snapshot_lineage(
            session,
            source=settings.data_provider or "aigenis",
            ingestion_run=ingestion_run,
            quality_status="ok" if details_err == 0 else "warning",
            rows_processed=details_ok + details_err,
            license_contract_id=settings.license_contract_id,
            extra={"market": ",".join(cur_list), "details_err": details_err},
        )
    logger.info("pipeline_done", **summary)
    return summary
