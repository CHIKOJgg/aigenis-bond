"""Auto-rebalance: детект drift, формирование плана, применение."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from ml.models import RebalanceAction, RebalancePlan
from portfolio.optimizer import allocate
from portfolio.positions_repository import (
    list_positions,
    mark_rebalance_applied,
    save_rebalance_plan,
    total_value,
    upsert_position,
)
from scoring.models import UserPreferences
from scraper.db import session_scope
from scraper.models import Bond

DEFAULT_DRIFT_THRESHOLD = 0.05
MIN_TRADE_AMOUNT = Decimal("50")


def _compute_weights(
    positions: Iterable,
    target_alloc: dict[str, Decimal],
    total: Decimal,
) -> dict[str, tuple[Decimal, float, float]]:
    current = {p.internal_id: p.amount for p in positions}
    result: dict[str, tuple[Decimal, float, float]] = {}
    all_ids = set(current) | set(target_alloc)
    for iid in all_ids:
        cur_amount = current.get(iid, Decimal("0"))
        tgt_amount = target_alloc.get(iid, Decimal("0"))
        weight_before = float(cur_amount / total) if total > 0 else 0.0
        weight_after = float(tgt_amount / total) if total > 0 else 0.0
        result[iid] = (tgt_amount - cur_amount, weight_before, weight_after)
    return result


def _drift(deltas: dict[str, tuple[Decimal, float, float]]) -> float:
    return max((abs(w_after - w_before) for _, w_before, w_after in deltas.values()), default=0.0)


def build_plan(
    *,
    bonds: list[Bond],
    prefs: UserPreferences,
    current_positions: list,
    current_total: Decimal,
    drift_threshold: float = DEFAULT_DRIFT_THRESHOLD,
    top_n: int = 10,
) -> RebalancePlan | None:
    """Сформировать план ребалансировки, если drift > threshold."""
    target_alloc = allocate(bonds, prefs, top_n=top_n)
    target_items = target_alloc.items
    deltas = _compute_weights(current_positions, target_items, current_total)
    drift = _drift(deltas)

    if drift < drift_threshold:
        return None

    actions: list[RebalanceAction] = []
    for iid, (delta, w_before, w_after) in deltas.items():
        if abs(delta) < MIN_TRADE_AMOUNT:
            continue
        if delta > 0:
            actions.append(
                RebalanceAction(
                    internal_id=iid,
                    side="buy",
                    amount=delta,
                    weight_before=round(w_before, 4),
                    weight_after=round(w_after, 4),
                    reason=f"довести долю до {w_after:.2%}",
                )
            )
        elif delta < 0:
            actions.append(
                RebalanceAction(
                    internal_id=iid,
                    side="sell",
                    amount=-delta,
                    weight_before=round(w_before, 4),
                    weight_after=round(w_after, 4),
                    reason=f"снизить долю до {w_after:.2%}",
                )
            )
        else:
            actions.append(
                RebalanceAction(
                    internal_id=iid,
                    side="hold",
                    amount=Decimal("0"),
                    weight_before=round(w_before, 4),
                    weight_after=round(w_after, 4),
                    reason="без изменений",
                )
            )

    return RebalancePlan(
        strategy=prefs.strategy,
        drift_threshold=drift_threshold,
        max_drift_observed=round(drift, 4),
        actions=actions,
        expected_return=target_alloc.expected_return,
        estimated_cost=sum(
            (abs(a.amount) for a in actions if a.side != "hold"), start=Decimal("0")
        ),
        created_at=datetime.now(UTC),
    )


async def maybe_auto_rebalance(
    *,
    user_id: int,
    prefs: UserPreferences,
    bonds: list[Bond],
    drift_threshold: float = DEFAULT_DRIFT_THRESHOLD,
) -> RebalancePlan | None:
    """Проверить drift и сохранить план, если требуется ребалансировка."""
    async with session_scope() as session:
        positions = await list_positions(session, user_id)
        total = total_value(positions) or prefs.initial_capital
        plan = build_plan(
            bonds=bonds,
            prefs=prefs,
            current_positions=positions,
            current_total=total,
            drift_threshold=drift_threshold,
        )
        if plan is None:
            return None
        plan_id = await save_rebalance_plan(session, user_id, plan)
        if plan_id:
            for a in plan.actions:
                if a.side == "buy":
                    await upsert_position(session, user_id, a.internal_id, a.amount)
                elif a.side == "sell":
                    pos = next(
                        (p for p in positions if p.internal_id == a.internal_id), None
                    )
                    if pos is not None:
                        new_amount = pos.amount - a.amount
                        if new_amount > 0:
                            await upsert_position(session, user_id, a.internal_id, new_amount)
            await mark_rebalance_applied(session, plan_id)
        return plan
