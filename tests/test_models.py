from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from scraper.models import (
    Bond,
    BondDailyAccrual,
    BondHistory,
    Stock,
    StockHistory,
    bond_instrument_ref,
    is_government_issuer,
    stock_instrument_ref,
)

BASE_BOND = {
    "internal_id": "B1",
    "name": "Test bond",
    "currency": "BYN",
    "fetched_at": datetime(2024, 1, 1),
}


def make_bond(**kw):
    return Bond(**{**BASE_BOND, **kw})


BASE_STOCK = {
    "internal_id": "S1",
    "secid": "GAZP",
    "name": "Test stock",
    "fetched_at": datetime(2024, 1, 1),
}


def make_stock(**kw):
    return Stock(**{**BASE_STOCK, **kw})


def test_to_decimal_empty_and_invalid():
    assert make_bond(price="   ").price is None
    with pytest.raises(ValidationError):
        make_bond(price="not-a-number")
    with pytest.raises(ValidationError):
        make_bond(price=object())


def test_bond_currency_required_and_normalized():
    with pytest.raises(ValidationError):
        make_bond(currency=None)
    assert make_bond(currency="доллар").currency == "USD"
    assert make_bond(currency="золото").currency == "XAU"
    assert make_bond(currency="usd").currency == "USD"


def test_bond_date_formats():
    assert make_bond(maturity_date="2024-05-01").maturity_date == date(2024, 5, 1)
    assert make_bond(maturity_date="01.05.2024").maturity_date == date(2024, 5, 1)
    assert make_bond(maturity_date="01/05/2024").maturity_date == date(2024, 5, 1)
    assert make_bond(maturity_date="2024-05-01T10:30:00").maturity_date == date(2024, 5, 1)
    assert make_bond(maturity_date="2024-05-01T10:30:00Z").maturity_date == date(2024, 5, 1)
    assert make_bond(maturity_date="2024-05-01T10:30:00.123456+03:00").maturity_date == date(
        2024, 5, 1
    )
    with pytest.raises(ValidationError):
        make_bond(maturity_date="not-a-date")
    assert make_bond(maturity_date="").maturity_date is None
    assert make_bond(maturity_date=date(2024, 5, 1)).maturity_date == date(2024, 5, 1)


def test_bond_status_normalization():
    assert make_bond(status=None).status == "unknown"
    assert make_bond(status="В ОБРАЩЕНИИ").status == "active"
    assert make_bond(status="снята").status == "delisted"
    assert make_bond(status="погашена").status == "matured"
    assert make_bond(status="оферта").status == "offer"
    assert make_bond(status="странный").status == "unknown"


def test_bond_income_method():
    assert make_bond(income_method="купонный").income_method == "coupon"
    assert make_bond(income_method="Дисконтный").income_method == "discount"
    assert make_bond(income_method="индексируемый").income_method == "indexed"
    assert make_bond(income_method="смешанный").income_method == "mixed"
    assert make_bond(income_method="непонятно").income_method == "unknown"
    assert make_bond(income_method="").income_method is None


def test_bond_indexation_currency():
    assert make_bond(indexation_currency="").indexation_currency is None
    assert make_bond(indexation_currency=" usd ").indexation_currency == "USD"


def test_bond_int_fields():
    assert make_bond(quantity=None).quantity is None
    assert make_bond(quantity=10).quantity == 10
    assert make_bond(quantity=10.7).quantity == 10
    assert make_bond(quantity="1 000 000").quantity == 1000000
    assert make_bond(quantity="1,000").quantity == 1000
    assert make_bond(quantity="approx").quantity is None
    assert make_bond(term_days="365").term_days == 365
    assert make_bond(issue_number=7).issue_number == 7
    assert make_bond(issue_number="Выпуск № 3").issue_number == 3
    assert make_bond(issue_number="N/A").issue_number is None


def test_stock_currency_and_int():
    assert make_stock(currency=None).currency == "RUB"
    assert make_stock(currency="sur").currency == "RUB"
    assert make_stock(lot_size="abc").lot_size is None
    assert make_stock(lot_size=100).lot_size == 100


def test_stock_status_normalization():
    assert make_stock(status=None).status == "unknown"
    assert make_stock(status="допущен").status == "active"
    assert make_stock(status="исключён").status == "delisted"
    assert make_stock(status="приостановлен").status == "suspended"
    assert make_stock(status="что-то ещё").status == "unknown"


def test_stock_history():
    h = StockHistory(
        internal_id="S1",
        date="2024-01-02",
        volume=None,
        open_price="12,5",
    )
    assert h.date == date(2024, 1, 2)
    assert h.open_price == Decimal("12.5")
    assert h.volume is None
    assert StockHistory(internal_id="S1", date=date(2024, 1, 2), volume="bad").volume is None
    assert StockHistory(internal_id="S1", date="2024-01-02", status=None).status == "unknown"


def test_bond_history():
    b = BondHistory(internal_id="B1", date="2024-01-02", price="100,0", yield_="9,5")
    assert b.date == date(2024, 1, 2)
    assert b.price == Decimal("100.0")
    assert b.yield_ == Decimal("9.5")
    assert BondHistory(internal_id="B1", date="2024-01-02", status=None).status == "unknown"


def test_bond_daily_accrual():
    a = BondDailyAccrual(internal_id="B1", date="2024-01-02", accrued="1,5")
    assert a.date == date(2024, 1, 2)
    assert a.accrued == Decimal("1.5")


def test_is_government_issuer():
    assert not is_government_issuer(None)
    assert not is_government_issuer("")
    assert is_government_issuer("Министерство финансов")
    assert not is_government_issuer("Рога и копыта ООО")


def test_instrument_refs():
    b = make_bond()
    r = bond_instrument_ref(b)
    assert r.asset_class == "bond"
    assert r.internal_id == "B1"
    s = make_stock()
    r2 = stock_instrument_ref(s)
    assert r2.asset_class == "equity"
    assert r2.internal_id == "S1"
