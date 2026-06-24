"""DOM-парсер карточки облигации (fallback)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup


def _try_json_state(soup: BeautifulSoup) -> dict[str, Any] | None:
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag and tag.string:
        try:
            data = json.loads(tag.string)
            props = data.get("props", {}).get("pageProps", {})
            bond = props.get("bond") or props.get("item")
            if isinstance(bond, dict):
                return bond
        except Exception:
            return None

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        if isinstance(data, dict):
            t = data.get("@type", "")
            if t in {"Bond", "FinancialProduct"}:
                return data
        elif isinstance(data, list):
            for node in data:
                if isinstance(node, dict) and node.get("@type") in {"Bond", "FinancialProduct"}:
                    return node
    return None


def _coerce(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    return s or None


def _find_label(soup: BeautifulSoup, label_patterns: list[str]) -> str | None:
    for pat in label_patterns:
        for el in soup.find_all(string=re.compile(pat, re.IGNORECASE)):
            parent = el.parent
            if parent is None:
                continue
            nxt = parent.find_next_sibling()
            if nxt:
                text = nxt.get_text(" ", strip=True)
                if text:
                    return text
            txt = parent.get_text(" ", strip=True)
            if ":" in txt:
                return txt.split(":", 1)[1].strip()
    return None


def _parse_coupon_rate_from_description(text: str) -> str | None:
    m = re.search(r"([\d,]+)\s*%", text)
    if m:
        return m.group(1).replace(",", ".")
    return None


def _parse_coupon_frequency_from_description(text: str) -> int | None:
    text_lower = text.lower()
    if "ежемесяч" in text_lower or "1 раз в месяц" in text_lower:
        return 12
    if "1 раз в квартал" in text_lower:
        return 4
    if "2 раз" in text_lower and "год" in text_lower:
        return 2
    m = re.search(r"(\d+)\s+раз\s+в\s+год", text_lower)
    if m:
        return int(m.group(1))
    return None


def _parse_coupon_schedule(html: str) -> dict[str, list[str]] | None:
    soup = BeautifulSoup(html, "lxml")
    p = soup.find("p", class_="bounds-years")
    if not p:
        return None
    schedule: dict[str, list[str]] = {}
    text = p.get_text("\n", strip=True)
    # Разделяем на токены: годы и даты в скобках
    current_year = None
    tokens = re.split(r"[\n\r]+", text)
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        # Если токен — год
        ym = re.match(r"(\d{4})$", token)
        if ym:
            current_year = ym.group(1)
            schedule.setdefault(current_year, [])
            continue
        # Если токен — скобки с датами
        dates = re.findall(r"(\d{1,2}\.\d{1,2}(?:\.\d{4})?)", token)
        if dates and current_year:
            schedule[current_year].extend(dates)
    return schedule if schedule else None


def _parse_dom(html: str, internal_id: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    title = _coerce(soup.title.get_text() if soup.title else None) or internal_id

    h1 = soup.select_one("h1")
    if h1:
        title = h1.get_text(strip=True) or title

    payload: dict[str, Any] = {
        "id": internal_id,
        "name": title,
        "fetched_at": datetime.now(UTC).isoformat(),
    }

    # Парсинг через dl/dt/dd списки (стандартный HTML)
    def grab(*patterns: str) -> str | None:
        return _find_label(soup, list(patterns))

    payload["issuer"] = grab("эмитент", "issuer") or "Айгенис"
    payload["currency"] = grab("валюта", "currency") or "USD"
    payload["nominal"] = grab("номинал", "nominal")
    payload["coupon_rate"] = grab("ставка купона", "купон", "coupon")
    payload["coupon_frequency"] = grab("периодичность", "частота", "frequency")
    payload["maturity_date"] = grab("дата погашения", "погашение", "maturity")
    payload["price"] = grab("цена", "price")
    payload["yield_to_maturity"] = grab("доходность", "ytm", "yield")
    payload["amortization"] = grab("амортизация", "amortization")
    payload["offer_date"] = grab("оферта", "offer")
    payload["start_date"] = grab("дата размещения", "размещение", "start")
    payload["end_date"] = grab("дата окончания", "окончание", "end")
    payload["isin"] = grab("isin")
    payload["status"] = grab("статус", "status")

    # Парсинг wp-block-aigenis-bounds (основной формат aigenis.by)
    for block in soup.select("div.wp-block-aigenis-bounds"):
        block_reg = (block.get("data-reg") or "").strip()
        block_code = (block.get("data-code") or "").strip()
        block_currency = (block.get("data-curency") or "").strip().upper()
        # Сопоставление: ищем совпадение internal_id с reg-номером или кодом выпуска.
        # Извлекаем числовую часть internal_id (напр. "OP-51" → "51")
        id_num = re.sub(r"[^0-9]", "", internal_id)
        code_num = re.sub(r"[^0-9]", "", block_code)
        reg_num = re.sub(r"[^0-9]", "", block_reg)
        matches = False
        if id_num and (id_num in code_num or id_num in reg_num or code_num in id_num or reg_num in id_num):
            matches = True
        if "aigenis-bounds" in str(soup).lower() and not matches:
            continue

        # data-* атрибуты
        payload.setdefault("registration_number", block.get("data-reg"))
        payload.setdefault("in_stock", (block.get("data-stock") == "true") if block.get("data-stock") else None)
        payload.setdefault("end_date", block.get("data-eterm"))
        payload.setdefault("maturity_term_text", block.get("data-vterm"))

        code_raw = block.get("data-code")
        if code_raw:
            m = re.search(r"(\d+)", code_raw)
            if m:
                payload.setdefault("issue_number", int(m.group(1)))

        content = block.find("div", class_="content")
        if not content:
            continue

        rows = content.find_all("div", class_="col-md-4")
        for row in rows:
            h4 = row.find("h4")
            if not h4:
                continue
            section = h4.get_text(strip=True).lower()

            h5_pairs = row.find_all(["h5", "p"])
            current_key = None
            for el in h5_pairs:
                if el.name == "h5":
                    current_key = el.get_text(strip=True).lower()
                elif el.name == "p" and current_key:
                    value = el.get_text(strip=True)
                    if "регистр" in current_key:
                        payload.setdefault("registration_number", value)
                    elif "номинал" in current_key:
                        m = re.search(r"([\d\s,]+)", value)
                        if m:
                            payload.setdefault("nominal", m.group(1).strip().replace(" ", "").replace("\xa0", "").replace(",", "."))
                    elif "объем" in current_key or "эмисс" in current_key:
                        m = re.search(r"([\d\s,]+)", value)
                        if m:
                            payload.setdefault("issue_volume", m.group(1).strip().replace(" ", "").replace("\xa0", "").replace(",", "."))
                    elif "способ" in current_key or "выплат" in current_key:
                        payload.setdefault("income_method", value)

            if "ставк" in section or "купон" in section:
                for p in row.find_all("p"):
                    text = p.get_text(strip=True)
                    if text and not payload.get("coupon_description"):
                        payload["coupon_description"] = text
                        cr = _parse_coupon_rate_from_description(text)
                        if cr:
                            payload["coupon_rate"] = cr
                        cf = _parse_coupon_frequency_from_description(text)
                        if cf:
                            payload["coupon_frequency"] = cf

            if "график" in section:
                schedule = _parse_coupon_schedule(str(row))
                if schedule:
                    payload["coupon_schedule"] = schedule
                g_text = row.get_text()
                m = re.search(r"Организация[:\s]*([^\n]+)", g_text)
                if m:
                    payload.setdefault("guarantor", m.group(1).strip())

        # Парсинг футера
        footer = block.find("div", class_="bounds-footer")
        if footer:
            ft = footer.get_text(" ", strip=True)
            m = re.search(r"Организация[:\s]*([^\n]+)", ft)
            if m:
                payload.setdefault("guarantor", m.group(1).strip())

        break  # Только первый подходящий блок

    return payload


def parse_detail_html(html: str, internal_id: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")

    state = _try_json_state(soup)
    if state and isinstance(state, dict):
        state.setdefault("id", internal_id)
        return state

    return _parse_dom(html, internal_id)
