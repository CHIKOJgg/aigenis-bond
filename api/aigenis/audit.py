"""
Structured audit logging для Aigenis Analytics Integration.

Формат логов:
- JSON (structured)
- Обязательные поля: timestamp, event, correlation_id, user_id (pseudonymized)
- Запрещено: PII, bearer token, portfolio structure, email, phone
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger("aigenis.audit")


def _clean_pii(data: dict[str, Any]) -> dict[str, Any]:
    """Удалить PII из логов."""
    forbidden_keys = {
        "email",
        "phone",
        "password",
        "token",
        "bearer",
        "access_token",
        "refresh_token",
        "portfolio",
        "positions",
    }
    return {k: v for k, v in data.items() if k not in forbidden_keys}


def audit_event(
    event: str,
    user_id: str | None = None,
    correlation_id: str | None = None,
    instrument_id: str | None = None,
    market: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Записать аудит-событие.

    Поля:
    - event: имя события (analytics_opened, bond_detail_opened, etc.)
    - user_id: псевдонимный идентификатор пользователя
    - correlation_id: сквозной идентификатор запроса
    - instrument_id: идентификатор инструмента (если применимо)
    - market: рынок (BCSE/MOEX)
    - extra: дополнительные данные (без PII)
    """
    if extra:
        extra = _clean_pii(extra)

    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        "user_id": user_id,
        "correlation_id": correlation_id or str(uuid4()),
        "instrument_id": instrument_id,
        "market": market,
        "environment": os.getenv("AIGENIS_ENVIRONMENT", "unknown"),
        "extra": extra or {},
    }

    logger.info(json.dumps(record, ensure_ascii=False))


# ──────────────────────────────────────────────
# Product event names (per Finalplan §17.2)
# ──────────────────────────────────────────────

EVENT_ANALYTICS_OPENED = "analytics_opened"
EVENT_FILTER_APPLIED = "analytics_filter_applied"
EVENT_SORT_CHANGED = "analytics_sort_changed"
EVENT_BOND_DETAIL_OPENED = "bond_detail_opened"
EVENT_SCORE_EXPLANATION_OPENED = "score_explanation_opened"
EVENT_PORTFOLIO_IMPACT_OPENED = "portfolio_impact_opened"
EVENT_ALERT_CREATED = "alert_created"
EVENT_ORDER_FLOW_STARTED = "order_flow_started_from_analytics"
