"""Audit test suite for scraper.models, scraper.fx, scraper.pipeline and the
Telegram subscription modules (telegram_bot.stars_payments, telegram_bot.subscriptions).

This file targets the EDGE cases the existing suites miss:
* ``_to_decimal`` / ``Bond`` parsing quirks (comma vs dot, thousand separators,
  cyrillic status/currency normalisation, int fields with separators);
* ``scraper.fx`` constants, NBRB payload edge cases and the fx/metal repository
  ordering (latest/previous); network is faked with monkeypatched ``httpx``;
* the pure helper functions of ``scraper.pipeline`` (period math, coupon rate
  derivation, ``_d`` coercion) — no network calls;
* Telegram Stars money-safety edges: unknown/mismatched charge ids, empty
  payloads, plan downgrades, double delivery idempotency, refunds without a
  charge id, cross-channel (Stars/YooKassa) interplay.

Every test is unit-level: no real Bot instance, no network. DB work uses the
project's in-memory aiosqlite schema (see tests/conftest.py) via
``scraper.db.session_scope``.
"""

from __future__ import annotations

import asyncio
import importlib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select

from scraper.db import session_scope
from scraper.orm import FxRateORM, MetalPriceORM, SubscriptionORM, UserORM
from telegram_bot import stars_payments
from telegram_bot import subscriptions as subs


def _now() -> datetime:
    return datetime.now(UTC)


def _expire_trial(tg_id: int) -> None:
    """Kill the automatic 7-day trial so tier assertions reflect paid status."""
    asyncio.run(_expire_trial_async(tg_id))


async def _expire_trial_async(tg_id: int) -> None:
    async with session_scope() as session:
        user = (
            await session.execute(select(UserORM).where(UserORM.telegram_id == tg_id))
        ).scalar_one()
        user.trial_end = _now() - timedelta(days=1)


async def _user_row(tg_id: int) -> UserORM:
    async with session_scope() as session:
        user = (
            await session.execute(select(UserORM).where(UserORM.telegram_id == tg_id))
        ).scalar_one()
        return user


# ─────────────────────────────────────────────────────────────────────────
# scraper.models — _to_decimal
# ─────────────────────────────────────────────────────────────────────────


def test_to_decimal_space_thousands_separator():
    from scraper.models import _to_decimal

    assert _to_decimal("1 234.56") == Decimal("1234.56")
    assert _to_decimal("12 345") == Decimal("12345")


def test_to_decimal_comma_is_decimal_separator():
    from scraper.models import _to_decimal

    assert _to_decimal("12,5") == Decimal("12.5")
    assert _to_decimal("12,5 %") == Decimal("12.5")
    assert _to_decimal("-5,5") == Decimal("-5.5")


def test_to_decimal_dot_and_sign_and_trailing_percent():
    from scraper.models import _to_decimal

    assert _to_decimal("12.5") == Decimal("12.5")
    assert _to_decimal("-5.5") == Decimal("-5.5")
    assert _to_decimal(" +12.5 ") == Decimal("12.5")
    assert _to_decimal("8.5%") == Decimal("8.5")


def test_to_decimal_empty_and_none():
    from scraper.models import _to_decimal

    assert _to_decimal(None) is None
    assert _to_decimal("") is None
    assert _to_decimal("   ") is None
    assert _to_decimal("  %  ") is None


def test_to_decimal_passthrough_and_numeric_types():
    from scraper.models import _to_decimal

    assert _to_decimal(Decimal("7.25")) == Decimal("7.25")
    assert _to_decimal(7) == Decimal("7")
    assert _to_decimal(7.5) == Decimal("7.5")
    assert _to_decimal(0) == Decimal("0")
    assert _to_decimal("0") == Decimal("0")  # zero is a value, not "missing"


def test_to_decimal_garbage_string_raises():
    from scraper.models import _to_decimal

    with pytest.raises(ValueError, match="Cannot parse decimal from 'abc'"):
        _to_decimal("abc")


def test_to_decimal_comma_thousands_rejected():
    """Source replaces "," with "." first, so "1,234.56" becomes "1.234.56"
    (an invalid number) and parsing raises. Comma is treated as a DECIMAL
    separator, never as a thousands separator."""
    from scraper.models import _to_decimal

    with pytest.raises(ValueError, match="Cannot parse decimal from '1,234.56'"):
        _to_decimal("1,234.56")


def test_to_decimal_extreme_values():
    from scraper.models import _to_decimal

    assert _to_decimal("99999999999999999999999999.5") == Decimal("99999999999999999999999999.5")
    assert _to_decimal("1e10") == Decimal("1E+10")
    assert _to_decimal("0.0000000001") == Decimal("0.0000000001")


def test_to_decimal_bool_raises_invalid_operation():
    """bool is an int subclass, so ``Decimal(str(True))`` is attempted and the
    resulting InvalidOperation escapes (the try/except only wraps strings)."""
    from scraper.models import _to_decimal

    with pytest.raises(InvalidOperation):
        _to_decimal(True)


def test_to_decimal_unsupported_type_raises():
    from scraper.models import _to_decimal

    with pytest.raises(ValueError, match="Unsupported decimal value"):
        _to_decimal([])
    with pytest.raises(ValueError, match="Unsupported decimal value"):
        _to_decimal(object())


# ─────────────────────────────────────────────────────────────────────────
# scraper.models — Bond model
# ─────────────────────────────────────────────────────────────────────────


def _bond(**overrides):
    from scraper.models import Bond

    kwargs = {
        "internal_id": "AUD-1",
        "name": "Audit Bond",
        "currency": "USD",
        "fetched_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    kwargs.update(overrides)
    return Bond(**kwargs)


def test_bond_minimal_construction_defaults():
    b = _bond()
    assert b.internal_id == "AUD-1"
    assert b.currency == "USD"
    assert b.market == "bcse"
    assert b.status == "unknown"
    assert b.is_government is False
    assert b.raw == {}
    assert b.coupon_rate is None
    assert b.coupon_frequency is None
    assert b.price is None
    assert b.yield_to_maturity is None
    assert b.maturity_date is None
    assert b.nominal is None


def test_bond_currency_normalization():
    assert _bond(currency="usd").currency == "USD"
    assert _bond(currency="ДОЛЛАР").currency == "USD"
    assert _bond(currency="ДОЛЛАР США").currency == "USD"
    assert _bond(currency="ДОЛЛАРЫ").currency == "USD"
    assert _bond(currency="РУБЛЬ").currency == "BYN"
    assert _bond(currency="БЕЛОРУССКИЙ РУБЛЬ").currency == "BYN"
    assert _bond(currency="ЕВРО").currency == "EUR"
    assert _bond(currency="ЗОЛОТО").currency == "XAU"
    assert _bond(currency="GOLD").currency == "XAU"
    assert _bond(currency="СЕРЕБРО").currency == "XAG"
    assert _bond(currency="ПЛАТИНА").currency == "XPT"


def test_bond_currency_unknown_or_missing_rejected():
    with pytest.raises(ValueError):  # pydantic ValidationError
        _bond(currency="GBP")
    with pytest.raises(ValueError):
        _bond(currency=None)


def test_bond_coupon_frequency_validation():
    for freq in (1, 2, 4, 12):
        assert _bond(coupon_frequency=freq).coupon_frequency == freq
    for bad in (3, 0, 6, "2", -1):
        with pytest.raises(ValueError):
            _bond(coupon_frequency=bad)


def test_bond_decimal_fields_parse_strings():
    b = _bond(
        coupon_rate="8,5 %",
        price="101.5",
        nominal="1 000",
        yield_to_maturity="-5.5",
        issue_volume="5000000.25",
        exchange_rate_on_start="3,29",
    )
    assert b.coupon_rate == Decimal("8.5")
    assert b.price == Decimal("101.5")
    assert b.nominal == Decimal("1000")
    assert b.yield_to_maturity == Decimal("-5.5")
    assert b.issue_volume == Decimal("5000000.25")
    assert b.exchange_rate_on_start == Decimal("3.29")


def test_bond_decimal_field_garbage_rejected():
    with pytest.raises(ValueError):
        _bond(coupon_rate="abc")
    # comma-thousands in a Decimal field -> invalid number -> ValidationError
    with pytest.raises(ValueError):
        _bond(issue_volume="1,234.56")


def test_bond_date_parsing_formats():
    assert _bond(maturity_date="2026-05-15").maturity_date == date(2026, 5, 15)
    assert _bond(maturity_date="15.05.2026").maturity_date == date(2026, 5, 15)
    assert _bond(maturity_date="15/05/2026").maturity_date == date(2026, 5, 15)
    assert _bond(maturity_date="2026-05-15T12:00:00Z").maturity_date == date(2026, 5, 15)
    assert _bond(maturity_date=date(2026, 5, 15)).maturity_date == date(2026, 5, 15)
    assert _bond(maturity_date="").maturity_date is None
    assert _bond(maturity_date=None).maturity_date is None


def test_bond_date_garbage_rejected():
    with pytest.raises(ValueError):
        _bond(maturity_date="2026-13-45")
    with pytest.raises(ValueError):
        _bond(maturity_date="not-a-date")


def test_bond_status_normalization():
    cases = {
        "active": "active",
        "в обращении": "active",
        "торгуется": "active",
        "размещена": "active",
        "активна": "active",
        "delisted": "delisted",
        "снята": "delisted",
        "исключена": "delisted",
        "снято": "delisted",
        "matured": "matured",
        "погашена": "matured",
        "погашен": "matured",
        "offer": "offer",
        "оферта": "offer",
    }
    for raw, expected in cases.items():
        assert _bond(status=raw).status == expected, raw
    assert _bond(status=None).status == "unknown"
    assert _bond(status="совершенно иное").status == "unknown"
    assert _bond(status="В ОБРАЩЕНИИ").status == "active"


def test_bond_income_method_normalization():
    assert _bond(income_method="купонный").income_method == "coupon"
    assert _bond(income_method="купон").income_method == "coupon"
    assert _bond(income_method="дисконт").income_method == "discount"
    assert _bond(income_method="индексация").income_method == "indexed"
    assert _bond(income_method="смешанный").income_method == "mixed"
    assert _bond(income_method="").income_method is None
    assert _bond(income_method=None).income_method is None
    assert _bond(income_method="странный").income_method == "unknown"


def test_bond_int_fields_strip_separators():
    assert _bond(quantity="1 000 000").quantity == 1_000_000
    assert _bond(quantity="1,000").quantity == 1000
    assert _bond(quantity=1000.7).quantity == 1000
    assert _bond(quantity="abc").quantity is None
    assert _bond(quantity="").quantity is None
    assert _bond(term_days="365").term_days == 365
    assert _bond(issue_number="Выпуск №3").issue_number == 3
    assert _bond(issue_number="0").issue_number == 0


def test_bond_extra_fields_ignored():
    b = _bond(bogus_extra_field=123, raw={"real": "kept"})
    assert b.raw == {"real": "kept"}


def test_bond_history_yield_alias():
    from scraper.models import BondHistory

    h = BondHistory(**{"internal_id": "H-1", "date": date(2026, 1, 2), "yield": "8.2"})
    assert h.yield_ == Decimal("8.2")
    assert h.price is None
    assert h.status == "unknown"


def test_is_government_issuer_keywords():
    from scraper.models import is_government_issuer

    assert is_government_issuer("Министерство финансов Республики Беларусь") is True
    assert is_government_issuer("Минфин РБ") is True
    assert is_government_issuer("Национальный банк Республики Беларусь") is True
    assert is_government_issuer("National Bank of the Republic of Belarus") is True
    assert is_government_issuer("The Treasury of the Republic") is True
    assert is_government_issuer("ООО Ромашка") is False
    # substring matching: "финансов" in the keyword list matches any issuer name
    assert is_government_issuer("ООО Финансовые решения") is True
    assert is_government_issuer(None) is False
    assert is_government_issuer("") is False


def test_bond_instrument_ref():
    from scraper.models import bond_instrument_ref

    b = _bond(status="active")
    ref = bond_instrument_ref(b)
    assert ref.asset_class == "bond"
    assert ref.internal_id == "AUD-1"
    assert ref.currency == "USD"
    assert ref.status == "active"


# ─────────────────────────────────────────────────────────────────────────
# scraper.fx — constants and NBRB payload edges (no real network)
# ─────────────────────────────────────────────────────────────────────────


def test_fx_constants_shape():
    from scraper.fx import FX_PAIRS, METAL_IDS, TROY_OZ_PER_GRAM

    assert FX_PAIRS == {
        "USD": "USD/BYN",
        "EUR": "EUR/BYN",
        "RUB": "RUB/BYN",
        "CNY": "CNY/BYN",
    }
    assert METAL_IDS == {"XAU": 0, "XAG": 1, "XPT": 2}
    assert TROY_OZ_PER_GRAM == Decimal("31.1034768")


class _FakeResp:
    def __init__(self, json_data=None, text=""):
        self._json = json_data
        self._text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self._json

    @property
    def text(self):
        return self._text


class _FakeHttpClient:
    def __init__(self, body=None):
        self.body = body
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def get(self, url):
        self.calls.append(("get", url))
        return _FakeResp(json_data=self.body)

    async def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return _FakeResp(text=self.body)


@pytest.mark.asyncio
async def test_fetch_and_save_rates_empty_payload(monkeypatch):
    from scraper.fx import fetch_and_save_rates

    client = _FakeHttpClient(body=[])
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)
    assert await fetch_and_save_rates() == {}


@pytest.mark.asyncio
async def test_fetch_and_save_rates_zero_scale_crashes(monkeypatch):
    """Documenting current behavior: a NBRB payload with Cur_Scale=0 divides by
    zero with no guard. NBRB never emits 0 scale, but a malformed payload would
    crash the whole fetch (no row is persisted)."""
    from scraper.fx import fetch_and_save_rates

    client = _FakeHttpClient(
        body=[{"Cur_Abbreviation": "USD", "Cur_Scale": 0, "Cur_OfficialRate": "3.2"}]
    )
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)
    with pytest.raises(ZeroDivisionError):
        await fetch_and_save_rates()


@pytest.mark.asyncio
async def test_fetch_and_save_rates_zero_and_negative_stored(monkeypatch):
    """No rate sanity filter: zero/negative official rates are persisted as-is."""
    from notifications.fx_repository import latest_fx
    from scraper.fx import fetch_and_save_rates

    client = _FakeHttpClient(
        body=[
            {"Cur_Abbreviation": "USD", "Cur_Scale": 1, "Cur_OfficialRate": "0"},
            {"Cur_Abbreviation": "EUR", "Cur_Scale": 1, "Cur_OfficialRate": "-3.2"},
        ]
    )
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)
    rates = await fetch_and_save_rates()
    assert rates["USD/BYN"] == Decimal("0")
    assert rates["EUR/BYN"] == Decimal("-3.2")
    async with session_scope() as session:
        assert (await latest_fx(session, "USD/BYN")).rate == Decimal("0")


@pytest.mark.asyncio
async def test_fetch_and_save_rates_scale_division_is_exact(monkeypatch):
    from scraper.fx import fetch_and_save_rates

    client = _FakeHttpClient(
        body=[{"Cur_Abbreviation": "RUB", "Cur_Scale": 100, "Cur_OfficialRate": "340.55"}]
    )
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)
    assert await fetch_and_save_rates() == {"RUB/BYN": Decimal("3.4055")}


@pytest.mark.asyncio
async def test_fetch_and_save_rates_missing_official_skipped(monkeypatch):
    from scraper.fx import fetch_and_save_rates

    client = _FakeHttpClient(
        body=[
            {"Cur_Abbreviation": "USD", "Cur_Scale": 1},
            {"Cur_Abbreviation": "CNY", "Cur_Scale": 1, "Cur_OfficialRate": "0.45"},
        ]
    )
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)
    assert await fetch_and_save_rates() == {"CNY/BYN": Decimal("0.45")}


def test_build_soap_envelope_contains_dates_and_metal():
    from scraper.fx import _build_soap_envelope

    env = _build_soap_envelope(2, date(2026, 1, 1), date(2026, 1, 8))
    assert "<MetalId>2</MetalId>" in env
    assert "<fromDate>2026-01-01</fromDate>" in env
    assert "<toDate>2026-01-08</toDate>" in env


def test_parse_metal_prices_edges():
    from scraper.fx import _parse_metal_prices

    xml = (
        "<?xml version='1.0'?><soap:Envelope xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>"
        "<soap:Body><MetalsPrices xmlns='https://www.nbrb.by/'>"
        "<AccountPrice><Price>1.5</Price></AccountPrice>"
        "<AccountPrice><Price/></AccountPrice>"
        "<AccountPrice><Other>ignored</Other></AccountPrice>"
        "</MetalsPrices></soap:Body></soap:Envelope>"
    )
    assert _parse_metal_prices(xml) == [Decimal("1.5")]


def test_parse_metal_prices_non_numeric_raises():
    from scraper.fx import _parse_metal_prices

    with pytest.raises(InvalidOperation):
        _parse_metal_prices("<root><AccountPrice><Price>abc</Price></AccountPrice></root>")


def test_parse_metal_prices_malformed_xml_raises():
    from xml.etree.ElementTree import ParseError

    from scraper.fx import _parse_metal_prices

    with pytest.raises(ParseError):
        _parse_metal_prices("this is not xml")


@pytest.mark.asyncio
async def test_fetch_metal_prices_uses_last_price(monkeypatch):
    from scraper.fx import TROY_OZ_PER_GRAM, fetch_and_save_metal_prices

    async def fake_fetch(metal_id, from_date, to_date):
        return [Decimal("1.5"), Decimal("2.5")]

    monkeypatch.setattr("scraper.fx._fetch_metal_prices_soap", fake_fetch)
    metals = await fetch_and_save_metal_prices()
    assert set(metals) == {"XAU", "XAG", "XPT"}
    assert metals["XAU"] == Decimal("2.5") * TROY_OZ_PER_GRAM


@pytest.mark.asyncio
async def test_fetch_metal_prices_all_empty(monkeypatch):
    from scraper.fx import fetch_and_save_metal_prices

    async with session_scope() as session:
        await session.execute(delete(MetalPriceORM))
    monkeypatch.setattr("scraper.fx._fetch_metal_prices_soap", AsyncMock(return_value=[]))
    assert await fetch_and_save_metal_prices() == {}
    async with session_scope() as session:
        assert (await session.execute(select(MetalPriceORM))).scalar_one_or_none() is None


# ─────────────────────────────────────────────────────────────────────────
# notifications.fx_repository — upsert / latest / previous ordering
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fx_repository_latest_and_previous_ordering():
    from notifications.fx_repository import latest_fx, previous_fx, upsert_fx

    async with session_scope() as session:
        await session.execute(delete(FxRateORM))
        for i, rate in enumerate(["3.0", "3.1", "3.2"]):
            await upsert_fx(session, "USD/BYN", Decimal(rate))
            row = (
                await session.execute(select(FxRateORM).order_by(FxRateORM.id.desc()).limit(1))
            ).scalar_one()
            row.observed_at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i)
        await session.flush()
    async with session_scope() as session:
        latest = await latest_fx(session, "USD/BYN")
        previous = await previous_fx(session, "USD/BYN")
    assert latest.rate == Decimal("3.2")
    assert previous.rate == Decimal("3.1")


@pytest.mark.asyncio
async def test_fx_repository_missing_rows():
    from notifications.fx_repository import latest_fx, previous_fx

    async with session_scope() as session:
        assert await latest_fx(session, "GBP/BYN") is None
        assert await previous_fx(session, "GBP/BYN") is None


@pytest.mark.asyncio
async def test_metal_repository_ordering_and_missing():
    from notifications.fx_repository import latest_metal, previous_metal, upsert_metal

    async with session_scope() as session:
        await session.execute(delete(MetalPriceORM))
        for i, price in enumerate(["100", "101", "102"]):
            await upsert_metal(session, "XAU", Decimal(price))
            row = (
                await session.execute(select(MetalPriceORM).order_by(MetalPriceORM.id.desc()).limit(1))
            ).scalar_one()
            row.observed_at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i)
        await session.flush()
    async with session_scope() as session:
        assert (await latest_metal(session, "XAU")).price == Decimal("102")
        assert (await previous_metal(session, "XAU")).price == Decimal("101")
        assert await latest_metal(session, "XAG") is None


# ─────────────────────────────────────────────────────────────────────────
# scraper.pipeline — pure helpers (no network)
# ─────────────────────────────────────────────────────────────────────────


def test_d_coercion_edges():
    from scraper.pipeline import _d

    assert _d("101.5") == Decimal("101.5")
    assert _d(0) == Decimal("0")
    assert _d("12,5") is None  # Decimal() rejects comma
    assert _d("  ") is None
    assert _d(True) is None
    assert _d(None) is None


def test_periods_to_schedule_groups_sorts_skips_invalid():
    from scraper.pipeline import _periods_to_schedule

    sched = _periods_to_schedule(
        [
            {"start": "2026-03-01"},
            {"start": ""},
            {"start": None},
            {"start": "not-a-year"},
            {"start": "2026-01-15"},
            {"start": "2025-12-01"},
        ]
    )
    assert sched == {
        "2025": ["2025-12-01"],
        "2026": ["2026-01-15", "2026-03-01"],
    }


def test_periods_to_frequency_counts_window_and_caps():
    from scraper.pipeline import _periods_to_frequency

    assert (
        _periods_to_frequency(
            [{"start": "2026-01-15"}, {"start": "2026-02-15"}, {"start": "2026-03-15"}, {"start": "2026-04-15"}]
        )
        == 4
    )
    monthly = [{"start": f"2026-{m:02d}-15"} for m in range(1, 14)]
    assert _periods_to_frequency(monthly) == 12  # capped at 12
    assert _periods_to_frequency([{"start": "junk"}, {"start": ""}]) is None
    assert _periods_to_frequency([]) is None
    assert _periods_to_frequency([{"start": "2026-01-15"}]) == 1


def test_current_period_coupon_rate_happy_path():
    from scraper.pipeline import _current_period_coupon_rate

    today = date.today()
    period = {
        "start": (today - timedelta(days=5)).isoformat(),
        "end": (today + timedelta(days=5)).isoformat(),
        "amount": "40",
        "days": 182,
    }
    rate = _current_period_coupon_rate([period], "1000")
    expected = Decimal("40") / Decimal("1000") * Decimal("365") / Decimal("182") * Decimal("100")
    assert rate == expected


def test_current_period_coupon_rate_edges():
    from scraper.pipeline import _current_period_coupon_rate

    today = date.today()
    cur = {
        "start": (today - timedelta(days=5)).isoformat(),
        "end": (today + timedelta(days=5)).isoformat(),
        "amount": "40",
        "days": 182,
    }
    assert _current_period_coupon_rate([cur], None) is None
    assert _current_period_coupon_rate([cur], "0") is None
    assert _current_period_coupon_rate([], "1000") is None
    assert _current_period_coupon_rate([{"start": cur["start"], "end": cur["end"]}], "1000") is None
    assert (
        _current_period_coupon_rate(
            [{"start": cur["start"], "end": cur["end"], "amount": "abc", "days": 182}], "1000"
        )
        is None
    )
    # rate outside the sane 0.1..100 band is rejected
    assert (
        _current_period_coupon_rate(
            [{"start": cur["start"], "end": cur["end"], "amount": "2000", "days": 182}], "1000"
        )
        is None
    )


def test_current_period_coupon_rate_falls_back_to_first_amount_period():
    from scraper.pipeline import _current_period_coupon_rate

    past = {"start": "2026-01-01", "end": "2026-02-01", "amount": "40", "days": 31}
    rate = _current_period_coupon_rate([past], "1000")
    assert rate == Decimal("40") / Decimal("1000") * Decimal("365") / Decimal("31") * Decimal("100")


def test_period_days_resolution_order():
    from scraper.pipeline import _period_days

    assert _period_days({"days": "182"}) == 182
    assert _period_days({"days": 0, "start": "2026-01-01", "end": "2026-03-01"}) == 59
    assert _period_days({"days": "abc", "start": "2026-01-01", "end": "2026-03-01"}) == 59
    assert _period_days({"start": "2026-01-01", "end": "2026-01-01"}) == 365  # 0-day window
    assert _period_days({}) == 365


# ─────────────────────────────────────────────────────────────────────────
# telegram_bot.stars_payments — pricing and keyboard
# ─────────────────────────────────────────────────────────────────────────


def test_star_plans_exact_pricing_defaults(monkeypatch):
    monkeypatch.delenv("STARS_PRO", raising=False)
    monkeypatch.delenv("STARS_ENTERPRISE", raising=False)
    mod = importlib.reload(subs)
    assert mod.STAR_PLANS["pro"].stars == 150
    assert mod.STAR_PLANS["enterprise"].stars == 500
    assert mod.STAR_PLANS["pro"].duration_days == 30
    assert mod.STAR_PLANS["enterprise"].duration_days == 30
    assert mod.is_paid("pro") and mod.is_paid("enterprise")


def test_subscribe_keyboard_lists_plans_and_close():
    kb = stars_payments._subscribe_kb()
    rows = kb.inline_keyboard
    assert len(rows) == len(subs.STAR_PLANS) + 1
    for i, tier in enumerate(subs.STAR_PLANS):
        btn = rows[i][0]
        assert btn.callback_data == f"stars:pay:{tier}"
        assert subs.STAR_PLANS[tier].name in btn.text
        assert str(subs.STAR_PLANS[tier].stars) in btn.text
    assert rows[-1][0].callback_data == "stars:close"


# ─────────────────────────────────────────────────────────────────────────
# telegram_bot.stars_payments — pre-checkout validation
# ─────────────────────────────────────────────────────────────────────────


class _FakePreCheckout:
    def __init__(self, payload="", prices=None):
        self.invoice_payload = payload
        self.prices = prices
        self.answers = []

    async def answer(self, **kwargs):
        self.answers.append(kwargs)


@pytest.mark.asyncio
async def test_pre_checkout_accepts_exact_amount():
    expected = subs.STAR_PLANS["pro"].stars
    pc = _FakePreCheckout("stars_sub:pro", [SimpleNamespace(amount=expected)])
    await stars_payments.on_pre_checkout(pc)
    assert pc.answers == [{"ok": True}]


@pytest.mark.asyncio
async def test_pre_checkout_rejects_invalid_payloads():
    for payload in ("", "stars:x", "stars_subx:pro", "other:pro"):
        pc = _FakePreCheckout(payload, [SimpleNamespace(amount=150)])
        await stars_payments.on_pre_checkout(pc)
        assert pc.answers == [{"ok": False, "error_message": "Invalid subscription payload"}]


@pytest.mark.asyncio
async def test_pre_checkout_rejects_unknown_tier():
    pc = _FakePreCheckout("stars_sub:ultra", [SimpleNamespace(amount=999)])
    await stars_payments.on_pre_checkout(pc)
    assert pc.answers == [{"ok": False, "error_message": "Unknown plan tier"}]


@pytest.mark.asyncio
async def test_pre_checkout_rejects_amount_mismatch():
    expected = subs.STAR_PLANS["pro"].stars
    for total in (expected - 1, expected + 1, 0):
        pc = _FakePreCheckout("stars_sub:pro", [SimpleNamespace(amount=total)])
        await stars_payments.on_pre_checkout(pc)
        assert pc.answers == [{"ok": False, "error_message": "Price mismatch"}]


@pytest.mark.asyncio
async def test_pre_checkout_missing_prices_rejected():
    # No `prices` attribute at all -> total sums to 0 -> mismatch (unless a
    # plan costs 0 stars, which none do).
    pc = _FakePreCheckout("stars_sub:pro", None)
    await stars_payments.on_pre_checkout(pc)
    assert pc.answers == [{"ok": False, "error_message": "Price mismatch"}]


# ─────────────────────────────────────────────────────────────────────────
# telegram_bot.stars_payments — successful_payment edge cases
# ─────────────────────────────────────────────────────────────────────────


class _FakePayment:
    def __init__(self, payload, charge):
        self.invoice_payload = payload
        self.telegram_payment_charge_id = charge


class _FakeRefund:
    def __init__(self, payload, charge):
        self.invoice_payload = payload
        self.telegram_payment_charge_id = charge


class _FakeUser:
    def __init__(self, uid):
        self.id = uid


class _FakeMessage:
    def __init__(self, tg_id, payment=None, refund=None):
        self.from_user = _FakeUser(tg_id)
        self.successful_payment = payment
        self.refunded_payment = refund
        self.answers = []

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


@pytest.mark.asyncio
async def test_payment_charge_id_none_grants_each_delivery():
    """Documenting current behavior: with charge_id=None there is no dedup key,
    so every delivery re-applies the grant and STACKS the window (each extends
    from the previous expiry)."""
    tg = 800_001
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)

    await stars_payments.on_successful_payment(
        _FakeMessage(tg, _FakePayment("stars_sub:pro", None))
    )
    async with session_scope() as session:
        user = (await session.execute(select(UserORM).where(UserORM.telegram_id == tg))).scalar_one()
        expiry1 = user.subscription_expires_at
        assert user.last_charge_id is None

    await stars_payments.on_successful_payment(
        _FakeMessage(tg, _FakePayment("stars_sub:pro", None))
    )
    async with session_scope() as session:
        user = (await session.execute(select(UserORM).where(UserORM.telegram_id == tg))).scalar_one()
        expiry2 = user.subscription_expires_at
    assert expiry2 == expiry1 + timedelta(days=30)
    assert await subs.get_tier_by_telegram(tg) == "pro"


@pytest.mark.asyncio
async def test_payment_unknown_charge_id_grants_and_updates():
    tg = 800_002
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)

    msg = _FakeMessage(tg, _FakePayment("stars_sub:pro", "chg-new-1"))
    await stars_payments.on_successful_payment(msg)
    assert await subs.get_tier_by_telegram(tg) == "pro"
    assert len(msg.answers) == 1
    user = await _user_row(tg)
    assert user.last_charge_id == "chg-new-1"


@pytest.mark.asyncio
async def test_payment_charge_id_mismatch_is_not_duplicate():
    """A NEW charge id on a later purchase is a fresh payment, not a duplicate —
    it must extend and update last_charge_id."""
    tg = 800_003
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)

    await stars_payments.on_successful_payment(
        _FakeMessage(tg, _FakePayment("stars_sub:pro", "chg-old"))
    )
    msg = _FakeMessage(tg, _FakePayment("stars_sub:pro", "chg-new"))
    await stars_payments.on_successful_payment(msg)
    user = await _user_row(tg)
    assert user.last_charge_id == "chg-new"
    assert len(msg.answers) == 1


@pytest.mark.asyncio
async def test_payment_same_charge_different_tier_is_duplicate():
    """The dedup guard is keyed on charge_id only — a redelivery carrying a
    different tier with the same charge id must NOT upgrade the user."""
    tg = 800_004
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)

    await stars_payments.on_successful_payment(
        _FakeMessage(tg, _FakePayment("stars_sub:pro", "chg-dup"))
    )
    expiry_before = (await _user_row(tg)).subscription_expires_at
    msg2 = _FakeMessage(tg, _FakePayment("stars_sub:enterprise", "chg-dup"))
    await stars_payments.on_successful_payment(msg2)
    user = await _user_row(tg)
    assert user.subscription_tier == "pro"  # NOT upgraded to enterprise
    assert user.subscription_expires_at == expiry_before  # window not re-extended
    assert len(msg2.answers) == 0


@pytest.mark.asyncio
async def test_payment_user_not_found_creates_and_grants():
    tg = 800_005
    msg = _FakeMessage(tg, _FakePayment("stars_sub:enterprise", "chg-first"))
    await stars_payments.on_successful_payment(msg)
    assert await subs.get_tier_by_telegram(tg) == "enterprise"
    user = await _user_row(tg)
    assert user.last_charge_id == "chg-first"
    assert len(msg.answers) == 1


@pytest.mark.asyncio
async def test_payment_empty_payload_ignored():
    tg = 800_006
    msg = _FakeMessage(tg, _FakePayment("", "chg-x"))
    await stars_payments.on_successful_payment(msg)
    assert await subs.get_tier_by_telegram(tg) == "free"
    assert len(msg.answers) == 0


# ─────────────────────────────────────────────────────────────────────────
# telegram_bot.stars_payments — refunded_payment edge cases
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refund_charge_id_mismatch_does_not_revoke():
    tg = 800_007
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)
    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-a")

    msg = _FakeMessage(tg, refund=_FakeRefund("stars_sub:pro", "chg-b"))
    await stars_payments.on_refunded_payment(msg)
    assert await subs.get_tier_by_telegram(tg) == "pro"
    user = await _user_row(tg)
    assert user.last_charge_id == "chg-a"


@pytest.mark.asyncio
async def test_refund_without_charge_id_revokes_valid_stars_subscription():
    """Documenting current behavior (and a money-safety risk): a refund webhook
    that carries NO telegram_payment_charge_id revokes a valid Stars-paid
    subscription unconditionally (charge_id=None skips the match check and the
    channel is 'stars'). See report — this is the source's stated intent
    ('or no id given'), but any refund webhook missing the id kills access."""
    tg = 800_008
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)
    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-a")
    assert await subs.get_tier_by_telegram(tg) == "pro"

    msg = _FakeMessage(tg, refund=_FakeRefund("stars_sub:pro", None))
    await stars_payments.on_refunded_payment(msg)
    assert await subs.get_tier_by_telegram(tg) == "free"
    user = await _user_row(tg)
    assert user.subscription_expires_at is None
    assert user.last_charge_id is None


# ─────────────────────────────────────────────────────────────────────────
# telegram_bot.subscriptions — clear logic
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_charge_none_revokes_stars_subscription():
    tg = 800_010
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)
    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-x")
    assert await subs.get_tier_by_telegram(tg) == "pro"

    await subs.clear_subscription_by_telegram(tg, charge_id=None)
    assert await subs.get_tier_by_telegram(tg) == "free"
    user = await _user_row(tg)
    assert user.subscription_tier == "free"
    assert user.subscription_expires_at is None
    assert user.payment_channel is None
    assert user.last_charge_id is None


@pytest.mark.asyncio
async def test_clear_charge_mismatch_keeps_subscription():
    tg = 800_011
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)
    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-1")
    expiry = (await _user_row(tg)).subscription_expires_at

    await subs.clear_subscription_by_telegram(tg, charge_id="chg-2")
    assert await subs.get_tier_by_telegram(tg) == "pro"
    user = await _user_row(tg)
    assert user.subscription_expires_at == expiry


@pytest.mark.asyncio
async def test_clear_unknown_user_noop():
    await subs.clear_subscription_by_telegram(800_012, charge_id="chg-1")
    assert await subs.get_tier_by_telegram(800_012) == "free"


@pytest.mark.asyncio
async def test_clear_yookassa_channel_immune_even_matching_charge():
    """Cross-channel protection: a Stars refund must not cancel a YooKassa-paid
    window, even when the charge id matches last_charge_id."""
    tg = 800_013
    async with session_scope() as session:
        user = await subs.get_or_create_user_by_telegram(session, tg)
        user.trial_end = _now() - timedelta(days=1)
        user.subscription_tier = "pro"
        user.payment_channel = "yookassa"
        user.subscription_expires_at = _now() + timedelta(days=40)
        user.last_charge_id = "yk-1"
        await session.flush()

    await subs.clear_subscription_by_telegram(tg, charge_id="yk-1")
    assert await subs.get_tier_by_telegram(tg) == "pro"
    user = await _user_row(tg)
    assert user.payment_channel == "yookassa"
    assert user.last_charge_id == "yk-1"


@pytest.mark.asyncio
async def test_clear_yookassa_channel_immune_without_charge_id():
    tg = 800_014
    async with session_scope() as session:
        user = await subs.get_or_create_user_by_telegram(session, tg)
        user.trial_end = _now() - timedelta(days=1)
        user.subscription_tier = "pro"
        user.payment_channel = "yookassa"
        user.subscription_expires_at = _now() + timedelta(days=40)
        await session.flush()

    await subs.clear_subscription_by_telegram(tg, charge_id=None)
    assert await subs.get_tier_by_telegram(tg) == "pro"


@pytest.mark.asyncio
async def test_clear_with_charge_id_when_no_last_charge_revokes():
    """charge_id given but the user never recorded one -> the match check is
    skipped and the stars-channel subscription is revoked."""
    tg = 800_015
    async with session_scope() as session:
        user = await subs.get_or_create_user_by_telegram(session, tg)
        user.trial_end = _now() - timedelta(days=1)
        user.subscription_tier = "pro"
        user.subscription_expires_at = _now() + timedelta(days=10)
        user.payment_channel = "stars"
        user.last_charge_id = None
        await session.flush()

    await subs.clear_subscription_by_telegram(tg, charge_id="chg-whatever")
    assert await subs.get_tier_by_telegram(tg) == "free"


# ─────────────────────────────────────────────────────────────────────────
# telegram_bot.subscriptions — set_tier_by_telegram duration math
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_tier_extends_from_existing_expiry():
    tg = 800_020
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)

    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-1")
    expiry1 = (await _user_row(tg)).subscription_expires_at
    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-2")
    expiry2 = (await _user_row(tg)).subscription_expires_at
    # Second purchase extends from the later of now / existing expiry → +30d
    assert expiry2 == expiry1 + timedelta(days=30)


@pytest.mark.asyncio
async def test_set_tier_expired_window_starts_from_now():
    tg = 800_021
    async with session_scope() as session:
        user = await subs.get_or_create_user_by_telegram(session, tg)
        user.trial_end = _now() - timedelta(days=1)
        user.subscription_tier = "pro"
        user.payment_channel = "stars"
        user.subscription_expires_at = _now() - timedelta(days=10)
        await session.flush()

    before = _now()
    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-new")
    expiry = subs._as_aware((await _user_row(tg)).subscription_expires_at)
    diff = expiry - before
    assert timedelta(days=30) <= diff < timedelta(days=30, seconds=5)


@pytest.mark.asyncio
async def test_set_tier_paid_without_duration_is_indefinite():
    """Documenting current behavior (money-safety risk): granting a paid tier
    with duration_days=None leaves subscription_expires_at None, and
    effective_tier treats an unexpired paid tier with no expiry as PERMANENT."""
    tg = 800_022
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)

    applied = await subs.set_tier_by_telegram(tg, "pro", charge_id="chg-x")
    assert applied is True
    user = await _user_row(tg)
    assert user.subscription_expires_at is None
    assert await subs.get_tier_by_telegram(tg) == "pro"


@pytest.mark.asyncio
async def test_set_tier_downgrade_to_free_clears_window():
    tg = 800_023
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)
    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-1")

    applied = await subs.set_tier_by_telegram(tg, "free", charge_id="chg-2")
    assert applied is True
    user = await _user_row(tg)
    assert user.subscription_tier == "free"
    assert user.subscription_expires_at is None
    assert user.payment_channel is None
    assert user.last_charge_id == "chg-2"
    assert await subs.get_tier_by_telegram(tg) == "free"


@pytest.mark.asyncio
async def test_set_tier_duplicate_does_not_mutate():
    tg = 800_024
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)
    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-dup")
    expiry = (await _user_row(tg)).subscription_expires_at

    assert await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-dup") is False
    user = await _user_row(tg)
    assert user.subscription_expires_at == expiry
    assert user.subscription_tier == "pro"


@pytest.mark.asyncio
async def test_set_tier_stars_keeps_longer_yookassa_window():
    """A Stars purchase must not overwrite a YooKassa-paid window that still
    runs past the new one (later expiry owns the record).

    (Regression: the cross-channel guard used to compare ``base >= new_expiry``
    where ``new_expiry = base + duration_days`` — never true — so a Stars
    purchase always hijacked the YooKassa channel and a later Stars refund
    revoked YooKassa-paid days.)"""
    tg = 800_025
    base = _now() + timedelta(days=40)
    async with session_scope() as session:
        user = await subs.get_or_create_user_by_telegram(session, tg)
        user.trial_end = _now() - timedelta(days=1)
        user.subscription_tier = "pro"
        user.payment_channel = "yookassa"
        user.subscription_expires_at = base
        user.last_charge_id = "yk-1"
        await session.flush()

    applied = await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="st-1")
    assert applied is True
    user = await _user_row(tg)
    assert subs._as_aware(user.subscription_expires_at) == base
    assert user.payment_channel == "yookassa"
    assert user.last_charge_id == "st-1"
    assert await subs.get_tier_by_telegram(tg) == "pro"


@pytest.mark.asyncio
async def test_set_tier_stars_overwrites_shorter_yookassa_window():
    tg = 800_026
    async with session_scope() as session:
        user = await subs.get_or_create_user_by_telegram(session, tg)
        user.trial_end = _now() - timedelta(days=1)
        user.subscription_tier = "pro"
        user.payment_channel = "yookassa"
        user.subscription_expires_at = _now() + timedelta(days=10)
        await session.flush()

    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="st-1")
    user = await _user_row(tg)
    assert subs._as_aware(user.subscription_expires_at) > _now() + timedelta(days=39)
    assert user.payment_channel == "stars"


# ─────────────────────────────────────────────────────────────────────────
# telegram_bot.subscriptions — effective tier, days left, account status
# ─────────────────────────────────────────────────────────────────────────


def test_effective_tier_unknown_tier_passthrough():
    """Unknown tier strings are not paid, so they pass through as-is when there
    is no active trial (gating still ranks them as free)."""
    assert subs.effective_tier("gold", None) == "gold"
    assert subs.effective_tier("gold", _now() - timedelta(days=1)) == "gold"


def test_effective_tier_paid_without_expiry_is_active():
    assert subs.effective_tier("pro", None) == "pro"
    assert subs.effective_tier("enterprise", None) == "enterprise"


def test_effective_tier_trial_grants_pro_after_paid_lapse():
    future = _now() + timedelta(days=2)
    past = _now() - timedelta(days=1)
    assert subs.effective_tier("pro", past, trial_end=future) == "pro"
    assert subs.effective_tier("free", None, trial_end=future) == "pro"
    assert subs.effective_tier("free", None, trial_end=past) == "free"


def test_days_left_edges():
    assert subs._days_left(None) is None
    assert subs._days_left(_now() - timedelta(days=1)) == 0
    assert subs._days_left(_now() + timedelta(seconds=1)) == 1
    assert subs._days_left(_now() + timedelta(days=1)) == 1
    assert subs._days_left(_now() + timedelta(days=2, hours=12)) == 3


@pytest.mark.asyncio
async def test_get_account_status_trial_then_expired():
    tg = 800_030
    status = await subs.get_account_status(tg)
    assert status.tier == "pro"
    assert status.is_trial is True
    assert status.days_left == subs.TRIAL_DAYS

    async with session_scope() as session:
        user = (await session.execute(select(UserORM).where(UserORM.telegram_id == tg))).scalar_one()
        user.trial_end = _now() - timedelta(days=1)
        await session.flush()
    status = await subs.get_account_status(tg)
    assert status.tier == "free"
    assert status.is_trial is False
    assert status.days_left is None


@pytest.mark.asyncio
async def test_get_account_status_paid_is_not_trial():
    tg = 800_031
    async with session_scope() as session:
        await subs.get_or_create_user_by_telegram(session, tg)
    await _expire_trial_async(tg)
    await subs.set_tier_by_telegram(tg, "pro", duration_days=30, charge_id="chg-1")

    status = await subs.get_account_status(tg)
    assert status.tier == "pro"
    assert status.is_trial is False
    assert status.expires_at is not None
    assert status.days_left == 30


# ─────────────────────────────────────────────────────────────────────────
# telegram_bot.subscriptions — referrer logic
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_attach_referrer_bonus_and_guards():
    inv_tg = 800_040
    ref_tg = 800_041
    async with session_scope() as session:
        inviter = await subs.get_or_create_user_by_telegram(session, ref_tg)
        await subs.get_or_create_user_by_telegram(session, inv_tg)
        ref_id = inviter.id

    assert await subs.attach_referrer(inv_tg, 0) is False
    assert await subs.attach_referrer(inv_tg, ref_id) is True

    # self-referral / missing referrer / already set → no-op
    inviter_user = await _user_row(ref_tg)
    invitee_user = await _user_row(inv_tg)
    assert await subs.attach_referrer(inv_tg, invitee_user.id) is False  # self
    assert await subs.attach_referrer(inv_tg, 9_999_999) is False  # missing referrer row
    assert await subs.attach_referrer(inv_tg, ref_id) is False  # already set

    # both active trials extended by REFERRAL_BONUS_DAYS (default 3)
    bonus = timedelta(days=3)
    assert subs._as_aware(inviter_user.trial_end) - subs._as_aware(
        subs._now() + timedelta(days=subs.TRIAL_DAYS)
    ) >= bonus - timedelta(seconds=5)
    assert subs._as_aware(invitee_user.trial_end) - subs._as_aware(
        subs._now() + timedelta(days=subs.TRIAL_DAYS)
    ) >= bonus - timedelta(seconds=5)


@pytest.mark.asyncio
async def test_attach_referrer_extends_paid_window_not_trial_from_scratch():
    ref_tg = 800_042
    inv_tg = 800_043
    async with session_scope() as session:
        referrer = await subs.get_or_create_user_by_telegram(session, ref_tg)
        referrer.trial_end = None  # trial consumed / never active
        referrer.subscription_tier = "pro"
        referrer.subscription_expires_at = _now() + timedelta(days=5)
        await session.flush()
        ref_id = referrer.id

    await subs.attach_referrer(inv_tg, ref_id)
    referrer = await _user_row(ref_tg)
    # paid window extended by 3 days (base was captured slightly before _now())
    assert subs._as_aware(referrer.subscription_expires_at) >= _now() + timedelta(days=8) - timedelta(
        seconds=5
    )
    # trial was NOT re-armed from scratch
    assert referrer.trial_end is None


# ─────────────────────────────────────────────────────────────────────────
# api gating — users table is the source of truth (no SubscriptionORM row)
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gating_uses_users_table_not_subscription_row():
    """A user with subscription_tier='pro' in users but NO SubscriptionORM row
    is still gated as pro — gating never consults the subscriptions table."""
    from api.access_control import _get_user_tier

    async with session_scope() as session:
        await session.execute(delete(UserORM).where(UserORM.telegram_id.in_([800_050, 800_051])))
        pro = UserORM(
            email="audit_gate_pro@local",
            name="Gate Pro",
            telegram_id=800_050,
            subscription_tier="pro",
            subscription_expires_at=_now() + timedelta(days=30),
            trial_end=None,
            role="user",
            is_active=True,
            is_verified=False,
        )
        expired = UserORM(
            email="audit_gate_expired@local",
            name="Gate Expired",
            telegram_id=800_051,
            subscription_tier="pro",
            subscription_expires_at=_now() - timedelta(days=1),
            trial_end=None,
            role="user",
            is_active=True,
            is_verified=False,
        )
        session.add_all([pro, expired])
        await session.flush()

        assert (
            await session.execute(
                select(SubscriptionORM).where(SubscriptionORM.user_id == pro.id)
            )
        ).first() is None  # no sub row for this user
        assert await _get_user_tier(session, pro.id) == "pro"
        assert await _get_user_tier(session, expired.id) == "free"  # expiry-aware
        assert await _get_user_tier(session, 9_000_000) is None  # no user row → None
