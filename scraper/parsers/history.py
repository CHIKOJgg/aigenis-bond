"""DOM-парсер для истории (fallback)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup


def _try_state(soup: BeautifulSoup) -> list[dict[str, Any]] | None:
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag and tag.string:
        try:
            data = json.loads(tag.string)
        except Exception:
            return None
        props = data.get("props", {}).get("pageProps", {})
        candidates = props.get("history") or props.get("items")
        if isinstance(candidates, list):
            return [c for c in candidates if isinstance(c, dict)]
        if isinstance(candidates, dict) and isinstance(candidates.get("items"), list):
            return [c for c in candidates["items"] if isinstance(c, dict)]
    return None


def _parse_table(soup: BeautifulSoup) -> list[dict[str, Any]]:
    rows = soup.select("table.history tbody tr, .history-row")
    out: list[dict[str, Any]] = []
    for row in rows:
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        date_text = cells[0]
        try:
            d = datetime.fromisoformat(date_text.replace("Z", "+00:00")).date()
        except Exception:
            m = re.search(r"\d{4}-\d{2}-\d{2}", date_text)
            if not m:
                continue
            try:
                d = datetime.strptime(m.group(0), "%Y-%m-%d").date()
            except Exception:
                continue
        out.append(
            {
                "date": d.isoformat(),
                "price": cells[1] if len(cells) > 1 else None,
                "yield": cells[2] if len(cells) > 2 else None,
                "coupon": cells[3] if len(cells) > 3 else None,
                "status": cells[4] if len(cells) > 4 else "unknown",
            }
        )
    return out


def parse_history_html(html: str, internal_id: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")

    state = _try_state(soup)
    if state:
        return state

    return _parse_table(soup)
