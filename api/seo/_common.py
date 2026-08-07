"""Shared constants, helpers and rendering for the SEO package (api.seo.*).

Formerly module-level code in api/seo.py; kept here so every sub-page can reuse
the same bot-detection, skeleton and formatting without duplication.
"""

from __future__ import annotations

import html
import os
import re
import tempfile
from datetime import date, datetime
from typing import Any

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse

from api.frontend import frontend_index
from scraper.logging import get_logger

logger = get_logger("api.seo")

# Where the pre-generated sitemap is written. The scheduler regenerates it after
# each parse when ``SEO_PUBLIC_BASE_URL`` is configured; the endpoint serves this
# file when present and otherwise renders on the fly from the request URL.
SEO_SITEMAP_PATH = os.getenv("SEO_SITEMAP_PATH") or os.path.join(
    tempfile.gettempdir(), "aigenis_sitemap.xml"
)

SITE_NAME = "Aigenis Bonds"
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").strip()
APP_CTA_LABEL = "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u043b\u043d\u044b\u0439 \u0440\u0430\u0437\u0431\u043e\u0440 \u0432 Aigenis Bonds"

# ─── Bot / human split ───────────────────────────────────────────────────────
# SEO-covered paths (/bonds, /bonds/{id}, /calculator) shadow the SPA in
# production, so crawlers must get the server-rendered page while regular
# visitors get the single-page app. Matching a wide set of crawlers and link
# previewers (Telegram, VK, Facebook, Slack…) — they also consume the
# server-rendered OG markup.
_BOT_UA_RE = re.compile(
    r"(googlebot|yandex(?:bot)?|bingbot|bingpreview|duckduckbot|baiduspider|"
    r"applebot|facebookexternalhit|facebot|twitterbot|linkedinbot|slackbot|"
    r"discordbot|telegrambot|whatsapp|vkShare|vkbot|pinterest|redditbot|"
    r"instagram|skypeuripreview|snapchat|"
    r"ahrefsbot|semrushbot|mj12bot|dotbot|rogerbot|serpstatbot|screaming frog|"
    r"blexbot|seznambot|exabot|sogou|ia_archiver|archive\.org|slurp|"
    r"monitor|uptimerobot|pingdom|"
    r"gptbot|chatgpt|claude(?:bot)?|anthropic|perplexity|bard|bytespider|"
    r"meta-externalagent|petalbot|cohere|youbot|"
    r"\bbot\b|\bspider\b|\bcrawler\b|\bpreview\b|\bslurp\b)",
    re.IGNORECASE,
)


def _is_bot(request: Request) -> bool:
    """True for crawlers and link previewers; empty UA counts as a bot."""
    ua = request.headers.get("user-agent", "")
    return not ua or bool(_BOT_UA_RE.search(ua))


def _spa_page() -> HTMLResponse | None:
    """The built SPA entry, or None when the frontend is not built here."""
    index = frontend_index()
    if index is None:
        return None
    return FileResponse(
        index,
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


# Minimal, dependency-free CSS — readable light theme for crawlers + visitors.
_PAGE_CSS = """
:root{--bg:#f7f8fa;--card:#fff;--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;
--brand:#004b65;--brand-d:#003545;--amber:#b45309;--red:#b91c1c;--chip:#e3eef3}
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


def _skeleton(
    title: str,
    description: str,
    body: str,
    request: Request,
    canonical: str,
    json_ld: list[str] | None = None,
) -> HTMLResponse:
    _web, bot = _app_links(request)
    ld = "\n".join(json_ld or [])
    ld_block = f'<script type="application/ld+json">{ld}</script>' if ld else ""
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
        f'aria-hidden="true"><polyline points="{poly}" fill="none" stroke="#004b65" '
        f'stroke-width="2"/></svg>'
    )
