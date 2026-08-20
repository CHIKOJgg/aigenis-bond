"""Data-driven issuer credit signal from real public financial reports.

Given free text of a public financial report (year/quarter, amounts, units), this
module extracts a structured ``IssuerFinancials`` snapshot and derives a credit
adjustment. It is deliberately rule-based (regex over Cyrillic/Latin with
number/unit heuristics) so it runs offline and is testable; an optional LLM pass
via ``api.document_analysis`` can be layered on top for messy filings.

The result is combined with the static expert profiles in
``scoring/issuer_risk.py`` by ``credit_for_issuer``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_UNITS = {
    "млрд": 1e9, "млрд.": 1e9, "млrd": 1e9, "bn": 1e9, "b": 1e9,
    "млн": 1e6, "млн.": 1e6, "mn": 1e6, "m": 1e6,
    "тыс": 1e3, "тыс.": 1e3, "th": 1e3, "k": 1e3,
}

_NUMBER_TOKEN = re.compile(r"[-+]?\d[\d\s]*[.,]\d+|\d[\d\s]*")

_CURRENCY_RE = re.compile(r"\b(BYN|USD|EUR|RUB|CNY|бел\. ?руб|белорусских руб)\b", re.IGNORECASE)
_PERIOD_RE = re.compile(r"(20\d{2})(?:[.\-/](?:9|I?I?I?V?X?)?)?|(\d\s?м\s?(?:20\d{2})?)|(?:за\s+)?(9\s?мес\.)", re.IGNORECASE)


@dataclass
class IssuerFinancials:
    revenue: float | None = None
    net_income: float | None = None
    ebitda: float | None = None
    assets: float | None = None
    equity: float | None = None
    liabilities: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    debt: float | None = None
    currency: str | None = None
    period: str | None = None
    raw: str = ""


def _to_float(token: str) -> float | None:
    token = token.replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(token)
    except ValueError:
        return None


def _find_value_on_line(line: str) -> float | None:
    m = _NUMBER_TOKEN.search(line)
    if not m:
        return None
    val = _to_float(m.group(0))
    if val is None:
        return None
    after = line[m.end(): m.end() + 14].lower()
    for unit, mult in _UNITS.items():
        if after.strip().startswith(unit):
            val *= mult
            break
    if re.search(r"убыток|отрицат", line.lower()):
        val = -abs(val)
    return val


def _find_value(text: str, *keywords: str) -> float | None:
    lowered = text.lower()
    for kw in keywords:
        for m in re.finditer(re.escape(kw.lower()), lowered):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end == -1:
                line_end = len(text)
            line = text[line_start:line_end]
            val = _find_value_on_line(line)
            if val is not None:
                return val
    return None


def parse_financial_report(text: str) -> IssuerFinancials:
    """Extract key figures from a free-text financial report."""
    fin = IssuerFinancials(raw=text)

    fin.revenue = _find_value(
        text, "выручка", "доход от реализации", "совокупный доход", "доходы"
    )
    fin.net_income = _find_value(
        text, "чистая прибыль", "чистый убыток", "прибыль", "финансовый результат"
    )
    fin.ebitda = _find_value(text, "ebitda", "ebitda")
    fin.assets = _find_value(
        text, "активы", "валюта баланса", "общая сумма активов"
    )
    fin.equity = _find_value(
        text, "собственный капитал", "капитал и резервы", "капитал"
    )
    fin.liabilities = _find_value(
        text, "обязательства", "кредиторская задолженность"
    )
    fin.current_assets = _find_value(text, "оборотные активы")
    fin.current_liabilities = _find_value(
        text, "краткосрочные обязательства", "краткосрочная кредиторская"
    )
    fin.debt = _find_value(
        text, "заемные средства", "финансовые обязательства", "долг", "кредитный портфель"
    )

    cm = _CURRENCY_RE.search(text)
    if cm:
        token = cm.group(1).upper().replace("БЕЛ. РУБ", "BYN").replace(
            "БЕЛОРУССКИХ РУБ", "BYN"
        )
        fin.currency = token

    pm = _PERIOD_RE.search(text)
    if pm:
        fin.period = (pm.group(1) or pm.group(3) or pm.group(2) or "").strip()

    return fin


def score_from_financials(fin: IssuerFinancials) -> tuple[float, str]:
    """Return (credit_adjustment, basis) in roughly [-4, +4] from the figures."""
    reasons: list[str] = []
    score = 0.0

    if fin.debt is not None and fin.assets:
        lev = fin.debt / fin.assets
        if lev < 0.2:
            score += 2.0
            reasons.append(f"низкий долг/активы {lev:.2f}")
        elif lev < 0.5:
            score += 0.5
        elif lev > 0.8:
            score -= 2.0
            reasons.append(f"высокий долг/активы {lev:.2f}")
        else:
            score -= 0.5

    if fin.equity is not None and fin.assets:
        er = fin.equity / fin.assets
        if er > 0.5:
            score += 1.0
            reasons.append(f"доля капитала {er:.2f}")
        elif er < 0.2:
            score -= 1.5
            reasons.append(f"низкая доля капитала {er:.2f}")

    if fin.current_assets and fin.current_liabilities:
        lr = fin.current_assets / fin.current_liabilities
        if lr < 1.0:
            score -= 1.5
            reasons.append(f"текущая ликвидность {lr:.2f}<1")
        elif lr > 1.5:
            score += 1.0

    if fin.net_income is not None and fin.revenue:
        pm_ = fin.net_income / fin.revenue
        if fin.net_income < 0:
            score -= 1.5
            reasons.append("чистый убыток")
        elif pm_ > 0.1:
            score += 1.5
            reasons.append(f"маржа {pm_:.1%}")
        elif pm_ > 0.03:
            score += 0.5

    score = max(-4.0, min(4.0, score))
    basis = (
        "Финансовые показатели (" + (fin.currency or "ед.") + ", "
        + (fin.period or "период?") + "): " + "; ".join(reasons)
        if reasons else "Недостаточно данных отчётности для вывода."
    )
    return score, basis
