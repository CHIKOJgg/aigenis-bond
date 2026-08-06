"""Machine-learning models: versions, training runs, predictions."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scraper.orm._base import Base


class ModelVersionORM(Base):
    __tablename__ = "model_versions"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    train_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    __table_args__ = (Index("ix_model_versions_kind", "kind"),)


class TrainingRunORM(Base):
    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="running")
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    __table_args__ = (
        Index("ix_training_runs_started", "started_at"),
        Index("ix_training_runs_version", "version"),
    )


class PredictionORM(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    internal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    asof_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_ytm: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    predicted_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    predicted_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    feature_importance: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    explanation: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_predictions_internal_id", "internal_id"),
        Index("ix_predictions_asof", "asof_date"),
        Index("ix_predictions_decision", "decision"),
        UniqueConstraint(
            "internal_id",
            "asof_date",
            "model_version",
            "kind",
            name="uq_predictions_key",
        ),
    )
