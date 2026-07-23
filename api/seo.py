"""Public, server-rendered SEO pages for bonds and leaderboards.

These pages are intentionally plain HTML (no client JS) so search-engine
crawlers index them fully. They act as a free organic acquisition surface and
funnel visitors into the app / Telegram bot (see ``docs/sales/cmo_audit.md``,
§2 and §6 — "публичные SEO-страницы по каждой облигации" + "лидерборды").

Routes (root-level for clean, indexable URLs):
    GET /bonds                  leaderboard / top bonds (filter ?currency=)
    GET /bonds/{internal_id}    per-bond facts + Score + CTA
    GET /sitemap.xml            dynamic sitemap of every bond page
    GET /robots.txt             crawler directives + sitemap pointer
"""
from __future__ import annotations

import html
import json
import os
import tempfile
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Form, Request
from scraper.config import get_settings
from scraper.logging import get_logger
import secrets as _secrets

logger = get_logger("api.seo")

# Where the pre-generated sitemap is written. The scheduler regenerates it after
# each parse when ``SEO_PUBLIC_BASE_URL`` is configured; the endpoint serves this
# file when present and otherwise renders on the fly from the request URL.
SEO_SITEMAP_PATH = os.getenv("SEO_SITEMAP_PATH") or os.path.join(
    tempfile.gettempdir(), "aigenis_sitemap.xml"
)
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import select

from scraper.db import session_scope
from scraper.orm import (
    BondHistoryORM,
    BondORM,
    BondScoreORM,
    CompanyORM,
    PartnerKeyORM,
    PartnerLeadORM,
)
from api.partner.security import generate_api_key

router = APIRouter(tags=["seo"])

SITE_NAME = "Aigenis Bonds"
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").strip()
APP_CTA_LABEL = "Открыть полный разбор в Aigenis Bonds"

# Minimal, dependency-free CSS — readable light theme for crawlers + visitors.
_PAGE_CSS = """
:root{--bg:#f7f8fa;--card:#fff;--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;
--brand:#059669;--brand-d:#047857;--amber:#b45309;--red:#b91c1c;--chip:#ecfdf5}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
background:var(--bg);color:var(--ink);line-height:1.55}
a{color:var(--brand-d);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:960px;margin:0 auto;padding:24px 18px 56px}
header.top{border-bottom:1px solid var(--line);background:var(--card)}
header.top .inner{max-width:960px;margin:0 auto;padding:14px 18px;display:flex;
align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.logo{font-weight:800;font-size:18px;color:var(--ink);display:flex;gap:8px;align-items:center}
.logo .dot{width:10px;height:10px;border-radius:50%;background:var(--brand)}
.cta{background:var(--brand);color:#fff;padding:10px 16px;border-radius:10px;
font-weight:600;white-space:nowrap}
.cta:hover{background:var(--brand-d);text-decoration:none}
h1{font-size:26px;line-height:1.25;margin:8px 0 6px}
h2{font-size:19px;margin:28px 0 10px}
.sub{color:var(--muted);margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:18px;margin:14px 0}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
tr:last-child td{border-bottom:none}
.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;
font-weight:700}
.b-A{background:var(--chip);color:var(--brand-d)}
.b-B{background:#eff6ff;color:#1d4ed8}
.b-C{background:#fef3c7;color:var(--amber)}
.b-D{background:#fee2e2;color:var(--red)}
.b-na{background:#f1f5f9;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.stat .k{color:var(--muted);font-size:12px}
.stat .v{font-size:20px;font-weight:700;margin-top:2px}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 18px}
.filters a{padding:6px 12px;border:1px solid var(--line);border-radius:999px;
background:var(--card);font-size:13px;color:var(--ink)}
.filters a.active{background:var(--brand);color:#fff;border-color:var(--brand)}
.note{font-size:13px;color:var(--muted);margin-top:10px}
.foot{color:var(--muted);font-size:13px;border-top:1px solid var(--line);margin-top:36px;padding-top:18px}
svg.spark{width:100%;height:64px;display:block}
.lead-form{display:grid;gap:12px;max-width:520px}
.lead-form label{display:grid;gap:4px;font-size:14px;color:var(--ink);font-weight:600}
.lead-form input,.lead-form select,.lead-form textarea{font:inherit;padding:9px 11px;
border:1px solid var(--line);border-radius:10px;background:#fff;color:var(--ink)}
.lead-form input:focus,.lead-form select:focus,.lead-form textarea:focus{
outline:2px solid var(--brand);border-color:var(--brand)}
.lead-form button.cta{border:none;cursor:pointer;justify-self:start}
.alarm{color:var(--red);font-weight:600}
"""

_VERDICTS = {
    "A": "Сильный профиль — высокий Score.",
    "B": "Умеренный профиль — средний Score.",
    "C": "Повышенный риск — низкий Score.",
    "D": "Слабый профиль — Score в зоне риска.",
}


def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _fmt_num(v: Any, digits: int = 2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return _esc(v)


def _fmt_date(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return _esc(v)


def _score_tier(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def _abs(request: Request, path: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}{path}"


def _app_links(request: Request) -> tuple[str, str]:
    """Return (web_app_url, bot_deeplink) for CTAs."""
    web = _abs(request, "/?ref=seo")
    bot = f"https://t.me/{BOT_USERNAME}?start=seo" if BOT_USERNAME else web
    return web, bot


def _skeleton(title: str, description: str, body: str, request: Request,
              canonical: str, json_ld: list[str] | None = None) -> HTMLResponse:
    web, bot = _app_links(request)
    ld = "\n".join(json_ld or [])
    ld_block = f"<script type=\"application/ld+json\">{ld}</script>" if ld else ""
    html_doc = f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{_esc(canonical)}">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{_esc(canonical)}">
{ld_block}
<style>{_PAGE_CSS}</style>
</head>
<body>
<header class="top"><div class="inner">
  <div class="logo"><span class="dot"></span>{_esc(SITE_NAME)}</div>
  <a class="cta" href="{_esc(bot)}">{_esc(APP_CTA_LABEL)} →</a>
</div></header>
<div class="wrap">
{body}
<footer class="foot">
  <a href="/partners">Aigenis Bonds для бизнеса: white-label, виджет и API →</a>
  <br>{_esc(SITE_NAME)} — аналитика облигаций фиксированного дохода. Данные предоставлены
  в ознакомительных целях и не являются индивидуальной инвестиционной рекомендацией.
  <br>© {date.today().year} {_esc(SITE_NAME)}.
</footer>
</div>
</body>
</html>"""
    return HTMLResponse(content=html_doc, headers={"Cache-Control": "public, max-age=600"})


def _sparkline(points: list[float]) -> str:
    if len(points) < 2:
        return ""
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    w, h = 600.0, 64.0
    coords = []
    for i, p in enumerate(points):
        x = (i / (len(points) - 1)) * w
        y = h - ((p - lo) / span) * (h - 6) - 3
        coords.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(coords)
    return (
        f'<svg class="spark" viewBox="0 0 {w:.0f} {h:.0f}" preserveAspectRatio="none" '
        f'aria-hidden="true"><polyline points="{poly}" fill="none" stroke="#059669" '
        f'stroke-width="2"/></svg>'
    )


@router.get("/bonds", response_class=HTMLResponse)
async def seo_bonds(request: Request, currency: str | None = None, sort: str = "score"):
    cur = currency.upper() if currency else None
    async with session_scope() as session:
        score_stmt = select(BondScoreORM).order_by(BondScoreORM.score.desc())
        scores = list((await session.execute(score_stmt)).scalars().all())
        ids = [s.internal_id for s in scores]
        if not ids:
            return _skeleton(
                f"Облигации — рейтинг {SITE_NAME}",
                "Аналитика и рейтинг облигаций фиксированного дохода.",
                "<h1>Облигации</h1><p class='sub'>Данные пока не загружены.</p>",
                request, _abs(request, "/bonds"),
            )
        bond_stmt = select(BondORM).where(BondORM.internal_id.in_(ids))
        if cur:
            bond_stmt = bond_stmt.where(BondORM.currency == cur)
        bonds = {b.internal_id: b for b in (await session.execute(bond_stmt)).scalars().all()}
        score_map = {s.internal_id: float(s.score) for s in scores}

    # Iterate the (currency-filtered) query result directly; `ids` may contain
    # bonds excluded by the currency filter, so don't index by `ids`.
    rows = list(bonds.values())
    # Sort: by score (default) or by yield desc.
    if sort == "ytm":
        rows.sort(key=lambda b: float(b.yield_to_maturity) if b.yield_to_maturity is not None else -1,
                  reverse=True)
    else:
        rows.sort(key=lambda b: score_map.get(b.internal_id, -1), reverse=True)

    cur_filter = cur or "Все"
    title = f"Облигации {_esc(cur_filter)}: рейтинг по доходности и Score | {SITE_NAME}"
    desc = (f"Рейтинг облигаций ({cur_filter}) по доходности к погашению и Score Aigenis. "
            f"Топ-{min(len(rows), 50)} выпусков с ценой, купоном и погашением.")

    # Currency filter chips from available data.
    cur_counts: dict[str, int] = {}
    for b in bonds.values():
        cur_counts[b.currency] = cur_counts.get(b.currency, 0) + 1
    chips = ['<a class="%s" href="/bonds%s">Все</a>' % (
        "active" if not cur else "", "?currency=" if cur else "")]
    for c in sorted(cur_counts):
        q = f"?currency={c}"
        active = "active" if cur == c else ""
        chips.append(f'<a class="{active}" href="/bonds{q}">{_esc(c)} ({cur_counts[c]})</a>')

    body = f"""<h1>Рейтинг облигаций</h1>
<p class="sub">Топ выпусков по Score Aigenis и доходности к погашению. Клик — на страницу облигации.</p>
<div class="filters">{' '.join(chips)}</div>
<div class="filters">
  <a class="{'' if sort!='ytm' else 'active'}" href="/bonds{'?currency='+cur if cur else ''}">По Score</a>
  <a class="{('active' if sort=='ytm' else '')}" href="/bonds?sort=ytm{'&currency='+cur if cur else ''}">По доходности</a>
</div>
<div class="card" style="padding:6px 4px">
<table>
<thead><tr><th>Облигация</th><th>Валюта</th><th>YTM, %</th><th>Цена</th>
<th>Купон, %</th><th>Погашение</th><th>Score</th></tr></thead>
<tbody>"""
    for b in rows[:50]:
        sc = score_map.get(b.internal_id)
        tier = _score_tier(sc)
        badge = (f'<span class="badge b-{tier}">{tier} · {_fmt_num(sc,1)}</span>'
                 if tier else '<span class="badge b-na">—</span>')
        body += (
            f"<tr><td><a href=\"/bonds/{_esc(b.internal_id)}\">{_esc(b.name)}</a>"
            f"<br><span class='num' style='color:var(--muted);font-size:12px'>{_esc(b.internal_id)}</span></td>"
            f"<td>{_esc(b.currency)}</td>"
            f"<td class='num'>{_fmt_num(b.yield_to_maturity)}</td>"
            f"<td class='num'>{_fmt_num(b.price)}</td>"
            f"<td class='num'>{_fmt_num(b.coupon_rate)}</td>"
            f"<td class='num'>{_fmt_date(b.maturity_date)}</td>"
            f"<td>{badge}</td></tr>"
        )
    body += "</tbody></table></div>"
    body += f'<p class="note">Показано {min(len(rows),50)} из {len(rows)} облигаций' + \
            (f' в валюте {_esc(cur)}' if cur else '') + '.</p>'

    json_ld = [json.dumps({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": desc,
        "url": _abs(request, "/bonds"),
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME,
                     "url": _abs(request, "/")},
    }, ensure_ascii=False)]
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
    async with session_scope() as session:
        bond = (await session.execute(
            select(BondORM).where(BondORM.internal_id == internal_id)
        )).scalar_one_or_none()
        if bond is None:
            not_found = (
                "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
                f"<title>Облигация не найдена | {_esc(SITE_NAME)}</title></head>"
                "<body style='font-family:system-ui;max-width:640px;margin:80px auto;padding:0 18px'>"
                f"<h1>Облигация {_esc(internal_id)} не найдена</h1>"
                f"<p><a href='{_esc(_abs(request, '/bonds'))}'>← Рейтинг облигаций</a></p></body></html>"
            )
            return HTMLResponse(content=not_found, status_code=404)
        score_row = (await session.execute(
            select(BondScoreORM).where(BondScoreORM.internal_id == internal_id)
        )).scalar_one_or_none()
        score = float(score_row.score) if score_row and score_row.score is not None else None
        tier = score_row.tier if score_row else None
        if not tier:
            tier = _score_tier(score)
        company = None
        if bond.issuer:
            company = (await session.execute(
                select(CompanyORM).where(CompanyORM.issuer == bond.issuer)
            )).scalar_one_or_none()
        history = list((await session.execute(
            select(BondHistoryORM)
            .where(BondHistoryORM.internal_id == internal_id)
            .order_by(BondHistoryORM.date.desc())
            .limit(60)
        )).scalars().all())

    sc = score
    tier_badge = (f'<span class="badge b-{tier}">{tier} · {_fmt_num(sc,1)}</span>'
                  if tier else '<span class="badge b-na">—</span>')
    verdict = _VERDICTS.get(tier, "Профиль требует анализа.")
    web, bot = _app_links(request)

    spark = _sparkline([float(h.price) for h in history if h.price is not None][::-1])

    facts = f"""<div class="grid">
  <div class="stat"><div class="k">Валюта</div><div class="v">{_esc(bond.currency)}</div></div>
  <div class="stat"><div class="k">Цена</div><div class="v num">{_fmt_num(bond.price)}</div></div>
  <div class="stat"><div class="k">Доходность к погашению</div><div class="v num">{_fmt_num(bond.yield_to_maturity)}%</div></div>
  <div class="stat"><div class="k">Купон</div><div class="v num">{_fmt_num(bond.coupon_rate)}%</div></div>
  <div class="stat"><div class="k">Частота купона</div><div class="v num">{bond.coupon_frequency if bond.coupon_frequency else '—'}</div></div>
  <div class="stat"><div class="k">Погашение</div><div class="v num" style="font-size:16px">{_fmt_date(bond.maturity_date)}</div></div>
</div>"""

    issuer_line = ""
    if company and company.name:
        issuer_line = (f"Эмитент: <b>{_esc(company.name)}</b>"
                       + (f" · {_esc(company.sector)}" if company.sector else "")
                       + (f"<br><span class='note'>{_esc(company.description)}</span>" if company.description else ""))

    body = f"""<h1>{_esc(bond.name)}</h1>
<p class="sub">ID: <span class="num">{_esc(bond.internal_id)}</span> · Статус: {_esc(bond.status)}</p>
<div class="card">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <div>Score Aigenis: {tier_badge}</div>
    <div style="color:var(--muted)">{_esc(verdict)}</div>
  </div>
  {facts}
  {('<h2>Динамика цены</h2>' + spark) if spark else ''}
  {('<p class="note">' + issuer_line + '</p>' if issuer_line else '')}
</div>
<div class="card" style="border-color:var(--brand);background:#f0fdf9">
  <h2 style="margin-top:0">Полный разбор — бесплатно</h2>
  <p>Что влияет на Score, ML-прогноз, стресс-тест и рекомендация «стоит ли покупать» —
  в приложении {SITE_NAME}. Доступен 7-дневный пробный Pro.</p>
  <p style="margin-bottom:0"><a class="cta" href="{_esc(bot)}">Открыть в Telegram-боте →</a>
  &nbsp; <a href="{_esc(web)}">Открыть в веб-приложении →</a></p>
</div>
<p class="note">Данные обновлены: {_fmt_date(bond.fetched_at)}. Источник — публичные и партнёрские
рыночные данные. Не является индивидуальной инвестиционной рекомендацией.</p>
<p><a href="{_esc(_abs(request, '/bonds'))}">← Рейтинг всех облигаций</a></p>"""

    title = f"{_esc(bond.name)} ({_esc(bond.internal_id)}): доходность, цена, Score | {SITE_NAME}"
    desc = (f"Облигация {_esc(bond.name)}: доходность к погашению "
            f"{_fmt_num(bond.yield_to_maturity)}%, цена {_fmt_num(bond.price)}, "
            f"купон {_fmt_num(bond.coupon_rate)}%, погашение {_fmt_date(bond.maturity_date)}. "
            f"Score Aigenis {_fmt_num(sc,1)} (тир {tier or '—'}).")

    json_ld = [json.dumps({
        "@context": "https://schema.org",
        "@type": "Product",
        "name": bond.name,
        "category": "Облигация фиксированного дохода",
        "description": desc,
        "url": _abs(request, f"/bonds/{bond.internal_id}"),
        "brand": {"@type": "Brand", "name": (company.name if company else (bond.issuer or SITE_NAME))},
        "offers": {"@type": "Offer", "priceCurrency": bond.currency,
                   "price": _fmt_num(bond.price, 2), "availability": "https://schema.org/InStock"},
    }, ensure_ascii=False)]
    json_ld.append(json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Облигации",
             "item": _abs(request, "/bonds")},
            {"@type": "ListItem", "position": 2, "name": bond.name,
             "item": _abs(request, f"/bonds/{bond.internal_id}")},
        ],
    }, ensure_ascii=False))
    return _skeleton(title, desc, body, request, _abs(request, f"/bonds/{bond.internal_id}"), json_ld)


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
        for iid, fetched in rows:
            lastmod = fetched.isoformat() if fetched else date.today().isoformat()
            urls.append(f"{base}/bonds/{_esc(iid)}")
    except Exception as exc:
        logger.warning("sitemap_bonds_query_failed", error=str(exc))
    return urls


def _sitemap_xml(urls: list[str]) -> str:
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        body.append(f"  <url><loc>{u}</loc></url>")
    body.append("</urlset>")
    return "\n".join(body)


@router.get("/sitemap.xml", response_class=PlainTextResponse)
async def seo_sitemap(request: Request):
    # Serve a pre-generated file if present (regenerated by the scheduler after
    # each parse); otherwise render on the fly from the request's base URL so the
    # canonical domain is always correct.
    if os.path.exists(SEO_SITEMAP_PATH) and os.path.getsize(SEO_SITEMAP_PATH) > 0:
        try:
            with open(SEO_SITEMAP_PATH, "r", encoding="utf-8") as fh:
                xml = fh.read()
            return PlainTextResponse(xml, media_type="application/xml",
                                     headers={"Cache-Control": "public, max-age=600"})
        except OSError:
            pass
    urls = await _sitemap_urls(str(request.base_url))
    return PlainTextResponse(_sitemap_xml(urls), media_type="application/xml",
                             headers={"Cache-Control": "public, max-age=600"})


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
    try:
        os.makedirs(os.path.dirname(SEO_SITEMAP_PATH) or ".", exist_ok=True)
        with open(SEO_SITEMAP_PATH, "w", encoding="utf-8") as fh:
            fh.write(xml)
    except OSError as exc:
        logger.warning("seo_sitemap_write_failed", error=str(exc))
        return None
    logger.info("seo_sitemap_regenerated", urls=len(urls), path=SEO_SITEMAP_PATH)
    return xml


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


@router.get("/partners", response_class=HTMLResponse)
async def seo_partners(request: Request):
    """Public B2B / white-label acquisition page (see docs/sales/cmo_audit.md §8).

    The product already ships the B2B plumbing (Partner API keys, webhooks,
    read-only analytics, affiliate referrals, embeddable widget, demo mode) but
    had no public surface to convert brokers / fintech / EdTech leads. This page
    is that surface: it explains the offer and funnels leads to the bot.
    """
    web, bot = _app_links(request)
    partner_bot = (f"https://t.me/{BOT_USERNAME}?start=partner"
                   if BOT_USERNAME else web)
    title = f"{SITE_NAME} для бизнеса: white-label аналитика облигаций | B2B"
    desc = ("Встройте аналитику облигаций (скоринг, Desk, ML) в своё приложение "
            "или сайт: виджет, Bond API, white-label и партнёрская программа с %.")

    features = [
        ("Виджет за 1 строку", "iframe «Топ облигаций» на вашем сайте или в блоге. "
         "Бесплатно, с вашим дизайном, ведёт трафик в вашу воронку."),
        ("Bond API", "Программный доступ к скорингу 0–100, Desk-аналитике "
         "(duration, кривая, RV, carry, РЕПО, стресс-тесты) и ML-рекомендациям."),
        ("White-label", "Аналитика под вашим брендом — для брокеров, агрегаторов "
         "котировок и финтех-приложений. Демо-режим для быстрого показа."),
        ("Партнёрская программа", "Affiliate: % с приведённых подписок через "
         "реферальный код. Подходит блогерам и каналам по инвестициям."),
    ]
    cards = "".join(
        f'<div class="card"><h2 style="margin-top:0">{_esc(t)}</h2>'
        f'<p class="sub">{_esc(d)}</p></div>'
        for t, d in features
    )

    body = f"""<h1>{SITE_NAME} для бизнеса</h1>
<p class="sub">Аналитика облигаций фиксированного дохода «под ключ»: встройте за день
через виджет или API и монетизируйте свой трафик.</p>
{cards}
<h2>Кому подходит</h2>
<ul>
  <li><b>Брокеры / агрегаторы котировок</b> — white-label аналитика на вашем бренде.</li>
  <li><b>Финтех-приложения</b> — виджет «Топ облигаций» и Bond API.</li>
  <li><b>EdTech по инвестициям</b> — готовая учебная платформа с реальными данными.</li>
  <li><b>Финансовые медиа и блогеры</b> — партнёрская программа с % с подписок.</li>
</ul>
<div class="card" style="border-color:var(--brand);background:#f0fdf9">
  <h2 style="margin-top:0">Оставить заявку на B2B / white-label</h2>
  <p>Заполните форму — мы пришлём API-ключ, виджет и условия партнёрки в Telegram.
  Или сразу <a href="{_esc(partner_bot)}">напишите боту про B2B →</a>.</p>
  <form method="post" action="/partners/request" class="lead-form">
    <label>Имя *<input name="name" required maxlength="128" placeholder="Как к вам обращаться"></label>
    <label>Email<input name="email" type="email" maxlength="256" placeholder="you@company.com"></label>
    <label>Telegram (без @)<input name="telegram" maxlength="64" placeholder="username"></label>
    <label>Компания<input name="company" maxlength="128" placeholder="Название компании"></label>
    <label>Что интересно
      <select name="interest">
        <option value="white-label">White-label</option>
        <option value="api">Bond API</option>
        <option value="widget">Виджет</option>
        <option value="affiliate">Партнёрская программа</option>
        <option value="license">Лицензия / покупка</option>
      </select>
    </label>
    <label>Сообщение<textarea name="message" maxlength="2000" rows="3" placeholder="Кратко о задаче"></textarea></label>
    <button class="cta" type="submit">Отправить заявку</button>
    <span class="note">Или сразу <a href="{_esc(partner_bot)}">напишите боту →</a>
    · <a href="/bonds">Посмотреть публичные данные →</a></span>
  </form>
</div>
<p class="note">Готовые материалы для buyer/партнёра — <code>docs/sales/one_pager.md</code>
и <code>docs/sales/teaser.md</code>.</p>"""

    json_ld = [json.dumps({
        "@context": "https://schema.org",
        "@type": "Service",
        "name": f"{SITE_NAME} для бизнеса",
        "description": desc,
        "url": _abs(request, "/partners"),
        "provider": {"@type": "Organization", "name": SITE_NAME},
        "areaServed": "СНГ",
        "offers": {"@type": "Offer", "priceCurrency": "BYN",
                   "price": "0", "availability": "https://schema.org/InStock"},
    }, ensure_ascii=False)]
    body += (
        '<p class="note">Полезные материалы: '
        '<a href="/guides/kak-vybrat-obligaciyu">Как выбрать облигацию</a> · '
        '<a href="/guides/obligacii-vs-depozit">Облигации vs депозит</a> · '
        '<a href="/bonds">Рейтинг облигаций →</a></p>'
    )
    return _skeleton(title, desc, body, request, _abs(request, "/partners"), json_ld)


async def _issue_partner_key(session, lead: PartnerLeadORM) -> tuple[str, PartnerKeyORM]:
    """Create a live Partner API key for the lead (self-serve onboarding).

    Returns ``(raw_key, key)`` — the raw key is shown only once (to the lead and
    the admin alert). Mirrors ``api.partner.router.create_partner_key``.
    """
    raw, key_hash = generate_api_key()
    code = _secrets.token_urlsafe(8)[:10]
    key = PartnerKeyORM(
        name=(lead.company or lead.name)[:128],
        owner_user_id=None,
        key_hash=key_hash,
        tier="partner",
        rate_limit=120,
        active=True,
        referral_code=code,
    )
    session.add(key)
    await session.flush()
    return raw, key


async def _notify_partner_lead(lead: PartnerLeadORM, issued: tuple[str, PartnerKeyORM] | None = None) -> None:
    """Best-effort Telegram alert (admin) + DM to the lead with the issued key."""
    settings = get_settings()
    tg = settings.telegram
    if not tg.bot_token:
        return
    raw_key, key = issued if issued else (None, None)

    admin_chat = (tg.alert_chat_id or (str(tg.admin_ids[0]) if tg.admin_ids else "")).strip()
    if admin_chat:
        text = (
            f"🤝 <b>Новая B2B-заявка + ключ выдан</b> (#{lead.id})\n"
            f"Имя: {html.escape(lead.name)}\n"
            f"Компания: {html.escape(lead.company or '—')}\n"
            f"Email: {html.escape(lead.email or '—')}\n"
            f"Telegram: @{html.escape(lead.telegram or '—')}\n"
            f"Интерес: {html.escape(lead.interest or '—')}\n"
            f"Ключ: <code>{html.escape(raw_key or '—')}</code>\n"
            f"Реф. код: <code>{html.escape(key.referral_code if key else '—')}</code>"
        )
        try:
            from telegram import Bot

            await Bot(token=tg.bot_token).send_message(
                chat_id=admin_chat, text=text, parse_mode="HTML"
            )
        except Exception as exc:
            logger.warning("partner_lead_admin_notify_failed", id=lead.id, error=str(exc))

    # DM the key to the lead directly (self-serve: they get instant access).
    if lead.telegram and raw_key and key:
        dm = (
            f"✅ <b>Ваш партнёрский доступ {SITE_NAME} готов!</b>\n\n"
            f"API-ключ (покажем один раз):\n<code>{html.escape(raw_key)}</code>\n\n"
            f"Реферальная ссылка (affiliate %):\n"
            f"<code>?referral_code={html.escape(key.referral_code)}</code>\n\n"
            f"Виджет и документацию — в личном кабинете / API."
        )
        try:
            from telegram import Bot

            await Bot(token=tg.bot_token).send_message(
                chat_id="@" + lead.telegram.lstrip("@"), text=dm, parse_mode="HTML"
            )
        except Exception as exc:
            logger.warning("partner_lead_dm_failed", id=lead.id, error=str(exc))


def _lead_thanks_page(request: Request, issued: tuple[str, PartnerKeyORM] | None = None) -> HTMLResponse:
    if issued:
        raw_key, key = issued
        base = _abs(request, "/").rstrip("/")
        widget = f"{base}/widget/embed.js"
        ref_link = f"{base}/?referral_code={html.escape(key.referral_code)}"
        body = (
            "<h1>Доступ готов ✅</h1>"
            "<p class='sub'>Спасибо! Ваш партнёрский ключ создан — используйте его сразу. "
            "Ключ показан один раз, сохраните его.</p>"
            "<div class='card' style='border-color:var(--brand);background:#f0fdf9'>"
            "<h2 style='margin-top:0'>Ваш Partner API-ключ</h2>"
            f"<pre style='overflow:auto'><code>{html.escape(raw_key)}</code></pre>"
            "<h3>Виджет «Топ облигаций» (вставьте 1 строку)</h3>"
            f"<pre style='overflow:auto'><code>&lt;script src=\"{html.escape(widget)}\"&gt;&lt;/script&gt;</code></pre>"
            "<h3>Реферальная ссылка (affiliate % с подписок)</h3>"
            f"<pre style='overflow:auto'><code>{ref_link}</code></pre>"
            "<h3>API</h3>"
            f"<p class='note'>Заголовок <code>X-Aigenis-Api-Key: {html.escape(raw_key)}</code> → "
            f"<code>{html.escape(base)}/api/v1/partner/bonds</code></p>"
            "</div>"
            "<p><a class='cta' href='/bonds'>Открыть публичные данные →</a></p>"
        )
    else:
        body = (
            "<h1>Заявка отправлена ✅</h1>"
            "<p class='sub'>Спасибо! Мы свяжемся с вами в Telegram с API-ключом, "
            "виджетом и условиями партнёрки.</p>"
            "<p><a class='cta' href='/bonds'>Посмотреть публичные данные →</a></p>"
        )
    return _skeleton("Партнёрский доступ | " + SITE_NAME, "", body, request,
                     _abs(request, "/partners"))


def _lead_error_page(request: Request, error: str) -> HTMLResponse:
    body = (
        "<h1>Не получилось отправить</h1>"
        f"<p class='alarm'>{html.escape(error)}</p>"
        "<p><a class='cta' href='/partners'>← Вернуться к форме</a></p>"
    )
    resp = _skeleton("Ошибка заявки | " + SITE_NAME, "", body, request,
                     _abs(request, "/partners"))
    resp.status_code = 400
    return resp


@router.post("/partners/request", response_class=HTMLResponse)
async def seo_partners_request(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    telegram: str = Form(""),
    company: str = Form(""),
    interest: str = Form(""),
    message: str = Form(""),
):
    """Capture a B2B lead from the public /partners page and self-serve a key."""
    name = (name or "").strip()
    email = (email or "").strip() or None
    telegram = ((telegram or "").strip().lstrip("@")) or None
    company = (company or "").strip() or None
    interest = (interest or "").strip() or None
    message = (message or "").strip() or None

    if not name:
        return _lead_error_page(request, "Укажите имя.")
    if not email and not telegram:
        return _lead_error_page(request, "Укажите email или Telegram для связи.")

    issued: tuple[str, PartnerKeyORM] | None = None
    async with session_scope() as session:
        lead = PartnerLeadORM(
            name=name[:128],
            email=email,
            telegram=telegram,
            company=company,
            interest=interest,
            message=message,
        )
        session.add(lead)
        await session.flush()
        lead_id = lead.id
        # Self-serve onboarding: issue a live partner key immediately.
        raw_key, key = await _issue_partner_key(session, lead)
        lead.partner_key_id = key.id
        await session.flush()
        issued = (raw_key, key)
        try:
            await _notify_partner_lead(lead, issued)
        except Exception as exc:
            logger.warning("partner_lead_notify_failed", id=lead_id, error=str(exc))
    logger.info("partner_lead_created", id=lead_id, interest=interest,
                partner_key_id=lead.partner_key_id)
    return _lead_thanks_page(request, issued)


# ---------------------------------------------------------------------------
# Educational guides (top-of-funnel organic surface, audit §2 long-tail).
# Each guide is its own indexable page with internal links to /bonds + /partners.
# ---------------------------------------------------------------------------

_GUIDES: list[dict] = [
    {
        "slug": "kak-vybrat-obligaciyu",
        "title": "Как выбрать облигацию в 2026: чек-лист инвестора",
        "description": "Пошаговый разбор: доходность к погашению, риск эмитента, "
                       "дюрация, налоги и ликвидность. С чем сравнивать и на что "
                       "смотреть до покупки.",
        "updated": "2026-07-01",
        "body": """
<h2>1. Доходность к погашению (YTM)</h2>
<p>Смотрите на <b>YTM</b>, а не на купонную ставку. YTM уже учитывает цену покупки,
купоны и номинал — это ваша реальная доходность, если держать до погашения.
Актуальный <a href="/bonds">рейтинг облигаций по доходности</a> виден на отдельной странице.</p>
<h2>2. Риск эмитента</h2>
<p>Государственные и квазигосударственные — надёжнее корпоративных. Для корпоратов
смотрите отрасль, долговую нагрузку и то, есть ли у эмитента история выплат.
Наш <a href="/bonds">Score 0–100</a> сжимает эти факторы в одну оценку риска/доходности.</p>
<h2>3. Дюрация и срок</h2>
<p>Чем длиннее срок, тем выше процентный риск: при росте ставок длинные облигации
дешевеют сильнее. <a href="/guides/duration-i-repo-prosto">Что такое Duration — разбор простыми словами →</a></p>
<h2>4. Ликвидность и налоги</h2>
<p>Проверьте, торгуется ли выпуск реальным объёмом, а не только на бумаге. Учитывайте
НДФЛ с купонов/дохода — он влияет на чистую доходность.</p>
<h2>5. Диверсификация</h2>
<p>Не держите всё в одном эмитенте и валюте. Распределяйте между RUB/USD/EUR и
металлами. <a href="/guides/obligacii-vs-depozit">Облигации против депозита →</a></p>
<p class="note">Готовый шорт-лист с Score и YTM — на странице <a href="/bonds">рейтинга облигаций</a>.
Для брокеров и финтеха доступен <a href="/partners">white-label и Bond API</a>.</p>
""",
    },
    {
        "slug": "duration-i-repo-prosto",
        "title": "Duration и РЕПО простыми словами",
        "description": "Что такое дюрация облигации, почему она важна при изменении "
                       "ставок, и как работает сделка РЕПО с облигациями.",
        "updated": "2026-07-01",
        "body": """
<h2>Что такое Duration</h2>
<p><b>Дюрация</b> — мера чувствительности цены облигации к процентным ставкам.
Грубо: если ставка вырастет на 1%, цена облигации упадёт примерно на значение
дюрации (в годах). Чем дюрация выше, тем больше ценовой риск при росте ставок
и тем больше потенциал роста цены при их снижении.</p>
<h2>Зачем это инвестору</h2>
<p>Если ждёте снижения ставок — длинные облигации (высокая дюрация) дадут больше
капитального роста. Если ставки растут — короткие безопаснее. Наша Desk-аналитика
считает duration по портфелю и по каждой бумаге отдельно.</p>
<h2>Что такое РЕПО</h2>
<p><b>РЕПО</b> — сделка «облигация в залог под деньги» с обязательством выкупа.
Кредитор получает облигацию и процент (ставка РЕПО), заёмщик — ликвидность,
оставляя бумагу у себя. Для трейдера это способ плеча или краткосрочного фондирования.</p>
<h2>Связь с выбором</h2>
<p>Дюрация помогает балансировать портфель под свой взгляд на ставку, а РЕПО —
управлять ликвидностью. Начните с <a href="/guides/kak-vybrat-obligaciyu">чека-листа выбора облигации →</a>
и актуального <a href="/bonds">рейтинга по доходности</a>.</p>
<p class="note">Desk-инструменты (Duration, РЕПО, Carry, стресс-тесты) доступны по
<a href="/partners">B2B/white-label</a> и в тарифах Pro/Enterprise.</p>
""",
    },
    {
        "slug": "obligacii-vs-depozit",
        "title": "Облигации vs депозит: что выгоднее в 2026",
        "description": "Сравниваем доходность, риски, сроки и налоги облигаций и "
                       "банковского вклада — и когда что имеет смысл.",
        "updated": "2026-07-01",
        "body": """
<h2>Доходность</h2>
<p>Качественные корпоративные и гособлигации часто дают доходность выше, чем
средний депозит той же валюты/срока, особенно на горизонте 1–3 лет.
Сравните на <a href="/bonds">странице рейтинга облигаций</a> (колонка YTM).</p>
<h2>Риск</h2>
<p>Депозит застрахован (в пределах лимита ФГВ/аналога), облигации — нет, но риск
зависит от эмитента. Гособлигации и бумаги надёжных эмитентов близки к депозиту
по надёжности. Наш <a href="/bonds">Score</a> помогает отсеять слабых эмитентов.</p>
<h2>Ликвидность</h2>
<p>Депозит обычно нельзя снять досрочно без потери %, облигацию можно продать
на рынке (цену определит спрос). Дюрация и рыночная цена дадут просадку при
росте ставок — см. <a href="/guides/duration-i-repo-prosto">разбор дюрации →</a>.</p>
<h2>Налоги</h2>
<p>И с купонов, и с депозитных процентов берётся НДФЛ. Считайте чистую доходность
после налога, а не «на витрине».</p>
<h2>Итог</h2>
<p>Облигации — гибче и часто доходнее при том же горизонте, депозит — проще и
застрахован. Разумно комбинировать. Начните с <a href="/guides/kak-vybrat-obligaciyu">чека-листа выбора →</a>.</p>
<p class="note">Для встраивания рейтинга облигаций на свой сайт — <a href="/partners">виджет и API</a>.</p>
""",
    },
]


@router.get("/guides", response_class=HTMLResponse)
async def seo_guides_index(request: Request):
    title = f"Гайды по облигациям | {SITE_NAME}"
    desc = ("Бесплатные разборы: как выбрать облигацию, что такое Duration и РЕПО, "
            "облигации против депозита. С внутренними ссылками на живой рейтинг.")
    items = "".join(
        f'<div class="card"><h2 style="margin-top:0"><a href="/guides/{_esc(g["slug"])}">'
        f'{_esc(g["title"])}</a></h2><p class="sub">{_esc(g["description"])}</p></div>'
        for g in _GUIDES
    )
    body = (
        f"<h1>Гайды по облигациям</h1>"
        f"<p class='sub'>Короткие практические разборы по фиксированному доходу. "
        f"Каждый — с переходом к живому <a href='/bonds'>рейтингу облигаций</a>.</p>"
        f"{items}"
        f"<p class='note'>Для бизнеса — white-label, виджет и Bond API: "
        f"<a href='/partners'>Aigenis Bonds для бизнеса →</a>.</p>"
    )
    json_ld = [json.dumps({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": desc,
        "url": _abs(request, "/guides"),
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": _abs(request, "/")},
    }, ensure_ascii=False)]
    return _skeleton(title, desc, body, request, _abs(request, "/guides"), json_ld)


@router.get("/guides/{slug}", response_class=HTMLResponse)
async def seo_guide_detail(request: Request, slug: str):
    guide = next((g for g in _GUIDES if g["slug"] == slug), None)
    if guide is None:
        not_found = (
            "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
            f"<title>Гайд не найден | {_esc(SITE_NAME)}</title></head>"
            "<body style='font-family:system-ui;max-width:640px;margin:80px auto;padding:0 18px'>"
            f"<h1>Гайд не найден</h1>"
            f"<p><a href='{_esc(_abs(request, '/guides'))}'>← Все гайды</a></p></body></html>"
        )
        return HTMLResponse(content=not_found, status_code=404)
    title = guide["title"]
    desc = guide["description"]
    body = (
        f"<h1>{_esc(title)}</h1>"
        f"<p class='sub'>{_esc(desc)}</p>"
        f"{guide['body']}"
        f"<p class='note'>Смотрите живой <a href='/bonds'>рейтинг облигаций</a> · "
        f"<a href='/partners'>Aigenis Bonds для бизнеса →</a> · "
        f"<a href='/guides'>Все гайды →</a></p>"
    )
    json_ld = [
        json.dumps({
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "description": desc,
            "dateModified": guide["updated"],
            "publisher": {"@type": "Organization", "name": SITE_NAME},
            "mainEntityOfPage": {"@type": "WebPage", "url": _abs(request, f"/guides/{slug}")},
        }, ensure_ascii=False),
        json.dumps({
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Гайды",
                 "item": _abs(request, "/guides")},
                {"@type": "ListItem", "position": 2, "name": title,
                 "item": _abs(request, f"/guides/{slug}")},
            ],
        }, ensure_ascii=False),
    ]
    return _skeleton(title, desc, body, request, _abs(request, f"/guides/{slug}"), json_ld)


# ---------------------------------------------------------------------------
# Public bond calculator (YTM / duration / price) — high-intent long-tail SEO.
# Captures "калькулятор облигаций", "расчет доходности облигации", "duration облигаций".
# Server-rendered, no DB dependency.
# ---------------------------------------------------------------------------

def _calc_ytm(price: float, face: float, coupon: float, freq: int, years: float) -> float | None:
    """Approximate YTM via Newton-Raphson. Returns None if fails."""
    if price <= 0 or face <= 0 or years <= 0 or freq <= 0:
        return None
    # Coupon payment per period
    c = face * coupon / 100.0 / freq
    n = int(years * freq)
    if n <= 0:
        return None
    # Initial guess: current yield
    y = (coupon / 100.0) * (face / price)
    for _ in range(50):
        # Price as function of y
        pv_coupons = 0.0
        for i in range(1, n + 1):
            pv_coupons += c / (1 + y / freq) ** i
        pv_face = face / (1 + y / freq) ** n
        px = pv_coupons + pv_face
        # Derivative dP/dy
        dpx = 0.0
        for i in range(1, n + 1):
            dpx -= i * c / (freq * (1 + y / freq) ** (i + 1))
        dpx -= n * face / (freq * (1 + y / freq) ** (n + 1))
        if dpx == 0:
            break
        diff = px - price
        if abs(diff) < 1e-6:
            return y * 100.0
        y -= diff / dpx
        if y <= -0.99:
            return None
    return y * 100.0 if y > -0.99 else None


def _calc_price(face: float, coupon: float, freq: int, years: float, ytm: float) -> float | None:
    """Clean price from YTM."""
    if face <= 0 or years <= 0 or freq <= 0:
        return None
    c = face * coupon / 100.0 / freq
    n = int(years * freq)
    y = ytm / 100.0
    if y <= -0.99:
        return None
    pv_coupons = 0.0
    for i in range(1, n + 1):
        pv_coupons += c / (1 + y / freq) ** i
    pv_face = face / (1 + y / freq) ** n
    return pv_coupons + pv_face


def _calc_macaulay_duration(price: float, face: float, coupon: float, freq: int, years: float) -> float | None:
    """Macaulay duration in years. Returns None if fails."""
    if price <= 0 or face <= 0 or years <= 0 or freq <= 0:
        return None
    c = face * coupon / 100.0 / freq
    n = int(years * freq)
    if n <= 0:
        return None
    y = None
    # Solve for y using approximate YTM
    ytm = _calc_ytm(price, face, coupon, freq, years)
    if ytm is None:
        return None
    y = ytm / 100.0
    # Weighted average time to cashflows
    num = 0.0
    denom = 0.0
    for i in range(1, n + 1):
        t = i / freq
        pv = c / (1 + y / freq) ** i
        num += t * pv
        denom += pv
    # Face
    t = years
    pv = face / (1 + y / freq) ** n
    num += t * pv
    denom += pv
    if denom == 0:
        return None
    return num / denom


def _calc_modified_duration(mac_duration: float | None, ytm: float | None, freq: int) -> float | None:
    if mac_duration is None or ytm is None or freq <= 0:
        return None
    return mac_duration / (1 + (ytm / 100.0) / freq)


@router.get("/calculator", response_class=HTMLResponse)
async def seo_calculator(request: Request):
    """Bond calculator: YTM from price, or price from YTM, plus duration."""
    # Parse query params for pre-filled form
    q = request.query_params
    price = q.get("price")
    face = q.get("face", "1000")
    coupon = q.get("coupon")
    freq = q.get("freq", "2")
    maturity = q.get("maturity")  # ISO date or years
    calc_mode = q.get("mode", "ytm")  # "ytm" or "price"

    # Defaults / parsed
    def _f(v, default=None):
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    price_v = _f(price)
    face_v = _f(face, 1000.0)
    coupon_v = _f(coupon)
    freq_v = int(_f(freq, 2) or 2)
    if freq_v <= 0:
        freq_v = 2

    years_v = None
    if maturity:
        try:
            # Try ISO date
            mat_date = date.fromisoformat(maturity)
            years_v = max(0.0, (mat_date - date.today()).days / 365.0)
        except ValueError:
            years_v = _f(maturity)

    # Calculate
    ytm_v = None
    price_calc_v = None
    mac_dur = None
    mod_dur = None
    error = None

    if calc_mode == "ytm":
        if price_v is not None and coupon_v is not None and years_v is not None:
            ytm_v = _calc_ytm(price_v, face_v, coupon_v, freq_v, years_v)
            if ytm_v is not None:
                mac_dur = _calc_macaulay_duration(price_v, face_v, coupon_v, freq_v, years_v)
                mod_dur = _calc_modified_duration(mac_dur, ytm_v, freq_v)
            else:
                error = "Не удалось рассчитать YTM — проверьте ввод."
    else:  # price from YTM
        ytm_in = _f(q.get("ytm"))
        if ytm_in is not None and coupon_v is not None and years_v is not None:
            price_calc_v = _calc_price(face_v, coupon_v, freq_v, years_v, ytm_in)
            if price_calc_v is not None:
                mac_dur = _calc_macaulay_duration(price_calc_v, face_v, coupon_v, freq_v, years_v)
                mod_dur = _calc_modified_duration(mac_dur, ytm_in, freq_v)
            else:
                error = "Не удалось рассчитать цену — проверьте YTM."
        else:
            error = "Для расчёта цены укажите YTM, купон и срок."

    # Build form
    form_html = f"""
    <form method="get" action="/calculator" class="lead-form" style="max-width:600px">
      <label>Режим
        <select name="mode">
          <option value="ytm" {"selected" if calc_mode=="ytm" else ""}>YTM из цены</option>
          <option value="price" {"selected" if calc_mode=="price" else ""}>Цена из YTM</option>
        </select>
      </label>
      <label>Номинал (face value)<input name="face" type="number" step="0.01" value="{_esc(face)}" required></label>
      <label>Купон, % в год<input name="coupon" type="number" step="0.01" value="{_esc(coupon) if coupon else ''}" required></label>
      <label>Частота купонов в год
        <select name="freq">
          <option value="1" {"selected" if freq_v==1 else ""}>1 (раз в год)</option>
          <option value="2" {"selected" if freq_v==2 else ""}>2 (полугодие)</option>
          <option value="4" {"selected" if freq_v==4 else ""}>4 (квартал)</option>
        </select>
      </label>
      <label>Срок до погашения
        <input name="maturity" type="text" placeholder="гггг-мм-дд или годы (напр. 2.5)" value="{_esc(maturity) if maturity else ''}" required>
        <span class="note">Год-месяц-день или дробное число лет</span>
      </label>
      <div id="ytm-fields" style="{'display:none' if calc_mode=='price' else ''}">
        <label>Текущая цена<input name="price" type="number" step="0.01" value="{_esc(price) if price else ''}" required></label>
      </div>
      <div id="price-fields" style="{'display:none' if calc_mode=='ytm' else ''}">
        <label>Ожидаемый YTM, %<input name="ytm" type="number" step="0.01" value="{_esc(q.get('ytm')) if q.get('ytm') else ''}" required></label>
      </div>
      <button class="cta" type="submit">Рассчитать</button>
      <span class="note">Результат — справа. Для глубокого анализа: <a href="/bonds">рейтинг облигаций</a> · <a href="/partners">B2B/API</a></span>
    </form>
    <script>
    // Toggle fields on mode change
    document.querySelector('select[name="mode"]').addEventListener('change', function(e) {{
      document.getElementById('ytm-fields').style.display = e.target.value === 'ytm' ? '' : 'none';
      document.getElementById('price-fields').style.display = e.target.value === 'price' ? '' : 'none';
    }});
    </script>
    """

    # Results card
    result_html = ""
    if ytm_v is not None or price_calc_v is not None:
        result_html = "<div class='card' style='border-color:var(--brand);background:#f0fdf9'><h2 style='margin-top:0'>Результат</h2>"
        if ytm_v is not None:
            result_html += f"<div class='grid'><div class='stat'><div class='k'>YTM (доходность к погашению)</div><div class='v num'>{_fmt_num(ytm_v, 2)}%</div></div>"
            if price_v is not None:
                result_html += f"<div class='stat'><div class='k'>Текущая цена</div><div class='v num'>{_fmt_num(price_v)}</div></div>"
        if price_calc_v is not None:
            result_html += f"<div class='stat'><div class='k'>Чистая цена (расчётная)</div><div class='v num'>{_fmt_num(price_calc_v, 2)}</div></div>"
        if mac_dur is not None:
            result_html += f"<div class='stat'><div class='k'>Модифицированная дюрация</div><div class='v num'>{_fmt_num(mod_dur, 2)}</div></div>"
        if mod_dur is not None:
            result_html += f"<div class='stat'><div class='k'>Дюрация Меколея</div><div class='v num'>{_fmt_num(mac_dur, 2)} лет</div></div>"
        result_html += "</div>"
    elif error:
        result_html = f"<div class='card' style='border-color:var(--red);background:#fef2f2'><p class='alarm'>{_esc(error)}</p></div>"

    body = f"""<h1>Калькулятор облигаций: YTM, цена, дюрация</h1>
<p class="sub">Рассчитайте доходность к погашению (YTM) по текущей цене — или обратную цену по целевому YTM. Дюрация показывает чувствительность к ставкам.</p>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start">
  <div>{form_html}</div>
  <div>{result_html if result_html else "<div class='card'><p class='sub'>Заполните форму — результат появится здесь.</p></div>"}</div>
</div>
<p class="note">Гайды: <a href="/guides/kak-vybrat-obligaciyu">Как выбрать облигацию</a> · <a href="/guides/duration-i-repo-prosto">Duration и РЕПО</a> · <a href="/bonds">Рейтинг облигаций</a> · <a href="/partners">Для бизнеса →</a></p>"""

    title = "Калькулятор облигаций: YTM, цена, дюрация | Aigenis Bonds"
    desc = ("Бесплатный калькулятор облигаций: YTM из цены, цена из YTM, дюрация Меколея и модифицированная. "
            "Помогает сравнивать облигации и депозиты, оценивать процентный риск.")
    json_ld = [json.dumps({
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": "Калькулятор облигаций Aigenis Bonds",
        "description": desc,
        "url": _abs(request, "/calculator"),
        "applicationCategory": "FinanceApplication",
        "operatingSystem": "Web",
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "BYN",
                   "availability": "https://schema.org/InStock"},
    }, ensure_ascii=False)]
    return _skeleton(title, desc, body, request, _abs(request, "/calculator"), json_ld)
