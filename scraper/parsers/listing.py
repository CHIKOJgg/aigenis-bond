"""DOM-парсер для листинга (fallback)."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup


def _try_jsonld(soup: BeautifulSoup) -> list[dict[str, Any]] | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            return [n for n in data["@graph"] if isinstance(n, dict)]
        if isinstance(data, list):
            return [n for n in data if isinstance(n, dict)]
    return None


def _try_next_data(soup: BeautifulSoup) -> list[dict[str, Any]] | None:
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        data = json.loads(tag.string)
    except Exception:
        return None
    props = data.get("props", {}).get("pageProps", {})
    candidates = props.get("bonds") or props.get("items") or props.get("data")
    if isinstance(candidates, list):
        return [c for c in candidates if isinstance(c, dict)]
    if isinstance(candidates, dict):
        items = candidates.get("items")
        if isinstance(items, list):
            return [c for c in items if isinstance(c, dict)]
    return None


def _try_table(soup: BeautifulSoup, currency: str) -> list[dict[str, Any]]:
    rows = soup.select("table.bonds tbody tr, .bond-row")
    out: list[dict[str, Any]] = []
    for row in rows:
        a = row.select_one("a[href*='/bonds/']")
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"/bonds/([A-Za-z0-9_-]+)", str(href))
        if not m:
            continue
        internal_id = m.group(1)
        name = (a.get_text() or "").strip() or internal_id
        out.append(
            {
                "internal_id": internal_id,
                "name": name,
                "currency": currency.upper(),
                "isin": None,
            }
        )
    return out


def _parse_coupon_rate_from_description(text: str) -> str | None:
    """Извлечь процентную ставку из описания типа '7% годовых, 1 раз в квартал'."""
    m = re.search(r"([\d,]+)\s*%", text)
    if m:
        return m.group(1).replace(",", ".")
    return None


def _parse_coupon_frequency_from_description(text: str) -> int | None:
    """Извлечь периодичность купона из описания."""
    text_lower = text.lower()
    if "кажд" in text_lower or "месяц" in text_lower:
        if "1 раз в месяц" in text_lower or "ежемесяч" in text_lower:
            return 12
        if "1 раз в квартал" in text_lower:
            return 4
        if "2 раз" in text_lower:
            return 2
    # "N раз в год" pattern
    m = re.search(r"(\d+)\s+раз\s+в\s+год", text_lower)
    if m:
        return int(m.group(1))
    # "1 раз в N месяцев" pattern
    m = re.search(r"1\s+раз\s+в\s+(\d+)\s+месяц", text_lower)
    if m:
        months = int(m.group(1))
        return {1: 12, 2: 6, 3: 4, 4: 3, 6: 2, 12: 1}.get(months)
    return None


def _parse_coupon_schedule(summary_div: BeautifulSoup | None) -> dict[str, list[str]] | None:
    """Парсит график купонных выплат из блока <p class='bounds-years'>."""
    if summary_div is None:
        return None
    p = summary_div.find("p", class_="bounds-years")
    if not p:
        return None
    schedule: dict[str, list[str]] = {}
    text = p.get_text("\n", strip=True)
    current_year = None
    tokens = re.split(r"[\n\r]+", text)
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        ym = re.match(r"(\d{4})$", token)
        if ym:
            current_year = ym.group(1)
            schedule.setdefault(current_year, [])
            continue
        dates = re.findall(r"(\d{1,2}\.\d{1,2}(?:\.\d{4})?)", token)
        if dates and current_year:
            schedule[current_year].extend(dates)
    return schedule if schedule else None


def _parse_guarantor(summary_div: BeautifulSoup | None) -> str | None:
    """Извлечь организацию-гаранта из блока bounds-years или bounds-footer."""
    if summary_div is None:
        return None
    p = summary_div.find("p", class_="bounds-years")
    if p:
        text = p.get_text()
        m = re.search(r"Организация[:\s]*([^\n]+)", text)
        if m:
            return m.group(1).strip()
    return None


def _parse_aigenis_bond_block(block: BeautifulSoup, target_currency: str) -> dict[str, Any] | None:
    """Распарсить один блок wp-block-aigenis-bounds в структуру Bond."""
    # --- data-* атрибуты ---
    currency_raw = (block.get("data-curency") or "").strip().upper()
    eterm = block.get("data-eterm")
    vterm = block.get("data-vterm")
    stock = block.get("data-stock")
    code_raw = block.get("data-code")
    reg_raw = block.get("data-reg")

    if not currency_raw:
        return None

    # Фильтр по валюте
    if target_currency not in {"", "ALL", "ЛЮБАЯ"} and currency_raw != target_currency:
        return None

    internal_id = reg_raw or ""
    name = (code_raw or internal_id or "").strip()

    # --- Извлекаем issue_number из code_raw (например "51 выпуск") ---
    issue_number = None
    if code_raw:
        m = re.search(r"(\d+)", code_raw)
        if m:
            issue_number = int(m.group(1))

    # Собираем базовую структуру
    payload: dict[str, Any] = {
        "internal_id": internal_id,
        "name": name,
        "currency": currency_raw,
        "isin": None,
        "registration_number": reg_raw,
        "issue_number": issue_number,
        "in_stock": stock == "true" if stock else None,
        "end_date": eterm,
        "maturity_term_text": vterm,
    }

    # --- Извлекаем summary строки (видимая часть до раскрытия) ---
    # Summary содержит: title/currency, coupon rate (как "Доходность"), end date, maturity
    summary = block.find("summary")
    if summary:
        # Купон (Доходность) из видимой строки — это ставка купона
        text_cols = summary.find_all("div", class_="display-column")
        for col in text_cols:
            title_el = col.find("span", class_="title")
            text_el = col.find("span", class_="text")
            if not title_el or not text_el:
                continue
            title = title_el.get_text(strip=True).lower()
            text = text_el.get_text(strip=True)
            if "доход" in title:
                # Это ставка купона (coupon_rate), не YTM!
                rate_str = text.replace("%", "").replace(",", ".").strip()
                if rate_str and rate_str != "—":
                    payload["coupon_rate"] = rate_str
                    payload["coupon_description"] = text

    # --- Извлекаем expanded content (после раскрытия) ---
    content_div = block.find("div", class_="content")
    if content_div:
        # Секция "Основное"
        rows = content_div.find_all("div", class_="col-md-4")

        for row in rows:
            h4 = row.find("h4")
            if not h4:
                continue
            section_title = h4.get_text(strip=True).lower()

            h5_pairs = row.find_all(["h5", "p"])
            current_key = None
            for el in h5_pairs:
                if el.name == "h5":
                    current_key = el.get_text(strip=True).lower()
                elif el.name == "p" and current_key:
                    value = el.get_text(strip=True)

                    if "номер" in current_key and (
                        "регистрац" in current_key or "регистр" in current_key
                    ):
                        if not payload.get("registration_number"):
                            payload["registration_number"] = value
                        if not payload.get("internal_id"):
                            payload["internal_id"] = value

                    elif "номинал" in current_key:
                        m = re.search(r"([\d\s,]+)", value)
                        if m:
                            payload["nominal"] = (
                                m.group(1)
                                .strip()
                                .replace(" ", "")
                                .replace("\xa0", "")
                                .replace(",", ".")
                            )

                    elif "объем" in current_key:
                        m = re.search(r"([\d\s,]+)", value)
                        if m:
                            payload["issue_volume"] = (
                                m.group(1)
                                .strip()
                                .replace(" ", "")
                                .replace("\xa0", "")
                                .replace(",", ".")
                            )

                    elif (
                        "способ" in current_key or "выплат" in current_key or "доход" in current_key
                    ):
                        payload["income_method"] = value
                        # Также парсим coupon_rate из описания "Купон, номинирована в EUR"
                        if not payload.get("coupon_rate"):
                            cr = _parse_coupon_rate_from_description(value)
                            if cr:
                                payload["coupon_rate"] = cr
                            cf = _parse_coupon_frequency_from_description(value)
                            if cf:
                                payload["coupon_frequency"] = cf

                    elif "эмитент" in current_key or "issuer" in current_key:
                        payload["issuer"] = value

            # Секция "Ставка купона"
            if "ставк" in section_title or "купон" in section_title:
                # Пример: "7% годовых, 1 раз в квартал"
                ps = row.find_all("p")
                for p in ps:
                    text = p.get_text(strip=True)
                    if text:
                        payload["coupon_description"] = text
                        cr = _parse_coupon_rate_from_description(text)
                        if cr:
                            payload["coupon_rate"] = cr
                        cf = _parse_coupon_frequency_from_description(text)
                        if cf:
                            payload["coupon_frequency"] = cf

            # Секция "График купона"
            if "график" in section_title or "купон" in section_title:
                schedule = _parse_coupon_schedule(row)
                if schedule:
                    payload["coupon_schedule"] = schedule
                guarantor = _parse_guarantor(row)
                if guarantor:
                    payload["guarantor"] = guarantor

    # --- Пытаемся извлечь coupon_rate и maturity_date из футера ---
    footer = block.find("div", class_="bounds-footer")
    if footer:
        footer_text = footer.get_text(" ", strip=True)
        if "организац" in footer_text.lower():
            m = re.search(r"Организация[:\s]*([^\n]+)", footer_text)
            if m:
                g = m.group(1).strip()
                if g and not payload.get("guarantor"):
                    payload["guarantor"] = g

    return payload


def _try_aigenis_by_blocks(soup: BeautifulSoup, currency: str) -> list[dict[str, Any]]:
    """Парсер блоков aigenis.by (wp-block-aigenis-bounds) — полный парсинг."""
    out: list[dict[str, Any]] = []
    target_currency = currency.strip().upper()

    for block in soup.select("div.wp-block-aigenis-bounds"):
        payload = _parse_aigenis_bond_block(block, target_currency)
        if payload is not None:
            out.append(payload)

    return out


def parse_listing_html(html: str, currency: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")

    blocks = _try_aigenis_by_blocks(soup, currency)
    if blocks:
        return blocks

    for extractor in (_try_next_data, _try_jsonld):
        items = extractor(soup)
        if items:
            from scraper.api import parse_listing_items

            if any(("bond" in str(it).lower() or "isin" in it) for it in items):
                return parse_listing_items(items, currency)

    return _try_table(soup, currency)
