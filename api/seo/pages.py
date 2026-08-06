"""Public SEO pages: bond leaderboard, per-bond pages, sitemap, robots.txt.

Routes (root-level for clean, indexable URLs):
    GET /bonds                  leaderboard / top bonds (filter ?currency=)
    GET /bonds/{internal_id}    per-bond facts + Score + CTA
    GET /sitemap.xml            dynamic sitemap of every bond page
    GET /robots.txt             crawler directives + sitemap pointer
"""

from __future__ import annotations

import asyncio
import json
import os

from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import select

from api.seo import router
from api.seo._common import (
    _VERDICTS,
    SEO_SITEMAP_PATH,
    SITE_NAME,
    _abs,
    _app_links,
    _esc,
    _fmt_date,
    _fmt_num,
    _is_bot,
    _score_tier,
    _skeleton,
    _spa_page,
    _sparkline,
)
from api.seo.guides import _GUIDES
from scraper.db import session_scope
from scraper.logging import get_logger
from scraper.orm import BondHistoryORM, BondORM, BondScoreORM, CompanyORM

logger = get_logger("api.seo")


@router.get("/bonds", response_class=HTMLResponse)
async def seo_bonds(
    request: Request, currency: str | None = None, sort: str = "score", market: str | None = None
):
    if not _is_bot(request):
        spa = _spa_page()
        if spa is not None:
            return spa
    cur = currency.upper() if currency else None
    mkt = market.lower() if market and market.lower() in ("bcse", "moex") else None
    async with session_scope() as session:
        score_stmt = select(BondScoreORM)
        if mkt:
            score_stmt = score_stmt.join(
                BondORM, BondScoreORM.internal_id == BondORM.internal_id, isouter=True
            )
            score_stmt = score_stmt.where(BondORM.market == mkt)
        score_stmt = score_stmt.order_by(BondScoreORM.score.desc())
        scores = list((await session.execute(score_stmt)).scalars().all())
        ids = [s.internal_id for s in scores]
        if not ids:
            return _skeleton(
                f"Облигации — рейтинг {SITE_NAME}",
                "Аналитика и рейтинг облигаций фиксированного дохода.",
                "<h1>Облигации</h1><p class='sub'>Данные пока не загружены.</p>",
                request,
                _abs(request, "/bonds"),
            )
        bond_stmt = select(BondORM).where(BondORM.internal_id.in_(ids))
        if cur:
            bond_stmt = bond_stmt.where(BondORM.currency == cur)
        if mkt:
            bond_stmt = bond_stmt.where(BondORM.market == mkt)
        bonds = {b.internal_id: b for b in (await session.execute(bond_stmt)).scalars().all()}
        score_map = {s.internal_id: float(s.score) for s in scores}

    # Iterate the (currency-filtered) query result directly; `ids` may contain
    # bonds excluded by the currency filter, so don't index by `ids`.
    rows = list(bonds.values())
    # Sort: by score (default) or by yield desc.
    if sort == "ytm":
        rows.sort(
            key=lambda b: float(b.yield_to_maturity) if b.yield_to_maturity is not None else -1,
            reverse=True,
        )
    else:
        rows.sort(key=lambda b: score_map.get(b.internal_id, -1), reverse=True)

    cur_filter = cur or "Все"
    title = f"Облигации {_esc(cur_filter)}: рейтинг по доходности и Score | {SITE_NAME}"
    desc = (
        f"Рейтинг облигаций ({cur_filter}) по доходности к погашению и Score Aigenis. "
        f"Топ-{min(len(rows), 50)} выпусков с ценой, купоном и погашением."
    )

    # Currency filter chips from available data.
    cur_counts: dict[str, int] = {}
    for b in bonds.values():
        cur_counts[b.currency] = cur_counts.get(b.currency, 0) + 1
    chips = [
        f'<a class="{"active" if not cur else ""}" href="/bonds{"?currency=" if cur else ""}">Все</a>'
    ]
    for c in sorted(cur_counts):
        q = f"?currency={c}"
        active = "active" if cur == c else ""
        chips.append(f'<a class="{active}" href="/bonds{q}">{_esc(c)} ({cur_counts[c]})</a>')

    body = f"""<h1>Рейтинг облигаций</h1>
<p class="sub">Топ выпусков по Score Aigenis и доходности к погашению. Клик — на страницу облигации.</p>
<div class="filters">{" ".join(chips)}</div>
<div class="filters">
  <a class="{"" if sort != "ytm" else "active"}" href="/bonds{"?currency=" + cur if cur else ""}">По Score</a>
  <a class="{("active" if sort == "ytm" else "")}" href="/bonds?sort=ytm{"&currency=" + cur if cur else ""}">По доходности</a>
</div>
<div class="card" style="padding:6px 4px">
<table>
<thead><tr><th>Облигация</th><th>Валюта</th><th>YTM, %</th><th>Цена</th>
<th>Купон, %</th><th>Погашение</th><th>Score</th></tr></thead>
<tbody>"""
    for b in rows[:50]:
        sc = score_map.get(b.internal_id)
        tier = _score_tier(sc)
        badge = (
            f'<span class="badge b-{tier}">{tier} · {_fmt_num(sc, 1)}</span>'
            if tier
            else '<span class="badge b-na">—</span>'
        )
        body += (
            f'<tr><td><a href="/bonds/{_esc(b.internal_id)}">{_esc(b.name)}</a>'
            f"<br><span class='num' style='color:var(--muted);font-size:12px'>{_esc(b.internal_id)}</span></td>"
            f"<td>{_esc(b.currency)}</td>"
            f"<td class='num'>{_fmt_num(b.yield_to_maturity)}</td>"
            f"<td class='num'>{_fmt_num(b.price)}</td>"
            f"<td class='num'>{_fmt_num(b.coupon_rate)}</td>"
            f"<td class='num'>{_fmt_date(b.maturity_date)}</td>"
            f"<td>{badge}</td></tr>"
        )
    body += "</tbody></table></div>"
    body += (
        f'<p class="note">Показано {min(len(rows), 50)} из {len(rows)} облигаций'
        + (f" в валюте {_esc(cur)}" if cur else "")
        + ".</p>"
    )

    json_ld = [
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "CollectionPage",
                "name": title,
                "description": desc,
                "url": _abs(request, "/bonds"),
                "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": _abs(request, "/")},
            },
            ensure_ascii=False,
        )
    ]
    body += (
        '<p class="note">Гайды: <a href="/guides/kak-vybrat-obligaciyu">'
        "Как выбрать облигацию</a> · "
        '<a href="/guides/duration-i-repo-prosto">Duration и РЕПО</a> · '
        '<a href="/guides/obligacii-vs-depozit">Облигации vs депозит</a> · '
        '<a href="/partners">Aigenis Bonds для бизнеса →</a></p>'
    )
    return _skeleton(title, desc, body, request, _abs(request, "/bonds"), json_ld)


@router.get("/bonds/{internal_id}", response_class=HTMLResponse)
async def seo_bond(request: Request, internal_id: str):
    if not _is_bot(request):
        spa = _spa_page()
        if spa is not None:
            return spa
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == internal_id))
        ).scalar_one_or_none()
        if bond is None:
            not_found = (
                "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
                f"<title>Облигация не найдена | {_esc(SITE_NAME)}</title></head>"
                "<body style='font-family:system-ui;max-width:640px;margin:80px auto;padding:0 18px'>"
                f"<h1>Облигация {_esc(internal_id)} не найдена</h1>"
                f"<p><a href='{_esc(_abs(request, '/bonds'))}'>← Рейтинг облигаций</a></p></body></html>"
            )
            return HTMLResponse(content=not_found, status_code=404)
        score_row = (
            await session.execute(
                select(BondScoreORM).where(BondScoreORM.internal_id == internal_id)
            )
        ).scalar_one_or_none()
        score = float(score_row.score) if score_row and score_row.score is not None else None
        tier = score_row.tier if score_row else None
        if not tier:
            tier = _score_tier(score)
        company = None
        if bond.issuer:
            company = (
                await session.execute(select(CompanyORM).where(CompanyORM.issuer == bond.issuer))
            ).scalar_one_or_none()
        history = list(
            (
                await session.execute(
                    select(BondHistoryORM)
                    .where(BondHistoryORM.internal_id == internal_id)
                    .order_by(BondHistoryORM.date.desc())
                    .limit(60)
                )
            )
            .scalars()
            .all()
        )

    sc = score
    tier_badge = (
        f'<span class="badge b-{tier}">{tier} · {_fmt_num(sc, 1)}</span>'
        if tier
        else '<span class="badge b-na">—</span>'
    )
    verdict = _VERDICTS.get(tier, "Профиль требует анализа.")
    web, bot = _app_links(request)

    spark = _sparkline([float(h.price) for h in history if h.price is not None][::-1])

    facts = f"""<div class="grid">
  <div class="stat"><div class="k">Валюта</div><div class="v">{_esc(bond.currency)}</div></div>
  <div class="stat"><div class="k">Цена</div><div class="v num">{_fmt_num(bond.price)}</div></div>
  <div class="stat"><div class="k">Доходность к погашению</div><div class="v num">{_fmt_num(bond.yield_to_maturity)}%</div></div>
  <div class="stat"><div class="k">Купон</div><div class="v num">{_fmt_num(bond.coupon_rate)}%</div></div>
  <div class="stat"><div class="k">Частота купона</div><div class="v num">{bond.coupon_frequency if bond.coupon_frequency else "—"}</div></div>
  <div class="stat"><div class="k">Погашение</div><div class="v num" style="font-size:16px">{_fmt_date(bond.maturity_date)}</div></div>
</div>"""

    issuer_line = ""
    if company and company.name:
        issuer_line = (
            f"Эмитент: <b>{_esc(company.name)}</b>"
            + (f" · {_esc(company.sector)}" if company.sector else "")
            + (
                f"<br><span class='note'>{_esc(company.description)}</span>"
                if company.description
                else ""
            )
        )

    body = f"""<h1>{_esc(bond.name)}</h1>
<p class="sub">ID: <span class="num">{_esc(bond.internal_id)}</span> · Статус: {_esc(bond.status)}</p>
<div class="card">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <div>Score Aigenis: {tier_badge}</div>
    <div style="color:var(--muted)">{_esc(verdict)}</div>
  </div>
  {facts}
  {("<h2>Динамика цены</h2>" + spark) if spark else ""}
  {('<p class="note">' + issuer_line + "</p>" if issuer_line else "")}
</div>
<div class="card" style="border-color:var(--brand);background:#f0f6f9">
  <h2 style="margin-top:0">Полный разбор — бесплатно</h2>
  <p>Что влияет на Score, ML-прогноз, стресс-тест и рекомендация «стоит ли покупать» —
  в приложении {SITE_NAME}. Доступен 7-дневный пробный Pro.</p>
  <p style="margin-bottom:0"><a class="cta" href="{_esc(bot)}">Открыть в Telegram-боте →</a>
  &nbsp; <a href="{_esc(web)}">Открыть в веб-приложении →</a></p>
</div>
<p class="note">Данные обновлены: {_fmt_date(bond.fetched_at)}. Источник — публичные и партнёрские
рыночные данные. Не является индивидуальной инвестиционной рекомендацией.</p>
<p><a href="{_esc(_abs(request, "/bonds"))}">← Рейтинг всех облигаций</a></p>"""

    title = f"{_esc(bond.name)} ({_esc(bond.internal_id)}): доходность, цена, Score | {SITE_NAME}"
    desc = (
        f"Облигация {_esc(bond.name)}: доходность к погашению "
        f"{_fmt_num(bond.yield_to_maturity)}%, цена {_fmt_num(bond.price)}, "
        f"купон {_fmt_num(bond.coupon_rate)}%, погашение {_fmt_date(bond.maturity_date)}. "
        f"Score Aigenis {_fmt_num(sc, 1)} (тир {tier or '—'})."
    )

    json_ld = [
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": bond.name,
                "category": "Облигация фиксированного дохода",
                "description": desc,
                "url": _abs(request, f"/bonds/{bond.internal_id}"),
                "brand": {
                    "@type": "Brand",
                    "name": (company.name if company else (bond.issuer or SITE_NAME)),
                },
                "offers": {
                    "@type": "Offer",
                    "priceCurrency": bond.currency,
                    "price": _fmt_num(bond.price, 2),
                    "availability": "https://schema.org/InStock",
                },
            },
            ensure_ascii=False,
        )
    ]
    json_ld.append(
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "Облигации",
                        "item": _abs(request, "/bonds"),
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": bond.name,
                        "item": _abs(request, f"/bonds/{bond.internal_id}"),
                    },
                ],
            },
            ensure_ascii=False,
        )
    )
    return _skeleton(
        title, desc, body, request, _abs(request, f"/bonds/{bond.internal_id}"), json_ld
    )


async def _sitemap_urls(base_url: str) -> list[str]:
    base = base_url.rstrip("/")
    urls = [f"{base}/bonds", f"{base}/partners", f"{base}/guides", f"{base}/calculator"]
    urls += [f"{base}/guides/{g['slug']}" for g in _GUIDES]
    # Bond pages are best-effort: a transient DB issue must not blank the sitemap
    # (crawlers depend on it). Static pages above are always included.
    try:
        async with session_scope() as session:
            result = await session.execute(select(BondORM.internal_id, BondORM.fetched_at))
            rows = result.all()
        for iid, _fetched in rows:
            urls.append(f"{base}/bonds/{_esc(iid)}")
    except Exception as exc:
        logger.warning("sitemap_bonds_query_failed", error=str(exc))
    return urls


def _sitemap_xml(urls: list[str]) -> str:
    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for u in urls:
        body.append(f"  <url><loc>{u}</loc></url>")
    body.append("</urlset>")
    return "\n".join(body)


@router.get("/sitemap.xml", response_class=PlainTextResponse)
async def seo_sitemap(request: Request):
    # Serve a pre-generated file if present (regenerated by the scheduler after
    # each parse); otherwise render on the fly from the request's base URL so the
    # canonical domain is always correct.
    xml = await asyncio.to_thread(_read_sitemap_file)
    if xml is None:
        urls = await _sitemap_urls(str(request.base_url))
        xml = _sitemap_xml(urls)
    return PlainTextResponse(
        xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=600"}
    )


def _read_sitemap_file() -> str | None:
    """Blocking file read, offloaded to a worker thread (never blocks the loop)."""
    try:
        if os.path.exists(SEO_SITEMAP_PATH) and os.path.getsize(SEO_SITEMAP_PATH) > 0:
            with open(SEO_SITEMAP_PATH, encoding="utf-8") as fh:
                return fh.read()
    except OSError:
        pass
    return None


async def regenerate_sitemap() -> str | None:
    """Regenerate the cached sitemap file after a parse run.

    Only writes when ``SEO_PUBLIC_BASE_URL`` (the canonical public domain) is
    configured — without a known public base URL the per-request endpoint stays
    the source of truth. Returns the XML written, or ``None`` if skipped.
    """
    base_url = os.getenv("SEO_PUBLIC_BASE_URL", "").strip()
    if not base_url:
        return None
    urls = await _sitemap_urls(base_url)
    xml = _sitemap_xml(urls)
    if not await asyncio.to_thread(_write_sitemap_file, xml):
        return None
    logger.info("seo_sitemap_regenerated", urls=len(urls), path=SEO_SITEMAP_PATH)
    return xml


def _write_sitemap_file(xml: str) -> bool:
    try:
        dirname = os.path.dirname(SEO_SITEMAP_PATH)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(SEO_SITEMAP_PATH, "w", encoding="utf-8") as fh:
            fh.write(xml)
        return True
    except OSError as exc:
        logger.warning("seo_sitemap_write_failed", error=str(exc))
        return False


@router.get("/robots.txt", response_class=PlainTextResponse)
async def seo_robots(request: Request):
    base = str(request.base_url).rstrip("/")
    # Block crawler access to private API and the app shell; allow SEO pages.
    text = (
        "User-agent: *\n"
        "Allow: /bonds\n"
        "Allow: /partners\n"
        "Allow: /guides\n"
        "Allow: /calculator\n"
        "Allow: /sitemap.xml\n"
        "Disallow: /api/\n"
        "Disallow: /widget\n"
        "Disallow: /docs\n"
        "Disallow: /redoc\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return PlainTextResponse(text, media_type="text/plain")
