"""Educational SEO guides: /guides and /guides/{slug} (top-of-funnel organic surface).

Each guide is its own indexable page with internal links to /bonds + /partners.
"""

from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import HTMLResponse

from api.seo import router
from api.seo._common import SITE_NAME, _abs, _esc, _skeleton

# ---------------------------------------------------------------------------
# Educational guides (top-of-funnel organic surface, audit §2 long-tail).
# Each guide is its own indexable page with internal links to /bonds + /partners.
# ---------------------------------------------------------------------------

_GUIDES: list[dict] = [
    {
        "slug": "kak-vybrat-obligaciyu",
        "title": "Как выбрать облигацию в 2026: чек-лист инвестора",
        "description": "Пошаговый разбор: доходность к погашению, риск эмитента, "
        "дюрация, налоги и ликвидность. С чем сравнивать и на что "
        "смотреть до покупки.",
        "updated": "2026-07-01",
        "body": """
<h2>1. Доходность к погашению (YTM)</h2>
<p>Смотрите на <b>YTM</b>, а не на купонную ставку. YTM уже учитывает цену покупки,
купоны и номинал — это ваша реальная доходность, если держать до погашения.
Актуальный <a href="/bonds">рейтинг облигаций по доходности</a> виден на отдельной странице.</p>
<h2>2. Риск эмитента</h2>
<p>Государственные и квазигосударственные — надёжнее корпоративных. Для корпоратов
смотрите отрасль, долговую нагрузку и то, есть ли у эмитента история выплат.
Наш <a href="/bonds">Score 0–100</a> сжимает эти факторы в одну оценку риска/доходности.</p>
<h2>3. Дюрация и срок</h2>
<p>Чем длиннее срок, тем выше процентный риск: при росте ставок длинные облигации
дешевеют сильнее. <a href="/guides/duration-i-repo-prosto">Что такое Duration — разбор простыми словами →</a></p>
<h2>4. Ликвидность и налоги</h2>
<p>Проверьте, торгуется ли выпуск реальным объёмом, а не только на бумаге. Учитывайте
НДФЛ с купонов/дохода — он влияет на чистую доходность.</p>
<h2>5. Диверсификация</h2>
<p>Не держите всё в одном эмитенте и валюте. Распределяйте между RUB/USD/EUR и
металлами. <a href="/guides/obligacii-vs-depozit">Облигации против депозита →</a></p>
<p class="note">Готовый шорт-лист с Score и YTM — на странице <a href="/bonds">рейтинга облигаций</a>.
Для брокеров и финтеха доступен <a href="/partners">white-label и Bond API</a>.</p>
""",
    },
    {
        "slug": "duration-i-repo-prosto",
        "title": "Duration и РЕПО простыми словами",
        "description": "Что такое дюрация облигации, почему она важна при изменении "
        "ставок, и как работает сделка РЕПО с облигациями.",
        "updated": "2026-07-01",
        "body": """
<h2>Что такое Duration</h2>
<p><b>Дюрация</b> — мера чувствительности цены облигации к процентным ставкам.
Грубо: если ставка вырастет на 1%, цена облигации упадёт примерно на значение
дюрации (в годах). Чем дюрация выше, тем больше ценовой риск при росте ставок
и тем больше потенциал роста цены при их снижении.</p>
<h2>Зачем это инвестору</h2>
<p>Если ждёте снижения ставок — длинные облигации (высокая дюрация) дадут больше
капитального роста. Если ставки растут — короткие безопаснее. Наша Desk-аналитика
считает duration по портфелю и по каждой бумаге отдельно.</p>
<h2>Что такое РЕПО</h2>
<p><b>РЕПО</b> — сделка «облигация в залог под деньги» с обязательством выкупа.
Кредитор получает облигацию и процент (ставка РЕПО), заёмщик — ликвидность,
оставляя бумагу у себя. Для трейдера это способ плеча или краткосрочного фондирования.</p>
<h2>Связь с выбором</h2>
<p>Дюрация помогает балансировать портфель под свой взгляд на ставку, а РЕПО —
управлять ликвидностью. Начните с <a href="/guides/kak-vybrat-obligaciyu">чека-листа выбора облигации →</a>
и актуального <a href="/bonds">рейтинга по доходности</a>.</p>
<p class="note">Desk-инструменты (Duration, РЕПО, Carry, стресс-тесты) доступны по
<a href="/partners">B2B/white-label</a> и в тарифах Pro/Enterprise.</p>
""",
    },
    {
        "slug": "obligacii-vs-depozit",
        "title": "Облигации vs депозит: что выгоднее в 2026",
        "description": "Сравниваем доходность, риски, сроки и налоги облигаций и "
        "банковского вклада — и когда что имеет смысл.",
        "updated": "2026-07-01",
        "body": """
<h2>Доходность</h2>
<p>Качественные корпоративные и гособлигации часто дают доходность выше, чем
средний депозит той же валюты/срока, особенно на горизонте 1–3 лет.
Сравните на <a href="/bonds">странице рейтинга облигаций</a> (колонка YTM).</p>
<h2>Риск</h2>
<p>Депозит застрахован (в пределах лимита ФГВ/аналога), облигации — нет, но риск
зависит от эмитента. Гособлигации и бумаги надёжных эмитентов близки к депозиту
по надёжности. Наш <a href="/bonds">Score</a> помогает отсеять слабых эмитентов.</p>
<h2>Ликвидность</h2>
<p>Депозит обычно нельзя снять досрочно без потери %, облигацию можно продать
на рынке (цену определит спрос). Дюрация и рыночная цена дадут просадку при
росте ставок — см. <a href="/guides/duration-i-repo-prosto">разбор дюрации →</a>.</p>
<h2>Налоги</h2>
<p>И с купонов, и с депозитных процентов берётся НДФЛ. Считайте чистую доходность
после налога, а не «на витрине».</p>
<h2>Итог</h2>
<p>Облигации — гибче и часто доходнее при том же горизонте, депозит — проще и
застрахован. Разумно комбинировать. Начните с <a href="/guides/kak-vybrat-obligaciyu">чека-листа выбора →</a>.</p>
<p class="note">Для встраивания рейтинга облигаций на свой сайт — <a href="/partners">виджет и API</a>.</p>
""",
    },
]


@router.get("/guides", response_class=HTMLResponse)
async def seo_guides_index(request: Request):
    title = f"Гайды по облигациям | {SITE_NAME}"
    desc = (
        "Бесплатные разборы: как выбрать облигацию, что такое Duration и РЕПО, "
        "облигации против депозита. С внутренними ссылками на живой рейтинг."
    )
    items = "".join(
        f'<div class="card"><h2 style="margin-top:0"><a href="/guides/{_esc(g["slug"])}">'
        f'{_esc(g["title"])}</a></h2><p class="sub">{_esc(g["description"])}</p></div>'
        for g in _GUIDES
    )
    body = (
        f"<h1>Гайды по облигациям</h1>"
        f"<p class='sub'>Короткие практические разборы по фиксированному доходу. "
        f"Каждый — с переходом к живому <a href='/bonds'>рейтингу облигаций</a>.</p>"
        f"{items}"
        f"<p class='note'>Для бизнеса — white-label, виджет и Bond API: "
        f"<a href='/partners'>Aigenis Bonds для бизнеса →</a>.</p>"
    )
    json_ld = [
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "CollectionPage",
                "name": title,
                "description": desc,
                "url": _abs(request, "/guides"),
                "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": _abs(request, "/")},
            },
            ensure_ascii=False,
        )
    ]
    return _skeleton(title, desc, body, request, _abs(request, "/guides"), json_ld)


@router.get("/guides/{slug}", response_class=HTMLResponse)
async def seo_guide_detail(request: Request, slug: str):
    guide = next((g for g in _GUIDES if g["slug"] == slug), None)
    if guide is None:
        not_found = (
            "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
            f"<title>Гайд не найден | {_esc(SITE_NAME)}</title></head>"
            "<body style='font-family:system-ui;max-width:640px;margin:80px auto;padding:0 18px'>"
            f"<h1>Гайд не найден</h1>"
            f"<p><a href='{_esc(_abs(request, '/guides'))}'>← Все гайды</a></p></body></html>"
        )
        return HTMLResponse(content=not_found, status_code=404)
    title = guide["title"]
    desc = guide["description"]
    body = (
        f"<h1>{_esc(title)}</h1>"
        f"<p class='sub'>{_esc(desc)}</p>"
        f"{guide['body']}"
        f"<p class='note'>Смотрите живой <a href='/bonds'>рейтинг облигаций</a> · "
        f"<a href='/partners'>Aigenis Bonds для бизнеса →</a> · "
        f"<a href='/guides'>Все гайды →</a></p>"
    )
    json_ld = [
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": title,
                "description": desc,
                "dateModified": guide["updated"],
                "publisher": {"@type": "Organization", "name": SITE_NAME},
                "mainEntityOfPage": {"@type": "WebPage", "url": _abs(request, f"/guides/{slug}")},
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "Гайды",
                        "item": _abs(request, "/guides"),
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": title,
                        "item": _abs(request, f"/guides/{slug}"),
                    },
                ],
            },
            ensure_ascii=False,
        ),
    ]
    return _skeleton(title, desc, body, request, _abs(request, f"/guides/{slug}"), json_ld)
