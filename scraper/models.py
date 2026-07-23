from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Currency = Literal["USD", "BYN", "EUR", "RUB", "XAU", "XAG", "XPT"]
CouponFrequency = Literal[1, 2, 4, 12]
Amortization = Literal["none", "partial", "full"]
BondStatus = Literal["active", "delisted", "matured", "offer", "unknown"]
IncomeMethod = Literal["coupon", "discount", "indexed", "mixed", "unknown"]
StockStatus = Literal["active", "delisted", "suspended", "unknown"]
StockBoard = Literal["TQBR", "TQOD", "TQDE", "TQIY"]

_STOCK_CURRENCY_ALIASES = {
    "SUR": "RUB",
    "RUR": "RUB",
    "RUB": "RUB",
    "USD": "USD",
    "EUR": "EUR",
    "BYN": "BYN",
}


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace(",", ".").replace(" ", "").replace("%", "")
        if not cleaned:
            return None
        try:
            return Decimal(cleaned)
        except Exception as e:
            raise ValueError(f"Cannot parse decimal from {value!r}") from e
    raise ValueError(f"Unsupported decimal value: {value!r}")


class Bond(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    internal_id: str = Field(..., description="Внутренний id Aigenis (PK)")
    name: str
    issuer: str | None = None
    issuer_logo: str | None = None
    currency: Currency
    nominal: Decimal | None = None

    coupon_rate: Decimal | None = None
    coupon_frequency: CouponFrequency | None = None

    maturity_date: date | None = None
    price: Decimal | None = None
    yield_to_maturity: Decimal | None = None

    amortization: Amortization | None = None
    offer_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None

    isin: str | None = None
    status: BondStatus = "unknown"
    is_government: bool = False

    registration_number: str | None = Field(None, description="Номер государственной регистрации")
    issue_volume: Decimal | None = Field(None, description="Объём эмиссии")
    issue_number: int | None = Field(None, description="Номер выпуска")
    quantity: int | None = Field(None, description="Количество облигаций в выпуске")
    income_method: IncomeMethod | None = Field(None, description="Способ выплаты дохода")
    in_stock: bool | None = Field(None, description="В наличии (data-stock)")
    guarantor: str | None = Field(None, description="Организация/гарант")
    maturity_term_text: str | None = Field(
        None, description="Срок погашения (текст, из data-vterm)"
    )
    coupon_description: str | None = Field(
        None, description="Полное описание купона (ставка + периодичность)"
    )
    coupon_schedule: dict[str, list[str]] | None = Field(
        None, description="График купонных выплат по годам"
    )
    indexation_currency: str | None = Field(
        None, description="Валюта индексации (для индексируемых облигаций)"
    )
    exchange_rate_on_start: Decimal | None = Field(
        None, description="Курс валюты на дату начала обращения"
    )
    term_days: int | None = Field(None, description="Срок обращения в днях")

    raw: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, v: Any) -> str:
        if v is None:
            raise ValueError("currency is required")
        s = str(v).strip().upper()
        mapping = {
            "ДОЛЛАР": "USD",
            "ДОЛЛАР США": "USD",
            "ДОЛЛАРЫ": "USD",
            "РУБЛЬ": "BYN",
            "БЕЛОРУССКИЙ РУБЛЬ": "BYN",
            "ЕВРО": "EUR",
            "ЗОЛОТО": "XAU",
            "GOLD": "XAU",
            "СЕРЕБРО": "XAG",
            "ПЛАТИНА": "XPT",
        }
        return mapping.get(s, s)

    @field_validator(
        "coupon_rate",
        "yield_to_maturity",
        "price",
        "nominal",
        "issue_volume",
        "exchange_rate_on_start",
        mode="before",
    )
    @classmethod
    def _decimal_field(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)

    @field_validator("maturity_date", "offer_date", "start_date", "end_date", mode="before")
    @classmethod
    def _date_field(cls, v: Any) -> date | None:
        if v is None or v == "":
            return None
        if isinstance(v, date):
            return v
        s = str(v).strip()
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(s[:19], fmt[:19] if "T" in fmt else fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except Exception as e:
            raise ValueError(f"Cannot parse date from {v!r}") from e

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v: Any) -> str:
        if v is None:
            return "unknown"
        s = str(v).strip().lower()
        if s in {"active", "в обращении", "торгуется", "размещена", "активна"}:
            return "active"
        if s in {"delisted", "снята", "исключена", "снято"}:
            return "delisted"
        if s in {"matured", "погашена", "погашен"}:
            return "matured"
        if s in {"offer", "оферта"}:
            return "offer"
        return "unknown"

    @field_validator("income_method", mode="before")
    @classmethod
    def _normalize_income_method(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        s = str(v).strip().lower()
        if "купон" in s:
            return "coupon"
        if "дисконт" in s:
            return "discount"
        if "индекс" in s:
            return "indexed"
        if "смешан" in s:
            return "mixed"
        return "unknown"

    @field_validator("indexation_currency", mode="before")
    @classmethod
    def _normalize_indexation_currency(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip().upper()

    @field_validator("quantity", "term_days", mode="before")
    @classmethod
    def _int_field(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        s = str(v).strip()
        m = re.search(r"(\d+)", s)
        if m:
            return int(m.group(1))
        return None

    @field_validator("issue_number", mode="before")
    @classmethod
    def _parse_issue_number(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, int):
            return v
        s = str(v).strip()
        m = re.search(r"(\d+)", s)
        if m:
            return int(m.group(1))
        return None


class Stock(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    internal_id: str = Field(..., description="Внутренний id Aigenis (PK), MOEX_{SECID}")
    secid: str = Field(..., description="MOEX SECID (ticker)")
    name: str
    isin: str | None = None
    issuer: str | None = None
    board: str = "TQBR"
    currency: Currency = "RUB"
    lot_size: int | None = None
    prev_price: Decimal | None = None
    price: Decimal | None = None
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    close_price: Decimal | None = None
    volume: int | None = None
    value_traded: Decimal | None = None
    market_capitalization: Decimal | None = None
    pe_ratio: Decimal | None = None
    pbr_ratio: Decimal | None = None
    dividend_yield: Decimal | None = None
    earnings_per_share: Decimal | None = None
    sector: str | None = None
    status: StockStatus = "unknown"
    raw: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, v: Any) -> str:
        if v is None:
            return "RUB"
        s = str(v).strip().upper()
        return _STOCK_CURRENCY_ALIASES.get(s, s)

    @field_validator(
        "price", "prev_price", "open_price", "high_price", "low_price", "close_price",
        "market_capitalization", "pe_ratio", "pbr_ratio", "dividend_yield",
        "earnings_per_share", "value_traded",
        mode="before",
    )
    @classmethod
    def _decimal_field(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)

    @field_validator("lot_size", "volume", mode="before")
    @classmethod
    def _int_field(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        try:
            return int(float(str(v)))
        except (ValueError, TypeError):
            return None

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v: Any) -> str:
        if v is None:
            return "unknown"
        s = str(v).strip().lower()
        if s in {"active", "торгуется", "допущен"}:
            return "active"
        if s in {"delisted", "снят", "исключён", "исключен"}:
            return "delisted"
        if s in {"suspended", "приостановлен"}:
            return "suspended"
        return "unknown"


class StockHistory(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    internal_id: str
    date: date
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    close_price: Decimal | None = None
    volume: int | None = None
    value_traded: Decimal | None = None
    weighted_avg_price: Decimal | None = None
    status: StockStatus = "unknown"

    @field_validator("open_price", "high_price", "low_price", "close_price",
                      "value_traded", "weighted_avg_price", mode="before")
    @classmethod
    def _decimal_field(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)

    @field_validator("volume", mode="before")
    @classmethod
    def _int_field(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        try:
            return int(float(str(v)))
        except (ValueError, TypeError):
            return None

    @field_validator("date", mode="before")
    @classmethod
    def _date_field(cls, v: Any) -> date:
        if isinstance(v, date):
            return v
        s = str(v).strip()
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v: Any) -> str:
        if v is None:
            return "unknown"
        return str(v).strip().lower() or "unknown"


class BondHistory(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    internal_id: str
    date: date
    price: Decimal | None = None
    yield_: Decimal | None = Field(None, alias="yield")
    coupon: Decimal | None = None
    status: BondStatus = "unknown"

    @field_validator("price", "yield_", "coupon", mode="before")
    @classmethod
    def _decimal_field(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)

    @field_validator("date", mode="before")
    @classmethod
    def _date_field(cls, v: Any) -> date:
        if isinstance(v, date):
            return v
        s = str(v).strip()
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v: Any) -> str:
        if v is None:
            return "unknown"
        return str(v).strip().lower() or "unknown"


class BondDailyAccrual(BaseModel):
    model_config = ConfigDict(extra="ignore")

    internal_id: str
    date: date
    accrued: Decimal | None = None
    total_value: Decimal | None = None

    @field_validator("accrued", "total_value", mode="before")
    @classmethod
    def _decimal_field(cls, v: Any) -> Decimal | None:
        return _to_decimal(v)

    @field_validator("date", mode="before")
    @classmethod
    def _date_field(cls, v: Any) -> date:
        if isinstance(v, date):
            return v
        s = str(v).strip()
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()


_GOVERNMENT_ISSUER_KEYWORDS = (
    "министерство",
    "минфин",
    "национальн",
    "народный банк",
    "central bank",
    "national bank",
    "treasury",
    "казначей",
    "government",
    "правительств",
    "республик",
    "государствен",
    "municipal",
    "облисполком",
    "мингори",
    "финансов",
)


def is_government_issuer(name: str | None) -> bool:
    """Heuristic: does the issuer name look like a sovereign / central-bank /

    government body? Used to exclude risk-free issuers from credit-spread shocks
    and repo haircuts. Best-effort, based on well-known keywords.
    """
    if not name:
        return False
    low = name.lower()
    return any(k in low for k in _GOVERNMENT_ISSUER_KEYWORDS)
