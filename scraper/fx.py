"""Fetch FX rates and metal prices from the National Bank of the Republic of Belarus."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from xml.etree import ElementTree as ET

import httpx

from scraper.client import AigenisClient
from notifications.fx_repository import upsert_fx, upsert_metal
from scraper.db import session_scope
from scraper.logging import get_logger
from scraper.config import get_settings
from scraper.pipeline import run_once

logger = get_logger("scraper.fx")

NBRB_API_URL = "https://api.nbrb.by/exrates/rates?periodicity=0"
NBRB_SOAP_URL = "https://services.nbrb.by/exrates.asmx"

TROY_OZ_PER_GRAM = Decimal("31.1034768")

FX_PAIRS: dict[str, str] = {
    "USD": "USD/BYN",
    "EUR": "EUR/BYN",
    "RUB": "RUB/BYN",
    "CNY": "CNY/BYN",
}

METAL_IDS: dict[str, int] = {
    "XAU": 0,
    "XAG": 1,
    "XPT": 2,
}

INTERESTING = set(FX_PAIRS)


async def fetch_and_save_rates() -> dict[str, Decimal]:
    """Fetch currency rates from NBRB REST API and persist to DB."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(NBRB_API_URL)
        resp.raise_for_status()
        raw: list[dict] = resp.json()

    rates: dict[str, Decimal] = {}
    for item in raw:
        abbr: str | None = item.get("Cur_Abbreviation")
        if abbr not in INTERESTING:
            continue
        scale = Decimal(str(item.get("Cur_Scale", 1)))
        official = item.get("Cur_OfficialRate")
        if official is None:
            continue
        rates[FX_PAIRS[abbr]] = Decimal(str(official)) / scale

    async with session_scope() as session:
        for pair, rate in rates.items():
            await upsert_fx(session, pair, rate)

    logger.info("fx_rates_fetched", count=len(rates), rates={k: float(v) for k, v in rates.items()})
    return rates


def _build_soap_envelope(metal_id: int, from_date: date, to_date: date) -> str:
    return f"""<?xml version='1.0' encoding='utf-8'?>
<soap:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance'
               xmlns:xsd='http://www.w3.org/2001/XMLSchema'
               xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
  <soap:Body>
    <MetalsPrices xmlns='https://www.nbrb.by/'>
      <MetalId>{metal_id}</MetalId>
      <fromDate>{from_date.isoformat()}</fromDate>
      <toDate>{to_date.isoformat()}</toDate>
    </MetalsPrices>
  </soap:Body>
</soap:Envelope>"""


def _parse_metal_prices(xml_text: str) -> list[Decimal]:
    root = ET.fromstring(xml_text)
    prices: list[Decimal] = []
    for elem in root.iter():
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local == "AccountPrice":
            for child in elem:
                child_local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_local == "Price" and child.text:
                    prices.append(Decimal(child.text))
    return prices


async def _fetch_metal_prices_soap(metal_id: int, from_date: date, to_date: date) -> list[Decimal]:
    envelope = _build_soap_envelope(metal_id, from_date, to_date)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            NBRB_SOAP_URL,
            content=envelope,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "https://www.nbrb.by/MetalsPrices",
            },
        )
        resp.raise_for_status()
    return _parse_metal_prices(resp.text)


async def fetch_and_save_metal_prices() -> dict[str, Decimal]:
    """Fetch latest metal prices from NBRB SOAP service and persist to DB.

    The SOAP service returns prices in BYN per gram. We convert to BYN per troy ounce.
    """
    today = date.today()
    from_date = today - timedelta(days=7)

    metals: dict[str, Decimal] = {}
    for code, mid in METAL_IDS.items():
        prices = await _fetch_metal_prices_soap(mid, from_date, today)
        if prices:
            price_troy = prices[-1] * TROY_OZ_PER_GRAM
            metals[code] = price_troy

    async with session_scope() as session:
        for metal, price in metals.items():
            await upsert_metal(session, metal, price)

    logger.info("metal_prices_fetched", count=len(metals), prices={k: float(v) for k, v in metals.items()})
    return metals


async def fetch_and_save_bonds() -> None:
    """Parse all Aigenis bonds (USD, BYN, EUR, RUB, CNY) from the official website."""
    settings = get_settings()
    async with AigenisClient(settings.aigenis) as client:
        await run_once(client, settings.aigenis.currencies)

    logger.info("bond_scraped", summary=f"{settings.aigenis.currencies}")
