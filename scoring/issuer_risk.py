"""Per-issuer credit profiles for the Reward/Risk engine.

Для каждого эмитента из таблицы котировок БВФБ подобран профиль на основе
публичных данных (отчётность, рейтинги деловой репутации BIK Ratings, новости,
архив дефолтов). Профиль заменяет типовой кредитный компонент (см.
_CREDIT_TIERS в scoring/engine.py) на значение, обоснованное конкретным
эмитентом, и служит источником базиса и лестницы уровней в demo-UI
(api/demo.py::_issuer_risk_payload).

Значения credit — экспертные предположения по данным на 2026-08-20; для
эмитентов без свежей публичной отчётности применена консервативная оценка
(это отражено в basis). Статусные штрафы (defaulted/delisted/matured) в
engine.py применяются до профиля и не перекрываются им.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scoring.financials import IssuerFinancials, score_from_financials


@dataclass(frozen=True)
class IssuerProfile:
    key: str
    aliases: tuple[str, ...]
    kind: str
    credit: float
    basis: str
    sources: tuple[str, ...] = ()


_ORG_FORMS = (
    "общество с ограниченной ответственностью",
    "общество с дополнительной ответственностью",
    "закрытое акционерное общество",
    "открытое акционерное общество",
    "унитарное предприятие",
    "частное предприятие",
    "ооо",
    "одо",
    "зао",
    "оао",
)

_PUNCT_RE = re.compile(r"[«»\"'()\[\],.]+")


def _normalize(name: str) -> str:
    if not name:
        return ""
    s = name.lower().strip()
    for form in _ORG_FORMS:
        s = s.replace(form, " ")
    s = _PUNCT_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def profile_risk_ladder(credit: float) -> tuple[float, str]:
    """Лестница score/level для известных (профильных) эмитентов."""
    if credit >= 10.0:
        return 90.0, "Очень низкий"
    if credit >= 8.0:
        return 82.0, "Очень низкий"
    if credit >= 6.0:
        return 75.0, "Низкий"
    if credit >= 4.0:
        return 68.0, "Умеренно низкий"
    if credit >= 2.0:
        return 62.0, "Умеренно низкий"
    if credit >= 1.0:
        return 58.0, "Умеренный"
    if credit >= 0.0:
        return 56.0, "Умеренный"
    if credit > -2.0:
        return 50.0, "Повышенный"
    if credit > -5.0:
        return 44.0, "Повышенный"
    return 36.0, "Высокий"


PROFILES: tuple[IssuerProfile, ...] = (
    IssuerProfile(
        key="finance-ministry-by",
        aliases=("министерство финансов", "минфин"),
        kind="sovereign",
        credit=12.0,
        basis=(
            "Государственные облигации Республики Беларусь (ГДО/ВГДО): "
            "обязательства Минфина РБ, минимальный кредитный риск на внутреннем рынке."
        ),
        sources=("minfin.gov.by", "bcse.by"),
    ),
    IssuerProfile(
        key="executive-committee",
        aliases=("исполнительный комитет", "облисполком", "райисполком"),
        kind="sub_sovereign",
        credit=8.0,
        basis=(
            "Субсуверенный эмитент: облигации областных/районных исполнительных "
            "комитетов, обязательства обеспечены бюджетом соответствующего уровня."
        ),
        sources=("minfin.gov.by", "bcse.by"),
    ),
    IssuerProfile(
        key="nbrb",
        aliases=("национальный банк", "нбрб"),
        kind="sovereign",
        credit=10.0,
        basis=(
            "Центральный банк Республики Беларусь: облигации Национального банка — "
            "инструмент денежно-кредитной политики, эмитент без кредитного риска "
            "частного сектора."
        ),
        sources=("nbrb.by",),
    ),
    IssuerProfile(
        key="sber-bank-by",
        aliases=("сбер банк", "сбербанк", "бпс"),
        kind="bank_systemic",
        credit=4.0,
        basis=(
            "Один из крупнейших банков РБ: капитал 1,42 млрд BYN и чистая прибыль "
            "245 млн BYN по МСФО за 2025; публикует консолидированную отчётность, "
            "надзор НБРБ."
        ),
        sources=("sber-bank.by", "bikratings.by"),
    ),
    IssuerProfile(
        key="alfa-bank-by",
        aliases=("альфа-банк", "альфа банк", "альфабанк"),
        kind="bank",
        credit=3.0,
        basis=(
            "Крупный частный банк РБ: чистая прибыль по МСФО 2025 — 0,19 млрд BYN "
            "(2024: 0,34 млрд BYN, ROE 22,9%); публикует МСФО и НСФО, надзор НБРБ."
        ),
        sources=("alfa-bank.by", "cbonds.com"),
    ),
    IssuerProfile(
        key="reshenie-bank",
        aliases=("банк решение",),
        kind="bank",
        credit=2.5,
        basis=(
            "Коммерческий банк (с 1994) под надзором НБРБ, участник системы "
            "гарантирования вкладов; отчётность публикуется по требованиям НБРБ."
        ),
        sources=("nbrb.by", "bankreshenie.by"),
    ),
    IssuerProfile(
        key="mtbank",
        aliases=("мтбанк", "мт-банк", "мт банк"),
        kind="bank",
        credit=2.0,
        basis=(
            "Коммерческий банк под надзором НБРБ, участник системы гарантирования "
            "вкладов; публикует отчётность по требованиям НБРБ."
        ),
        sources=("nbrb.by", "mtbank.by"),
    ),
    IssuerProfile(
        key="evrotorg",
        aliases=("евроторг", "евроопт"),
        kind="retail",
        credit=3.0,
        basis=(
            "Крупнейший продуктовый ритейлер РБ (сети «Евроопт», ~19% рынка): выручка "
            "2025 — 9,2 млрд BYN, чистая прибыль 427 млн BYN (+21,8%), Долг/EBIT 1,8; "
            "имеет кредитные рейтинги Fitch/S&P/«Эксперт РА»."
        ),
        sources=("evrotorg.by", "cbonds.com", "expert-ra.ru"),
    ),
    IssuerProfile(
        key="general-leasing",
        aliases=("дженерал лизинг", "general leasing", "ringo"),
        kind="leasing",
        credit=1.5,
        basis=(
            "Лизинговый эмитент (Ringo): рейтинг деловой репутации BIK AAA "
            "(подтверждён 12/2025); активы 235 млн BYN, портфель 333 млн BYN, "
            "просрочка портфеля 0,75%, чистая прибыль 9 мес. 2025 — 7 млн BYN."
        ),
        sources=("bikratings.by", "ringo.by"),
    ),
    IssuerProfile(
        key="aigenis",
        aliases=("айгенис",),
        kind="broker",
        credit=1.0,
        basis=(
            "Инвестиционная компания (30+ лет), крупнейший эмитент корпоративных "
            "облигаций на БВФБ; металлические выпуски индексированы к учётным ценам "
            "НБРБ и захеджированы фьючерсами на 100% объёма; поддерживает "
            "двусторонние котировки (маркет-мейкер) по своим бумагам."
        ),
        sources=("aigenis.by", "bcse.by"),
    ),
    IssuerProfile(
        key="gurmina-pro",
        aliases=("гурмина",),
        kind="production",
        credit=0.0,
        basis=(
            "Производитель специй и приправ: рейтинг деловой репутации BIK A "
            "(03/2025); выручка 9 мес. 2025 — 20,8 млн BYN (+31,5%), чистая прибыль "
            "2 млн BYN; текущая ликвидность 2,8 (1 кв. 2026)."
        ),
        sources=("bikratings.by", "gurmina.by"),
    ),
    IssuerProfile(
        key="aktivlizing",
        aliases=("активлизинг",),
        kind="leasing",
        credit=-0.5,
        basis=(
            "Автолизинг для юрлиц (20 лет, ТОП-5 лизинговых компаний РБ): кредитный "
            "рейтинг BIK by.A+ (07/2026, прогноз неопределённый); 1 кв. 2025 — убыток "
            "из-за курсовых разниц; фондирование на ~50% облигациями."
        ),
        sources=("bikratings.by", "aktivlizing.by"),
    ),
    IssuerProfile(
        key="avangard-lizing",
        aliases=("авангард лизинг",),
        kind="leasing",
        credit=-1.5,
        basis=(
            "Одна из первых лизинговых компаний РБ на рынке облигаций (28 займов в "
            "обращении, двусторонние котировки). Ранее присваивался рейтинг деловой "
            "репутации BIK AA (03/2025), НО он ОТОЗВАН 20.03.2026 (bikratings.by / "
            "tokenbel.info) — текущая кредитная оценка опирается только на отчётность. "
            "Безубыточна с 2009, но прибыль низкая (9 тыс. BYN за 1 кв. 2025), "
            "долгосрочные обязательства ~71% баланса; оценка понижена до умеренно "
            "высокого риска за отсутствием действующего внешнего рейтинга."
        ),
        sources=("bikratings.by", "tokenbel.info", "minfin.by"),
    ),
    IssuerProfile(
        key="chistyy-bereg",
        aliases=("чистый берег",),
        kind="trade",
        credit=-1.0,
        basis=(
            "Крупнейший поставщик сантехники и инженерных систем РБ (активы ~69 млн "
            "BYN); рейтинг деловой репутации BIK AAA (04/2025), но финансовые "
            "результаты волатильны: убыток в 1 кв. 2024, ROE −21,2% на 1 пол. 2024."
        ),
        sources=("bikratings.by", "chistiy-bereg.by"),
    ),
    IssuerProfile(
        key="oliver",
        aliases=("оливер",),
        kind="production",
        credit=-1.0,
        basis=(
            "Крупнейший производитель сварочных материалов РБ (с 1993); выручка 9 мес. "
            "2022 — 112,8 млн BYN, чистая прибыль 11,7 млн BYN; актуальная отчётность "
            "(2024–2025) в открытых источниках не раскрыта."
        ),
        sources=("myfin.by", "oliwer.by"),
    ),
    IssuerProfile(
        key="mostra-grupp",
        aliases=("мостра",),
        kind="distribution",
        credit=-1.0,
        basis=(
            "Один из крупнейших дистрибуторов продуктов питания РБ (~20% рынка FMCG, "
            "2,5 тыс. сотрудников, RTL-Holding); свежая финансовая отчётность в "
            "открытых источниках не найдена, публичный долг ~2 млн USD."
        ),
        sources=("cbonds.com", "myfin.by"),
    ),
    IssuerProfile(
        key="vlk",
        aliases=("внешнеэкономическая лизинговая", "влк"),
        kind="leasing",
        credit=-1.5,
        basis=(
            "Лизинговая компания для юрлиц (с 2014): рейтинг деловой репутации BIK AA "
            "(08/2023); портфель 98 млн BYN (2023), но низкая текущая ликвидность "
            "(К1 1,06) и слабая финансовая устойчивость по оценкам 2024–2025."
        ),
        sources=("bikratings.by", "castle.by"),
    ),
    IssuerProfile(
        key="holzgrupp",
        aliases=("хольцгрупп", "хольц групп", "хольцгруп"),
        kind="trade",
        credit=-1.5,
        basis=(
            "Торговля плитными материалами и мебельное производство, официальный "
            "дилер EGGER/SWISS KRONO; финансовое положение устойчивое (1 пол. 2025), "
            "но масштаб небольшой (активы ~12 млн BYN) и ликвидность бумаг низкая "
            "(внесписочный сегмент, редкие сделки)."
        ),
        sources=("myfin.by", "bcse.by"),
    ),
    IssuerProfile(
        key="butik-invest",
        aliases=("бутик-инвест", "бутик инвест", "butikavto", "бутик"),
        kind="auto_retail",
        credit=-2.0,
        basis=(
            "Сеть автохаусов BUTIKAVTO (с 2023, 2900+ автомобилей, 13 городов); "
            "молодой эмитент — первый выпуск облигаций (Оп1, 06/2026), кредитная "
            "история короткая."
        ),
        sources=("butikavto.by", "bikratings.by"),
    ),
    IssuerProfile(
        key="np-service",
        aliases=("нп-сервис", "нп сервис"),
        kind="logistics",
        credit=-5.0,
        basis=(
            "Дистрибуция продуктов и логистика (с 2000); по облигациям эмитента "
            "фиксировался ДЕФОЛТ в 2022 году; рентабельность продаж −41,1% "
            "(1 пол. 2024), выручка −50% г/г; обслуживание текущих выпусков "
            "продолжается (Оп37/40/45/46)."
        ),
        sources=("cbonds.com", "myfin.by"),
    ),
)


def lookup_issuer_profile(issuer: str | None) -> IssuerProfile | None:
    """Найти профиль эмитента по названию (регистр/оргформа не важны)."""
    norm = _normalize(issuer or "")
    if not norm:
        return None
    for profile in PROFILES:
        for alias in profile.aliases:
            if alias in norm:
                return profile
    return None


def credit_for_issuer(
    issuer: str | None, financials: IssuerFinancials | None = None
) -> tuple[float, str]:
    """Resolve a credit score + basis for an issuer.

    Prefers real parsed financials (``scoring.financials``) when supplied, blended
    50/50 with the static expert profile so a single filing cannot swing the
    rating but genuine data still moves it. Falls back to the profile alone.
    """
    profile = lookup_issuer_profile(issuer)
    base_credit = profile.credit if profile else 0.0
    base_basis = (
        profile.basis
        if profile
        else "Профиль эмитента не найден; применена нейтральная оценка."
    )

    if financials is not None:
        fin_score, fin_basis = score_from_financials(financials)
        credit = max(-6.0, min(12.0, base_credit * 0.5 + fin_score * 0.5))
        basis = f"{base_basis} | Данные отчётности: {fin_basis}"
        return credit, basis

    return base_credit, base_basis