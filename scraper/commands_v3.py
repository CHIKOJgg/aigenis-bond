"""Команды V3: ml-train, ml-predict, recs, rebalance-now (async)."""

from __future__ import annotations

import json

from sqlalchemy import select

from ml.engine import (
    ARTIFACTS_DIR,
    latest_artifact,
    train_buy_classifier,
    train_ytm_regressor,
)
from ml.features import build_dataset, build_training_samples
from ml.repository import (
    insert_training_run,
    latest_model_version,
    upsert_model_version,
    upsert_predictions,
)
from portfolio.positions_repository import list_positions, total_value
from portfolio.rebalance import build_plan
from recommendations.engine import recommend_bonds
from scoring.models import UserPreferences
from scraper import repositories
from scraper.db import session_scope
from scraper.orm import BondHistoryORM, BondORM


async def _fetch_bonds_dicts() -> tuple[list[dict], dict[str, list[dict]]]:
    async with session_scope() as session:
        bonds_q = await session.execute(select(BondORM))
        bonds = list(bonds_q.scalars().all())
        history_q = await session.execute(select(BondHistoryORM))
        history = list(history_q.scalars().all())

        history_by_bond: dict[str, list[dict]] = {}
        for h in history:
            history_by_bond.setdefault(h.internal_id, []).append(
                {"date": h.date, "price": h.price, "yield": h.yield_, "coupon": h.coupon}
            )

        return [
            {
                "internal_id": b.internal_id,
                "name": b.name,
                "currency": b.currency,
                "yield_to_maturity": b.yield_to_maturity,
                "coupon_rate": b.coupon_rate,
                "maturity_date": b.maturity_date,
                "price": b.price,
                "status": b.status,
                "issuer": b.issuer,
            }
            for b in bonds
        ], history_by_bond


async def cmd_ml_train() -> int:
    bond_dicts, history = await _fetch_bonds_dicts()

    # Leakage-free supervised samples: features observed in the past paired with
    # the YTM realized a horizon later (see ml.features.build_training_samples).
    samples = build_training_samples(bond_dicts, history)
    if len(samples) < 30:
        print(
            f"Недостаточно исторических данных для честного обучения: {len(samples)} примеров. "
            "Нужна история котировок за несколько месяцев по достаточному числу облигаций."
        )
        return 1

    mv_reg, tr_reg = train_ytm_regressor(samples)
    try:
        mv_clf, tr_clf = train_buy_classifier(samples)
    except ValueError as exc:
        # Not enough class diversity yet — train the regressor only.
        print(f"Классификатор пропущен: {exc}")
        mv_clf = tr_clf = None

    async with session_scope() as session:
        await upsert_model_version(session, mv_reg)
        await insert_training_run(session, tr_reg)
        if mv_clf is not None:
            await upsert_model_version(session, mv_clf)
            await insert_training_run(session, tr_clf)

    print(
        json.dumps(
            {
                "samples": len(samples),
                "ytm_regression": {
                    "version": mv_reg.version,
                    "metrics": mv_reg.metrics,
                    "artifact": mv_reg.artifact_path,
                },
                "buy_classifier": (
                    {
                        "version": mv_clf.version,
                        "metrics": mv_clf.metrics,
                        "artifact": mv_clf.artifact_path,
                    }
                    if mv_clf is not None
                    else None
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


async def cmd_ml_predict() -> int:
    bond_dicts, history = await _fetch_bonds_dicts()
    features = build_dataset(bond_dicts, history)
    if not features:
        print("Нет данных для прогноза")
        return 1
    reg_path = latest_artifact("ytm_regression")
    clf_path = latest_artifact("buy_classifier")
    if not reg_path and not clf_path:
        print("Нет обученных моделей. Запустите `python -m scraper ml-train`")
        return 1
    from ml.engine import predict_batch

    preds = predict_batch(features, regressor_path=reg_path, classifier_path=clf_path)

    async with session_scope() as session:
        await upsert_predictions(session, preds)
    print(f"Predicted for {len(preds)} bonds; saved to DB")
    return 0


async def cmd_recs() -> int:
    bond_dicts, history = await _fetch_bonds_dicts()
    prefs = UserPreferences(user_id=0)
    recs = recommend_bonds(bond_dicts, prefs, history_by_bond=history, top_k=10)
    for r in recs:
        print(
            f"#{r.rank} {r.internal_id} {r.name}: {r.decision.upper()} "
            f"(score={r.score:.0f}, conf={r.confidence:.2f})"
        )
    return 0


async def cmd_rebalance_now() -> int:
    user_id = 0

    async with session_scope() as session:
        prefs = await get_preferences_for_user(session, user_id)
        positions = await list_positions(session, user_id)
        bonds_q = await repositories.bonds.get_all_internal_ids(session)
        bonds_orm = (
            (await session.execute(select(BondORM).where(BondORM.internal_id.in_(list(bonds_q)))))
            .scalars()
            .all()
        )
        from scraper.models import Bond as BondModel

        bonds = [
            BondModel(
                internal_id=b.internal_id,
                name=b.name,
                currency=b.currency,
                yield_to_maturity=b.yield_to_maturity,
                maturity_date=b.maturity_date,
                status=b.status,
                issuer=b.issuer,
                price=b.price,
                fetched_at=b.fetched_at,
            )
            for b in bonds_orm
        ]
        total = total_value(positions) or prefs.initial_capital
        return _print_plan(
            build_plan(
                bonds=bonds,
                prefs=prefs,
                current_positions=positions,
                current_total=total,
            )
        )


def _print_plan(plan) -> int:
    if plan is None:
        print("Drift ниже порога — ребалансировка не требуется")
        return 0
    print(f"План ребалансировки ({plan.strategy}):")
    for a in plan.actions:
        print(
            f"  {a.side.upper()} {a.internal_id}: {a.amount} "
            f"({a.weight_before:.2%} → {a.weight_after:.2%})"
        )
    return 0


async def get_preferences_for_user(session, user_id: int) -> UserPreferences:
    """Получить prefs из БД или дефолтные (для scheduler)."""
    from telegram_bot.preferences_repository import get_preferences

    return await get_preferences(session, user_id)


async def cmd_ml_status() -> int:
    async with session_scope() as session:
        mv_reg = await latest_model_version(session, "ytm_regression")
        mv_clf = await latest_model_version(session, "buy_classifier")
    out = {
        "ytm_regression": (
            {
                "version": mv_reg.version,
                "trained_at": mv_reg.trained_at.isoformat(),
                "metrics": mv_reg.metrics,
                "artifact_path": mv_reg.artifact_path,
            }
            if mv_reg
            else None
        ),
        "buy_classifier": (
            {
                "version": mv_clf.version,
                "trained_at": mv_clf.trained_at.isoformat(),
                "metrics": mv_clf.metrics,
                "artifact_path": mv_clf.artifact_path,
            }
            if mv_clf
            else None
        ),
        "artifacts_dir": str(ARTIFACTS_DIR),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0
