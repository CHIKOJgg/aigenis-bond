"""JSON API парсеры (ответы внутреннего endpoint)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from scraper.errors import ParseError
from scraper.models import Bond, BondHistory


def _coerce_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception as e:
        raise ParseError(f"bad date {value!r}") from e


def _first_not_none(*values: Any) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def parse_listing_items(items: list[dict[str, Any]], currency: str) -> list[dict[str, Any]]:
    """Нормализует список облигаций из JSON API к плоскому виду."""
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        internal_id = it.get("id") or it.get("internal_id") or it.get("slug") or it.get("registration_number")
        if not internal_id:
            continue
        out.append(
            {
                "internal_id": str(internal_id),
                "name": str(it.get("name") or it.get("title") or internal_id),
                "currency": str(it.get("currency") or currency).upper(),
                "isin": it.get("isin"),
                "nominal": it.get("nominal"),
                "coupon_rate": it.get("coupon_rate") or it.get("coupon"),
                "coupon_frequency": it.get("coupon_frequency") or it.get("frequency"),
                "registration_number": it.get("registration_number") or it.get("reg_number"),
                "issue_number": it.get("issue_number") or it.get("issue"),
                "issue_volume": it.get("issue_volume"),
                "income_method": it.get("income_method"),
                "in_stock": it.get("in_stock"),
                "guarantor": it.get("guarantor"),
                "maturity_term_text": it.get("maturity_term_text") or it.get("maturity_term"),
                "coupon_description": it.get("coupon_description"),
                "coupon_schedule": it.get("coupon_schedule"),
            }
        )
    return out


def parse_bond_payload(
    payload: dict[str, Any],
    *,
    internal_id_fallback: str | None = None,
) -> Bond:
    """Парсит JSON с детальной информацией об облигации в `Bond`."""
    internal_id = payload.get("id") or payload.get("internal_id") or internal_id_fallback
    if not internal_id:
        raise ParseError("missing internal_id in payload")
    name = payload.get("name") or payload.get("title")
    if not name:
        raise ParseError("missing name in payload")

    fetched_at_raw = payload.get("fetched_at") or datetime.now(UTC).isoformat()
    try:
        fetched_at = datetime.fromisoformat(str(fetched_at_raw).replace("Z", "+00:00"))
    except Exception:
        fetched_at = datetime.now(UTC)

    return Bond(
        internal_id=str(internal_id),
        name=str(name),
        issuer=payload.get("issuer"),
        currency=str(payload.get("currency", "USD")).upper(),
        nominal=payload.get("nominal"),
        coupon_rate=_first_not_none(payload.get("coupon_rate"), payload.get("coupon")),
        coupon_frequency=_first_not_none(payload.get("coupon_frequency"), payload.get("frequency")),
        maturity_date=_coerce_date(_first_not_none(payload.get("maturity_date"), payload.get("maturity"))),
        price=payload.get("price"),
        yield_to_maturity=_first_not_none(
            payload.get("yield_to_maturity"), payload.get("ytm"), payload.get("yield")
        ),
        amortization=payload.get("amortization"),
        offer_date=_coerce_date(payload.get("offer_date")),
        start_date=_coerce_date(payload.get("start_date")),
        end_date=_coerce_date(payload.get("end_date")),
        isin=payload.get("isin"),
        status=payload.get("status", "unknown"),
        registration_number=payload.get("registration_number") or payload.get("reg_number"),
        issue_volume=payload.get("issue_volume"),
        issue_number=payload.get("issue_number") or payload.get("issue"),
        income_method=payload.get("income_method"),
        in_stock=payload.get("in_stock"),
        guarantor=payload.get("guarantor"),
        maturity_term_text=payload.get("maturity_term_text") or payload.get("maturity_term"),
        coupon_description=payload.get("coupon_description"),
        coupon_schedule=payload.get("coupon_schedule"),
        raw=payload,
        fetched_at=fetched_at,
    )


def parse_history_items(
    items: list[dict[str, Any]],
    *,
    internal_id: str,
) -> list[BondHistory]:
    """Парсит JSON с историческими снимками в список `BondHistory`."""
    out: list[BondHistory] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        d = _coerce_date(it.get("date") or it.get("timestamp"))
        if d is None:
            continue
        yield_val = it.get("yield")
        if yield_val is None:
            yield_val = it.get("yield_to_maturity")
        if isinstance(yield_val, Decimal):
            yield_val = str(yield_val)
        out.append(
            BondHistory(
                internal_id=internal_id,
                date=d,
                price=it.get("price"),
                yield_=yield_val,
                coupon=it.get("coupon"),
                status=it.get("status", "unknown"),
            )
        )
    return out
