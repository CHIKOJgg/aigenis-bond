"""Persisted issuer financials extracted from public reports.

Real-data layer behind the issuer ratings (scoring/issuer_risk.py): each row is
one reporting period for one issuer, with the key figures parsed by
scoring/financials.py and the resulting credit signal.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from scraper.orm._base import Base


def _col() -> Mapped[float | None]:  # type: ignore[valid-type]
    return mapped_column(Numeric(24, 4), nullable=True)


class IssuerFinancialsORM(Base):
    """One reporting period of parsed issuer financials (figures in ``currency``)."""

    __tablename__ = "issuer_financials"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    issuer: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    period: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    period_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)

    revenue: Mapped[float | None] = _col()
    net_income: Mapped[float | None] = _col()
    ebitda: Mapped[float | None] = _col()
    assets: Mapped[float | None] = _col()
    equity: Mapped[float | None] = _col()
    liabilities: Mapped[float | None] = _col()
    current_assets: Mapped[float | None] = _col()
    current_liabilities: Mapped[float | None] = _col()
    debt: Mapped[float | None] = _col()

    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    credit_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    basis: Mapped[str | None] = mapped_column(Text, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
