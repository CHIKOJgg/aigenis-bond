"""Central legal disclaimer for all analytics that could be read as advice.

Every verdict, score explanation, ML forecast and recommendation surface must
carry this text. Fixed-income analytics on this platform are informational only
and are NOT individual investment advice. Keeping a single constant avoids drift
between the bot, the API and the website.
"""
from __future__ import annotations

# Short one-liner for compact UIs (bond cards, inline messages).
DISCLAIMER_SHORT = (
    "⚠️ Не является индивидуальной инвестиционной рекомендацией. "
    "Решения принимайте самостоятельно."
)

# Full text for detailed screens / API payloads.
DISCLAIMER_FULL = (
    "Данная информация носит справочно-аналитический характер, формируется "
    "автоматически на основе открытых данных и НЕ является индивидуальной "
    "инвестиционной рекомендацией в значении законодательства. Оценки, прогнозы "
    "и вердикты не гарантируют доходности; стоимость облигаций и доход по ним "
    "могут меняться. Прежде чем принимать инвестиционные решения, оцените риски "
    "самостоятельно или обратитесь к лицензированному консультанту."
)

# English variant for the i18n website.
DISCLAIMER_FULL_EN = (
    "This information is for reference and analytical purposes only, is generated "
    "automatically from public data and is NOT individual investment advice. "
    "Scores, forecasts and verdicts do not guarantee returns; bond prices and "
    "income may change. Assess the risks yourself or consult a licensed advisor "
    "before making investment decisions."
)

__all__ = ["DISCLAIMER_FULL", "DISCLAIMER_FULL_EN", "DISCLAIMER_SHORT"]
