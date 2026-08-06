"""Aigenis integration models: instrument mapping and snapshot lineage.

- ``instrument_map``   — версионированная таблица соответствия идентификаторов:
  ``aigenis_instrument_id`` ↔ ``isin`` ↔ ``external_ticker`` ↔ ``analytics_internal_id``.
  ISIN — предпочтительный стабильный ключ (Finalplan §13.6, plan item 5.14).
- ``snapshot_lineage`` — происхождение каждого ingestion snapshot:
  source, license/contract_id, as_of, ingestion_run, quality_status (plan item 5.6).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from scraper.orm._base import Base


class InstrumentMapORM(Base):
    __tablename__ = "instrument_map"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aigenis_instrument_id: Mapped[str] = mapped_column(String(64), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_ticker: Mapped[str | None] = mapped_column(String(64), nullable=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    analytics_internal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # active | delisted | renamed | not_covered
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_instrument_map_aigenis_id_version",
            "aigenis_instrument_id",
            "version",
            unique=True,
        ),
        Index("ix_instrument_map_aigenis_id", "aigenis_instrument_id"),
        Index("ix_instrument_map_isin", "isin"),
        Index("ix_instrument_map_internal_id", "analytics_internal_id"),
    )


class SnapshotLineageORM(Base):
    """Происхождение данных для каждого ingestion snapshot (plan item 5.6)."""

    __tablename__ = "snapshot_lineage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    license_contract_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingestion_run: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ok | warning | critical
    quality_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ok")
    market: Mapped[str | None] = mapped_column(String(8), nullable=True)
    rows_processed: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_snapshot_lineage_run", "ingestion_run"),
        Index("ix_snapshot_lineage_as_of", "as_of"),
    )
