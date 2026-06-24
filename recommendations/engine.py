"""Рекомендации по покупке: объединяем Score, ML и пользовательские предпочтения."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from ml.engine import latest_artifact, predict_batch
from ml.features import build_features
from ml.models import Decision, Recommendation
from ml.repository import upsert_predictions
from scoring.engine import score_bond
from scoring.models import UserPreferences
from scraper.db import session_scope

_DECISION_RANK: dict[Decision, int] = {"buy": 4, "hold": 3, "wait": 2, "avoid": 1}


def _confidence_rank(decision: Decision, ml_confidence: float, score: float) -> float:
    base = ml_confidence if ml_confidence > 0 else score / 100
    decision_bonus = (_DECISION_RANK[decision] - 1) / 3
    return round(min(base * 0.7 + decision_bonus * 0.3, 1.0), 3)


def recommend_bonds(
    bonds: list[dict],
    prefs: UserPreferences,
    *,
    asof: date | None = None,
    top_k: int = 10,
    history_by_bond: dict[str, list[dict]] | None = None,
) -> list[Recommendation]:
    """Сформировать список рекомендаций с объяснениями."""
    asof = asof or date.today()
    history_by_bond = history_by_bond or {}

    features = [
        build_features(
            bond_dict=b,
            history=history_by_bond.get(b["internal_id"], []),
            asof=asof,
        )
        for b in bonds
    ]

    reg_path = latest_artifact("ytm_regression")
    clf_path = latest_artifact("buy_classifier")
    predictions = predict_batch(
        features,
        regressor_path=reg_path,
        classifier_path=clf_path,
    )

    out: list[Recommendation] = []
    for bond, feature, pred in zip(bonds, features, predictions, strict=True):
        score = score_bond(
            internal_id=bond["internal_id"],
            yield_to_maturity=bond.get("yield_to_maturity"),
            currency=str(bond.get("currency", "USD")),
            maturity_date=bond.get("maturity_date"),
            status=str(bond.get("status", "unknown")),
            issuer=bond.get("issuer"),
            price=bond.get("price"),
        )

        if prefs.watchlist and bond["internal_id"] not in prefs.watchlist and pred.decision != "buy":
            continue

        currency = str(bond.get("currency", "USD")).upper()
        if currency == "USD" and prefs.share_usd <= 0:
            continue
        if currency == "BYN" and prefs.share_byn <= 0:
            continue
        if currency in {"XAU", "XAG", "XPT"} and prefs.share_metals <= 0:
            continue

        risks: list[str] = []
        if pred.predicted_return_pct is not None and pred.predicted_return_pct < 0:
            risks.append(f"прогноз снижения доходности: {pred.predicted_return_pct:.2f}%")
        if feature.score_duration_component < 0:
            risks.append("длительная дюрация — процентный риск")
        if not feature.is_gov_issuer and not feature.is_active:
            risks.append("не государственный эмитент / не активна")

        out.append(
            Recommendation(
                internal_id=bond["internal_id"],
                name=str(bond.get("name") or bond["internal_id"]),
                decision=pred.decision,
                confidence=_confidence_rank(pred.decision, pred.confidence, score.score),
                score=score.score,
                predicted_return_pct=pred.predicted_return_pct,
                reasons=pred.explanation,
                risks=risks,
                rank=0,
            )
        )

    out.sort(
        key=lambda r: (_DECISION_RANK[r.decision], r.confidence, r.score),
        reverse=True,
    )
    for i, r in enumerate(out[:top_k], 1):
        r.rank = i
    return out[:top_k]


async def save_predictions_to_db(predictions: Iterable) -> int:
    """Сохранить прогнозы в БД для аудита."""
    async with session_scope() as session:
        return await upsert_predictions(session, list(predictions))
