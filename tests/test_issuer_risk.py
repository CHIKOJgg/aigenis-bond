"""Tests for per-issuer credit profiles (scoring/issuer_risk.py)."""

from api.demo import _issuer_risk_payload
from scoring.engine import _credit_risk_component
from scoring.issuer_risk import lookup_issuer_profile, profile_risk_ladder


def test_lookup_full_bcse_names():
    cases = {
        "Национальный банк Республики Беларусь": "nbrb",
        "Министерство финансов Республики Беларусь": "finance-ministry-by",
        "Могилевский областной исполнительный комитет": "executive-committee",
        "Гомельский районный исполнительный комитет": "executive-committee",
        "Сбер Банк ОАО": "sber-bank-by",
        "ЗАО «Альфа-Банк»": "alfa-bank-by",
        "ЗАО «Банк «Решение»»": "reshenie-bank",
        "МТбанк ЗАО": "mtbank",
        "ЕВРОТОРГ Общество с ограниченной ответственностью": "evrotorg",
        "Дженерал лизинг Общество с ограниченной ответственностью": "general-leasing",
        "Айгенис Закрытое акционерное общество": "aigenis",
        "Гурмина-ПРО Общество с ограниченной ответственностью": "gurmina-pro",
        "Активлизинг Общество с ограниченной ответственностью": "aktivlizing",
        "АВАНГАРД ЛИЗИНГ Закрытое акционерное общество": "avangard-lizing",
        "Чистый берег Закрытое акционерное общество": "chistyy-bereg",
        "ОЛИВЕР Общество с ограниченной ответственностью": "oliver",
        "МОСТРА-ГРУПП Общество с дополнительной ответственностью": "mostra-grupp",
        "Внешнеэкономическая Лизинговая Компания": "vlk",
        "Хольцгрупп Общество с ограниченной ответственностью": "holzgrupp",
        "Бутик-Инвест Общество с ограниченной ответственностью": "butik-invest",
        "НП-СЕРВИС Общество с дополнительной ответственностью": "np-service",
    }
    for name, key in cases.items():
        assert lookup_issuer_profile(name) is not None, name
        assert lookup_issuer_profile(name).key == key, name


def test_lookup_unknown_and_none():
    assert lookup_issuer_profile(None) is None
    assert lookup_issuer_profile("") is None
    assert lookup_issuer_profile("ООО Рога и Копыта") is None
    assert lookup_issuer_profile("Газпром") is None
    assert lookup_issuer_profile("Банк Дабрабыт") is None
    assert lookup_issuer_profile("МТБанк") is not None  # кириллическая «МТбанк»


def test_profile_risk_ladder_buckets():
    assert profile_risk_ladder(12.0) == (90.0, "Очень низкий")
    assert profile_risk_ladder(8.0) == (82.0, "Очень низкий")
    assert profile_risk_ladder(6.0) == (75.0, "Низкий")
    assert profile_risk_ladder(4.0) == (68.0, "Умеренно низкий")
    assert profile_risk_ladder(2.0) == (62.0, "Умеренно низкий")
    assert profile_risk_ladder(1.0) == (58.0, "Умеренный")
    assert profile_risk_ladder(0.0) == (56.0, "Умеренный")
    assert profile_risk_ladder(-1.0) == (50.0, "Повышенный")
    assert profile_risk_ladder(-3.0) == (44.0, "Повышенный")
    assert profile_risk_ladder(-6.0) == (36.0, "Высокий")


def test_credit_component_uses_profiles():
    assert _credit_risk_component("Национальный банк Республики Беларусь", "active") == 10.0
    assert _credit_risk_component("Министерство финансов Республики Беларусь", "active") == 12.0
    assert _credit_risk_component("Сбер Банк ОАО", "active") == 4.0
    assert _credit_risk_component("ЗАО «Альфа-Банк»", "active") == 3.0
    assert _credit_risk_component("МТбанк ЗАО", "active") == 2.0
    assert _credit_risk_component("ЕВРОТОРГ ООО", "active") == 3.0
    assert _credit_risk_component("Айгенис ЗАО", "active") == 1.0
    assert _credit_risk_component("НП-СЕРВИС ОДО", "active") == -5.0
    assert _credit_risk_component("Бутик-Инвест ООО", "active") == -2.0
    # статусные штрафы по-прежнему перекрывают профиль
    assert _credit_risk_component("НП-СЕРВИС ОДО", "defaulted") == -35.0
    assert _credit_risk_component("ЕВРОТОРГ ООО", "delisted") == -28.0
    # эмитенты без профиля — типовой классификацией
    assert _credit_risk_component("Газпром", "active") == 6.0
    assert _credit_risk_component("ООО Рога", "active") == -3.0


def test_demo_issuer_risk_profiles():
    ev = _issuer_risk_payload(
        "ЕВРОТОРГ ООО", is_government=False, credit_component=3.0, status="active"
    )
    assert ev["score"] == 62.0
    assert ev["level"] == "Умеренно низкий"
    assert "Евроопт" in ev["basis"]
    assert ev["issuer_profile"] == "evrotorg"
    assert ev["sources"]

    np = _issuer_risk_payload(
        "НП-СЕРВИС ОДО", is_government=False, credit_component=-5.0, status="active"
    )
    assert np["score"] == 36.0
    assert np["level"] == "Высокий"
    assert "дефолт" in np["basis"].lower()

    av = _issuer_risk_payload(
        "АВАНГАРД ЛИЗИНГ ЗАО", is_government=False, credit_component=-0.5, status="active"
    )
    assert av["score"] == 50.0
    assert av["level"] == "Повышенный"

    minfin = _issuer_risk_payload(
        "Министерство финансов Республики Беларусь",
        is_government=True,
        credit_component=12.0,
        status="active",
    )
    assert minfin["score"] == 90.0
    assert minfin["level"] == "Очень низкий"
    assert minfin["issuer_profile"] == "finance-ministry-by"

    # статус дефолта перекрывает профиль даже для известного эмитента
    dflt = _issuer_risk_payload(
        "ЕВРОТОРГ ООО", is_government=False, credit_component=3.0, status="defaulted"
    )
    assert dflt["score"] == 15.0
    assert dflt["level"] == "Критический"