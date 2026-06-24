"""Репозиторий для ML: model_versions, training_runs, predictions."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ml.models import ModelVersion, Prediction, TrainingRun
from scraper.orm import ModelVersionORM, PredictionORM, TrainingRunORM


def _to_mv(mv: ModelVersion) -> dict:
    return {
        "version": mv.version,
        "kind": mv.kind,
        "metrics": mv.metrics,
        "trained_at": mv.trained_at,
        "train_rows": mv.train_rows,
        "artifact_path": mv.artifact_path,
        "notes": mv.notes or None,
    }


def _to_tr(tr: TrainingRun) -> dict:
    return {
        "version": tr.version,
        "kind": tr.kind,
        "started_at": tr.started_at,
        "finished_at": tr.finished_at,
        "metrics": tr.metrics,
        "status": tr.status,
        "notes": tr.notes or None,
    }


def _to_pred(p: Prediction) -> dict:
    return {
        "internal_id": p.internal_id,
        "model_version": p.model_version,
        "kind": p.model_kind,
        "asof_date": p.asof_date,
        "predicted_ytm": Decimal(str(p.predicted_ytm)) if p.predicted_ytm is not None else None,
        "predicted_return_pct": (
            Decimal(str(p.predicted_return_pct)) if p.predicted_return_pct is not None else None
        ),
        "predicted_volatility": (
            Decimal(str(p.predicted_volatility)) if p.predicted_volatility is not None else None
        ),
        "decision": p.decision,
        "confidence": Decimal(str(p.confidence)),
        "feature_importance": p.feature_importance,
        "explanation": p.explanation,
        "created_at": p.created_at,
    }


async def upsert_model_version(session: AsyncSession, mv: ModelVersion) -> None:
    stmt = pg_insert(ModelVersionORM).values(**_to_mv(mv))
    update_cols = {c: stmt.excluded[c] for c in _to_mv(mv) if c != "version"}
    stmt = stmt.on_conflict_do_update(
        index_elements=[ModelVersionORM.version], set_=update_cols
    )
    await session.execute(stmt)


async def latest_model_version(session: AsyncSession, kind: str) -> ModelVersionORM | None:
    result = await session.execute(
        select(ModelVersionORM)
        .where(ModelVersionORM.kind == kind)
        .order_by(ModelVersionORM.trained_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def insert_training_run(session: AsyncSession, run: TrainingRun) -> None:
    stmt = pg_insert(TrainingRunORM).values(**_to_tr(run))
    await session.execute(stmt)


async def upsert_predictions(session: AsyncSession, preds: Iterable[Prediction]) -> int:
    rows = [_to_pred(p) for p in preds]
    if not rows:
        return 0
    stmt = pg_insert(PredictionORM).values(rows)
    update_cols = {
        c: stmt.excluded[c]
        for c in rows[0]
        if c not in {"internal_id", "asof_date", "model_version", "kind"}
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            PredictionORM.internal_id,
            PredictionORM.asof_date,
            PredictionORM.model_version,
            PredictionORM.kind,
        ],
        set_=update_cols,
    )
    await session.execute(stmt)
    return len(rows)


async def latest_predictions(
    session: AsyncSession, limit: int = 50, decision: str | None = None
) -> list[PredictionORM]:
    stmt = select(PredictionORM).order_by(PredictionORM.created_at.desc()).limit(limit)
    if decision:
        stmt = stmt.where(PredictionORM.decision == decision)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def predictions_for_bond(
    session: AsyncSession, internal_id: str, limit: int = 20
) -> list[PredictionORM]:
    result = await session.execute(
        select(PredictionORM)
        .where(PredictionORM.internal_id == internal_id)
        .order_by(PredictionORM.asof_date.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
