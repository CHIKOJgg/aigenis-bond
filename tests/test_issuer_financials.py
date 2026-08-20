"""Tests for the data-driven issuer financials parser and scoring."""

from __future__ import annotations

from scoring.financials import parse_financial_report, score_from_financials
from scoring.issuer_risk import credit_for_issuer
from scoring.financials import IssuerFinancials


SAMPLE_REPORT = """
Отчёт эмитента за 2025 год (BYN):

Выручка: 9 223 млн
Чистая прибыль: 427,228 тыс
Активы: 2 500 млн
Собственный капитал: 1 400 млн
Обязательства: 1 100 млн
Оборотные активы: 900 млн
Краткосрочные обязательства: 700 млн
Заемные средства: 800 млн
"""


def test_parse_extracts_scaled_figures():
    fin = parse_financial_report(SAMPLE_REPORT)
    assert fin.revenue == 9_223_000_000
    assert fin.net_income == 427_228.0
    assert fin.assets == 2_500_000_000
    assert fin.equity == 1_400_000_000
    assert fin.liabilities == 1_100_000_000
    assert fin.current_assets == 900_000_000
    assert fin.current_liabilities == 700_000_000
    assert fin.debt == 800_000_000
    assert fin.currency == "BYN"
    assert fin.period == "2025"


def test_score_rewards_low_leverage_and_equity():
    fin = parse_financial_report(SAMPLE_REPORT)
    score, basis = score_from_financials(fin)
    assert score > 0
    assert "долг/активы" in basis or "доля капитала" in basis


def test_loss_turns_score_negative():
    loss_text = (
        "Отчёт за 2025 год (BYN)\n"
        "Выручка: 100 млн\n"
        "Чистый убыток: 20 млн\n"
        "Активы: 200 млн\n"
        "Собственный капитал: 30 млн\n"
        "Краткосрочные обязательства: 180 млн\n"
        "Оборотные активы: 50 млн\n"
    )
    fin = parse_financial_report(loss_text)
    score, _ = score_from_financials(fin)
    assert score < 0


def test_credit_for_issuer_blends_financials():
    fin = parse_financial_report(SAMPLE_REPORT)
    credit, basis = credit_for_issuer("Евроторг", financials=fin)
    assert -6.0 <= credit <= 12.0
    assert "Данные отчётности" in basis


def test_credit_for_issuer_fallback():
    credit, _ = credit_for_issuer("Евроторг")
    assert credit == 3.0
