"""verify_aigenis.py — комплексная проверка парсинга Aigenis.

Три режима:
  1) mock — использует фикстуры из tests/fixtures/
  2) sqlite — полный сквозной pipeline с SQLite in-memory
  3) live — реальный запрос к Aigenis (если сеть доступна)

Запуск:
  python verify_aigenis.py mock      # быстро, без сети
  python verify_aigenis.py sqlite    # end-to-end на SQLite
  python verify_aigenis.py live      # реальный сайт
  python verify_aigenis.py all       # все три режима
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("AIGENIS_HEADLESS", "true")
os.environ.setdefault("AIGENIS_USE_STEALTH", "false")
os.environ.setdefault("AIGENIS_DELAY_BETWEEN_REQUESTS", "0")
os.environ.setdefault(
    "DATABASE_URL", "sqlite+aiosqlite:///file:verify?mode=memory&cache=shared&uri=true"
)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Избегаем Alembic при тесте — создаём схему напрямую из Base
os.environ["AIGENIS_SKIP_MIGRATIONS"] = "1"

from scraper import repositories  # noqa: E402
from scraper.config import get_settings  # noqa: E402
from scraper.db import get_engine as get_engine_fn
from scraper.db import session_scope  # noqa: E402
from scraper.orm import Base  # noqa: E402

REPORT: dict = {"started_at": datetime.now(UTC).isoformat(), "checks": []}


def _check(name: str, ok: bool, details: dict | str = "") -> None:
    REPORT["checks"].append({"name": name, "ok": ok, "details": details})
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}: {details}")


async def _init_db() -> None:
    """Создать схему в SQLite in-memory (через единый движок db)."""
    from scraper import db as scraper_db

    scraper_db._engine = None
    scraper_db._session_factory = None
    engine = get_engine_fn()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# =============================================================================
# Режим 1: MOCK (по фикстурам)
# =============================================================================


async def verify_mock() -> dict:
    """Проверить парсеры на сохранённых фикстурах."""
    print("\n=== Режим 1: MOCK (фикстуры) ===")
    from scraper.api.detail import parse_detail_payload
    from scraper.api.history import parse_history_payload
    from scraper.api.listing import parse_listing_payload
    from scraper.parsers.detail import parse_detail_html
    from scraper.parsers.listing import parse_listing_html

    fx = PROJECT_ROOT / "tests" / "fixtures"
    result: dict = {"listing": {}, "detail": {}, "history": {}}

    # 1. Listing JSON
    listing_payload = json.loads((fx / "listing.json").read_text(encoding="utf-8"))
    items = parse_listing_payload(listing_payload, "USD")
    _check("mock.listing.count", len(items) >= 1, f"items={len(items)}")
    _check(
        "mock.listing.has_internal_id",
        all("internal_id" in it for it in items),
        f"ids={[it['internal_id'] for it in items]}",
    )
    _check(
        "mock.listing.currency_valid",
        all(it["currency"] in {"USD", "BYN", "EUR", "XAU", "XAG", "XPT"} for it in items),
        f"currencies={list({it['currency'] for it in items})}",
    )
    result["listing"] = {"count": len(items), "items": items}

    # 2. Listing HTML (DOM fallback)
    html = (fx / "listing.html").read_text(encoding="utf-8")
    dom_items = parse_listing_html(html, currency="USD")
    _check("mock.listing.dom.count", len(dom_items) >= 2, f"items={len(dom_items)}")
    result["listing"]["dom_count"] = len(dom_items)

    # 3. Detail JSON
    detail_payload = json.loads((fx / "detail.json").read_text(encoding="utf-8"))
    bond = parse_detail_payload(detail_payload, "OP-51")
    _check("mock.detail.internal_id", bond.internal_id == "OP-51", bond.internal_id)
    _check(
        "mock.detail.currency_valid",
        bond.currency in {"USD", "BYN", "EUR", "XAU", "XAG", "XPT"},
        bond.currency,
    )
    _check("mock.detail.nominal_positive", (bond.nominal or 0) > 0, f"nominal={bond.nominal}")
    _check(
        "mock.detail.yield_in_range",
        0 < float(bond.yield_to_maturity or 0) < 50,
        f"ytm={bond.yield_to_maturity}",
    )
    _check(
        "mock.detail.coupon_in_range",
        0 <= float(bond.coupon_rate or 0) < 100,
        f"coupon={bond.coupon_rate}",
    )
    _check("mock.detail.price_in_range", 0 < float(bond.price or 0) < 1000, f"price={bond.price}")
    _check(
        "mock.detail.maturity_future",
        bond.maturity_date is None or bond.maturity_date > date(2020, 1, 1),
        f"mat={bond.maturity_date}",
    )
    # Проверка новых полей
    _check(
        "mock.detail.registration_number",
        bool(bond.registration_number),
        f"reg={bond.registration_number}",
    )
    _check("mock.detail.issue_volume", (bond.issue_volume or 0) > 0, f"volume={bond.issue_volume}")
    _check("mock.detail.issue_number", (bond.issue_number or 0) > 0, f"issue={bond.issue_number}")
    _check("mock.detail.income_method", bool(bond.income_method), f"method={bond.income_method}")
    _check("mock.detail.in_stock", bond.in_stock is not None, f"stock={bond.in_stock}")
    _check("mock.detail.guarantor", bool(bond.guarantor), f"guarantor={bond.guarantor}")
    _check(
        "mock.detail.coupon_description",
        bool(bond.coupon_description),
        f"desc={bond.coupon_description}",
    )
    _check(
        "mock.detail.coupon_schedule",
        bool(bond.coupon_schedule),
        f"schedule_keys={list((bond.coupon_schedule or {}).keys())}",
    )
    result["detail"] = bond.model_dump(mode="json")

    # 4. Detail HTML (DOM fallback)
    html = (fx / "detail.html").read_text(encoding="utf-8")
    payload = parse_detail_html(html, internal_id="OP-51")
    _check("mock.detail.dom.name", bool(payload.get("name")), payload.get("name"))
    _check(
        "mock.detail.dom.registration_number",
        bool(payload.get("registration_number")),
        payload.get("registration_number"),
    )
    _check(
        "mock.detail.dom.issue_number",
        bool(payload.get("issue_number")),
        payload.get("issue_number"),
    )
    _check(
        "mock.detail.dom.issue_volume",
        bool(payload.get("issue_volume")),
        payload.get("issue_volume"),
    )
    _check("mock.detail.dom.in_stock", payload.get("in_stock") is not None, payload.get("in_stock"))
    _check("mock.detail.dom.guarantor", bool(payload.get("guarantor")), payload.get("guarantor"))
    _check(
        "mock.detail.dom.coupon_description",
        bool(payload.get("coupon_description")),
        payload.get("coupon_description"),
    )
    _check(
        "mock.detail.dom.coupon_schedule",
        bool(payload.get("coupon_schedule")),
        payload.get("coupon_schedule"),
    )
    result["detail"]["dom_payload"] = payload

    # 5. History JSON
    history_payload = json.loads((fx / "history.json").read_text(encoding="utf-8"))
    rows = parse_history_payload(history_payload, "OP-51")
    _check("mock.history.count", len(rows) >= 1, f"rows={len(rows)}")
    _check(
        "mock.history.dates_valid",
        all(r.date <= date.today() for r in rows),
        f"dates={[r.date for r in rows]}",
    )
    _check("mock.history.has_yield", all(r.yield_ is not None for r in rows))
    result["history"] = [
        {"date": r.date.isoformat(), "price": float(r.price or 0), "yield": float(r.yield_ or 0)}
        for r in rows
    ]

    return result


# =============================================================================
# Режим 2: SQLITE end-to-end
# =============================================================================


async def verify_sqlite() -> dict:
    """Сквозной pipeline на SQLite in-memory: listing → details → history → DB → Score."""
    print("\n=== Режим 2: SQLITE end-to-end ===")
    await _init_db()

    settings = get_settings()

    # Подменяем client.fetch_* методами, читающими фикстуры
    from scraper.client import AigenisClient

    fx = PROJECT_ROOT / "tests" / "fixtures"

    async def fake_listing(self, currency):
        items = json.loads((fx / "listing.json").read_text(encoding="utf-8"))
        return items

    async def fake_detail(self, internal_id):
        return json.loads((fx / "detail.json").read_text(encoding="utf-8"))

    async def fake_history(self, internal_id, since, until=None):
        return json.loads((fx / "history.json").read_text(encoding="utf-8"))

    AigenisClient.fetch_listing = fake_listing
    AigenisClient.fetch_detail = fake_detail
    AigenisClient.fetch_history = fake_history
    AigenisClient.start = lambda self: asyncio.sleep(0)
    AigenisClient.close = lambda self: asyncio.sleep(0)

    # Запускаем pipeline
    from scraper.pipeline import run_once

    async with AigenisClient(settings) as client:
        summary = await run_once(client, settings.currencies)

    _check(
        "sqlite.pipeline.listing_total",
        summary["listing_total"] >= 1,
        f"total={summary['listing_total']}",
    )
    _check(
        "sqlite.pipeline.details_ok",
        summary["details_ok"] >= 1,
        f"ok={summary['details_ok']}, err={summary['details_err']}",
    )
    _check(
        "sqlite.pipeline.history_rows",
        summary["history_rows"] >= 1,
        f"rows={summary['history_rows']}",
    )
    _check("sqlite.pipeline.scored", summary["scored"] >= 1, f"scored={summary['scored']}")

    # Проверяем, что данные реально в БД
    async with session_scope() as session:
        total_bonds = await repositories.bonds.count_bonds(session)
        total_history = await repositories.history.count_history(session)
        latest = await repositories.bonds.latest_fetched_at(session)
        from scoring.repository import top_scores

        top = await top_scores(session, limit=10)

    _check("sqlite.db.bonds_count", total_bonds >= 1, f"count={total_bonds}")
    _check("sqlite.db.history_count", total_history >= 1, f"count={total_history}")
    _check("sqlite.db.latest_fetched", latest is not None, f"latest={latest}")

    # Проверка деталей
    async with session_scope() as session:
        from sqlalchemy import select

        from scraper.orm import BondORM

        res = await session.execute(select(BondORM))
        bond = res.scalars().first()

    _check(
        "sqlite.db.bond_fields",
        bond is not None and bond.currency in {"USD", "BYN", "EUR", "XAU", "XAG", "XPT"},
        f"currency={bond.currency if bond else None}",
    )
    _check(
        "sqlite.db.bond_yield_range",
        bond is not None and 0 <= float(bond.yield_to_maturity or 0) <= 100,
        f"ytm={bond.yield_to_maturity if bond else None}",
    )

    # Score top
    _check("sqlite.scoring.top_count", len(top) >= 1, f"top_count={len(top)}")
    if top:
        scores = [float(s.score) for s in top]
        _check(
            "sqlite.scoring.scores_in_range", all(0 <= s <= 200 for s in scores), f"scores={scores}"
        )

    # Desk V4 проверка
    from desk import duration, relative_value, stress, yield_curve
    from scraper.models import Bond as BondModel

    async with session_scope() as session:
        from sqlalchemy import select as sel

        from scraper.orm import BondORM

        res = await session.execute(sel(BondORM))
        orm_bonds = list(res.scalars().all())
    bonds = [
        BondModel(
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
            registration_number=b.registration_number,
            issue_number=b.issue_number,
            in_stock=b.in_stock,
            guarantor=b.guarantor,
            maturity_term_text=b.maturity_term_text,
            coupon_description=b.coupon_description,
        )
        for b in orm_bonds
    ]
    if bonds:
        rep = duration.duration_report(bonds[0])
        _check(
            "sqlite.desk.duration",
            rep.modified_duration > 0,
            f"mod_dur={rep.modified_duration:.3f}",
        )
        curve = yield_curve.curve_from_bonds(bonds)
        _check("sqlite.desk.curve", len(curve.points) >= 1, f"points={len(curve.points)}")
        signals = relative_value.relative_value_signals(bonds)
        _check("sqlite.desk.rv", len(signals) >= 1, f"signals={len(signals)}")
        scn = stress.PRESET_SCENARIOS["parallel_+100bp"]
        res = stress.run_stress(scn, [(b, Decimal("1000")) for b in bonds])
        _check("sqlite.desk.stress", res.pnl != 0, f"pnl={float(res.pnl):.2f}")

    return {
        "summary": summary,
        "db": {"bonds": total_bonds, "history": total_history},
        "top_scores": [(s.internal_id, float(s.score)) for s in top],
    }


# =============================================================================
# Режим 3: LIVE (реальный сайт)
# =============================================================================


async def verify_live() -> dict:
    """Попытка реального парсинга aigenis.by (с HTTP-проверкой доступности)."""
    print("\n=== Режим 3: LIVE (aigenis.by) ===")
    settings = get_settings()
    settings.base_url = "https://aigenis.by"

    result: dict = {"attempted": True, "currencies": {}, "http_probe": {}, "bond_pages": {}}

    # 1) Быстрая HTTP-проверка доступности сайта
    try:
        import requests

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        resp = requests.get(settings.base_url, timeout=15, headers={"User-Agent": ua})
        status = resp.status_code
        html = resp.text[:8192]
        result["http_probe"] = {
            "ok": True,
            "status": status,
            "size_bytes": len(resp.text),
            "snippet": html[:300],
        }
        _check("live.http_probe", True, f"status={status}, total_size={len(resp.text)} bytes")
        has_bonds_table = "облигац" in html.lower() or "bond" in html.lower()
        _check(
            "live.html_contains_bonds",
            has_bonds_table,
            f"contains_bonds_keyword={has_bonds_table}",
        )

        # 1a) Проверка страницы /bonds/ — основной каталог
        for page in ("/bonds/", "/"):
            try:
                r = requests.get(
                    settings.base_url.rstrip("/") + page,
                    timeout=15,
                    headers={"User-Agent": ua},
                )
                page_html = r.text.lower()
                ob_count = page_html.count("облигац")
                bond_count = page_html.count("bond")
                usd_count = page_html.count("usd") + page_html.count("доллар")
                byn_count = page_html.count("byn") + page_html.count("белорусск")
                metal_count = (
                    page_html.count("золот") + page_html.count("серебр") + page_html.count("платин")
                )
                result["bond_pages"][page] = {
                    "status": r.status_code,
                    "size": len(r.text),
                    "obligation_mentions": ob_count,
                    "bond_mentions": bond_count,
                    "usd_mentions": usd_count,
                    "byn_mentions": byn_count,
                    "metal_mentions": metal_count,
                }
                _check(
                    f"live.bonds_page.{page.strip('/') or 'root'}",
                    r.status_code == 200 and ob_count > 0,
                    f"status={r.status_code}, облигац×{ob_count}, USD×{usd_count}, BYN×{byn_count}, metals×{metal_count}",
                )
            except Exception as e:  # noqa: BLE001
                result["bond_pages"][page] = {"error": str(e)[:200]}
                _check(f"live.bonds_page.{page.strip('/') or 'root'}", False, f"{type(e).__name__}")
    except Exception as e:  # noqa: BLE001
        result["http_probe"] = {"ok": False, "error": str(e)[:200]}
        _check(
            "live.http_probe",
            False,
            f"{type(e).__name__}: {str(e)[:120]}",
        )

    # 2) Если HTTP доступен — Playwright-парсинг
    if result["http_probe"].get("ok"):
        from scraper.client import AigenisClient

        try:
            async with AigenisClient(settings) as client:
                for currency in ("USD", "BYN"):
                    print(f"  → fetch listing {currency}...")
                    t0 = time.monotonic()
                    try:
                        items = await asyncio.wait_for(
                            client.fetch_listing(currency),
                            timeout=30.0,
                        )
                        elapsed = time.monotonic() - t0
                        if isinstance(items, dict):
                            items = list(items.values()) if items else []
                        sample = (
                            [dict(it) if isinstance(it, dict) else str(it) for it in items[:5]]
                            if items
                            else []
                        )
                        result["currencies"][currency] = {
                            "ok": True,
                            "count": len(items),
                            "elapsed_sec": round(elapsed, 2),
                            "sample": sample,
                        }
                        _check(
                            f"live.listing.{currency}.count",
                            len(items) >= 1,
                            f"count={len(items)} in {elapsed:.2f}s",
                        )
                    except TimeoutError:
                        result["currencies"][currency] = {"ok": False, "error": "timeout 30s"}
                        _check(f"live.listing.{currency}", False, "timeout 30s")
                    except Exception as e:  # noqa: BLE001
                        result["currencies"][currency] = {"ok": False, "error": str(e)[:200]}
                        _check(
                            f"live.listing.{currency}", False, f"{type(e).__name__}: {str(e)[:120]}"
                        )
        except Exception as e:  # noqa: BLE001
            result["client_error"] = str(e)[:200]
            _check("live.client_init", False, f"{type(e).__name__}: {str(e)[:120]}")
    else:
        print("  ⚠ HTTP probe failed, skipping Playwright (DNS/network issue)")
        _check("live.skipped", True, "skipped due to HTTP probe failure")

    return result


# =============================================================================
# Main
# =============================================================================


async def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    print("=== Verify Aigenis Parser ===")
    print(f"Mode: {mode}")
    print(f"Time: {REPORT['started_at']}")

    if mode in ("mock", "all"):
        try:
            REPORT["mock"] = await verify_mock()
        except Exception as e:  # noqa: BLE001
            _check("mock.overall", False, f"{type(e).__name__}: {e}")

    if mode in ("sqlite", "all"):
        try:
            REPORT["sqlite"] = await verify_sqlite()
        except Exception as e:  # noqa: BLE001
            _check("sqlite.overall", False, f"{type(e).__name__}: {e}")

    if mode in ("live", "all"):
        try:
            REPORT["live"] = await verify_live()
        except Exception as e:  # noqa: BLE001
            _check("live.overall", False, f"{type(e).__name__}: {e}")

    # Сводка
    REPORT["finished_at"] = datetime.now(UTC).isoformat()
    passed = sum(1 for c in REPORT["checks"] if c["ok"])
    failed = sum(1 for c in REPORT["checks"] if not c["ok"])
    REPORT["summary"] = {"passed": passed, "failed": failed, "total": passed + failed}

    print("\n=== ИТОГО ===")
    print(f"Пройдено: {passed}")
    print(f"Провалено: {failed}")

    # Сохраняем отчёт
    report_path = PROJECT_ROOT / "verify_report.json"
    report_path.write_text(
        json.dumps(REPORT, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nОтчёт: {report_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
