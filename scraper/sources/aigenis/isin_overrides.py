"""Корректировка ISIN для белорусских облигаций.

Фид aigenis.by отдаёт для многих BCSE-выпусков «Код выпуска» (BY12)
или 6-значный код РЦБ вместо настоящего ISIN. Настоящие ISIN (BYE/BYM/BYD)
взяты с bcse.by (каталог GetSCatalog + страницы /stock/securitydirectory/).
Маппинг применяется на этапе парсинга, поэтому переживает любой рескрейп.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_OVERRIDES_PATH = Path(__file__).with_name("isin_overrides.json")


@lru_cache(maxsize=1)
def _overrides() -> dict[str, str]:
    try:
        data: Any = json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).strip(): str(v).strip() for k, v in data.items() if isinstance(v, str)}


def override_isin(internal_id: str | None, isin: str | None) -> str | None:
    """Возвращает известный настоящий ISIN для внутреннего id, иначе исходный."""
    if internal_id:
        known = _overrides().get(str(internal_id).strip())
        if known:
            return known
    return isin