"""Issuer / bond news from the MOEX ISS sitenews feed (free, no auth).

The feed is a public JSON API and requires no key or login. Items are matched
by keyword: bond ISIN, bond name tokens and issuer tokens. The feed is cached
in memory for a few minutes so the endpoint stays cheap.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Query
from sqlalchemy import select

from scraper.db import session_scope
from scraper.orm import BondORM

router = APIRouter(prefix="/api/v1", tags=["news"])

MOEX_SITENEWS_URL = "https://iss.moex.com/iss/sitenews.json?iss=no&limit=50&lang=ru"
NEWS_URL_TMPL = "https://www.moex.com/n{news_id}"
CACHE_TTL_S = 15 * 60
FETCH_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
# The ISS feed is paginated in 50-item pages; pull several pages to widen the
# keyword-matching window without hammering the exchange.
FEED_PAGES = 4

# Short/function words that never help to match an issuer or a bond.
_STOPWORDS = {
    "облигац",
    "биржев",
    "выпуск",
    "ценных",
    "бумага",
    "бумаг",
    "регистрац",
    "включен",
    "исключен",
    "изменен",
    "список",
    "списка",
    "списке",
    "торгам",
    "торгов",
    "торгах",
    "решение",
    "решений",
    "приняты",
    "принять",
    "начала",
    "начале",
    "дату",
    "дата",
    "даты",
    "прекращен",
    "приостанов",
    "размещен",
    "проведен",
    "проведет",
    "состоятся",
    "аукцион",
    "депозитн",
    "рынка",
    "рынке",
    "рынок",
    "допуске",
    "допуск",
    "операциям",
    "операций",
    "значения",
    "значение",
    "границы",
    "границ",
    "коридора",
    "коридор",
    "риск",
    "риска",
    "рисков",
    "рыночных",
    "валютной",
    "валютных",
    "пары",
    "сделок",
    "сделки",
    "проспекта",
    "проспект",
    "эмиссионные",
    "эмиссион",
    "документы",
    "документ",
    "представител",
    "владельцев",
    "сведений",
    "сведен",
    "части",
    "часть",
    "внесении",
    "внесение",
    "порядке",
    "сбора",
    "заявок",
    "заключен",
    "серии",
    "серия",
    "номера",
    "номер",
    "присвоени",
    "изменены",
    "нижней",
    "верхней",
    "оценки",
    "диапазона",
    "проводится",
}

_cache: dict[str, tuple[float, list[dict]]] = {}


async def _fetch_feed() -> list[dict]:
    """Return the raw sitenews feed (several pages), cached for CACHE_TTL_S."""
    now = time.monotonic()
    cached = _cache.get("feed")
    if cached and now - cached[0] < CACHE_TTL_S:
        return cached[1]

    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        for start in range(0, FEED_PAGES * 50, 50):
            resp = await client.get(f"{MOEX_SITENEWS_URL}&start={start}")
            resp.raise_for_status()
            body = resp.json()
            block = body.get("sitenews", {})
            columns = block.get("columns", [])
            for row in block.get("data", []):
                record = dict(zip(columns, row, strict=False))
                items.append(
                    {
                        "id": record.get("id"),
                        "tag": record.get("tag"),
                        "title": str(record.get("title") or "").strip(),
                        "published_at": str(record.get("published_at") or ""),
                    }
                )
            if not block.get("data"):
                break

    # Feed pages are ordered newest-first; dedupe by id and keep the order.
    seen: set[int] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        if item["id"] is not None and item["id"] in seen:
            continue
        if item["id"] is not None:
            seen.add(item["id"])
        unique.append(item)

    _cache["feed"] = (now, unique)
    return unique


def _keywords(text: str | None) -> list[str]:
    """Significant lowercase tokens (>=4 letters) with stopwords removed."""
    if not text:
        return []
    tokens = re.findall(r"[a-zа-яё]{4,}", text.lower())
    return [t for t in tokens if t not in _STOPWORDS][:12]


def _matches(title: str, keywords: list[str]) -> bool:
    t = title.upper()
    return any(k.upper() in t for k in keywords)


async def _bond_keywords(bond_id: str) -> list[str] | None:
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == bond_id))
        ).scalar_one_or_none()
        if bond is None:
            return None
        haystacks = [bond.name, bond.issuer]
        if bond.isin:
            haystacks.append(bond.isin)
    keywords: list[str] = []
    for h in haystacks:
        for kw in _keywords(h):
            if kw not in keywords:
                keywords.append(kw)
    if bond.isin:
        keywords.append(bond.isin)
    return keywords


@router.get("/news")
async def api_news(
    issuer: str | None = Query(None, description="Issuer name to filter by"),
    bond_id: str | None = Query(None, description="Bond internal id to filter by"),
    limit: int = Query(10, ge=1, le=50),
    days: int = Query(365, ge=1, le=730),
):
    """Latest news relevant to an issuer or a bond, from the MOEX feed."""
    try:
        items = await _fetch_feed()
    except Exception:
        return []

    keywords: list[str] | None = None
    if bond_id:
        keywords = await _bond_keywords(bond_id)
        if keywords is None:
            return []
    elif issuer:
        keywords = _keywords(issuer)

    cutoff = datetime.now() - timedelta(days=days)
    out: list[dict[str, Any]] = []
    for item in items:
        published = item.get("published_at") or ""
        try:
            dt = datetime.strptime(published, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if dt < cutoff:
            continue
        if keywords and not _matches(item["title"], keywords):
            continue
        out.append(
            {
                "id": item["id"],
                "title": item["title"],
                "published_at": published,
                "url": NEWS_URL_TMPL.format(news_id=item["id"]),
            }
        )
        if len(out) >= limit:
            break
    return out
