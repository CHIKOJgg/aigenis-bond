"""Repo: простое моделирование сделки РЕПО (collateral + cash + interest)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from desk.models import RepoDeal
from scraper.models import Bond


def repo_deal(
    bond: Bond,
    *,
    notional: Decimal,
    haircut_pct: float,
    repo_rate_pct: float,
    tenor_days: int,
    asof: date | None = None,
) -> RepoDeal:
    """Смоделировать сделку РЕПО: сколько кэша дадим под залог облигации."""
    asof = asof or date.today()
    collateral_value = notional * (Decimal("1") - Decimal(str(haircut_pct)) / Decimal("100"))
    accrued = collateral_value * Decimal(str(repo_rate_pct)) / Decimal("100") * Decimal(tenor_days) / Decimal("365")
    return RepoDeal(
        internal_id=bond.internal_id,
        notional=notional,
        haircut_pct=haircut_pct,
        repo_rate_pct=repo_rate_pct,
        tenor_days=tenor_days,
        cash_lent=collateral_value.quantize(Decimal("0.01")),
        collateral_value=notional.quantize(Decimal("0.01")),
        accrued_interest=accrued.quantize(Decimal("0.01")),
        asof_date=asof,
    )


def haircut_by_issuer(issuer: str | None) -> float:
    """Простая эвристика: государство — 1%, банки — 3%, прочие — 5%."""
    if not issuer:
        return 5.0
    s = issuer.lower()
    if any(k in s for k in ("министерство", "республика", "государ", "treasury", "government")):
        return 1.0
    if "bank" in s or "банк" in s:
        return 3.0
    return 5.0
