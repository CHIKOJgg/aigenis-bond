"""Scheduler job run history (plan 11.3).

One row per scheduled pipeline invocation. Status is one of
``running`` / ``ok`` / ``skipped`` / ``failed`` / ``timeout``.
``error`` carries a short, single-line summary of the failure so the
history table stays greppable and chart-friendly; full tracebacks continue
to live in structured logs.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from scraper.orm._base import Base


class JobRunORM(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_job_runs_name_started", "job_name", "started_at"),
        Index("ix_job_runs_status", "status"),
    )
