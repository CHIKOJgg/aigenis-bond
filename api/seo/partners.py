"""Public B2B acquisition pages: /partners + self-serve lead form + key issue.

The product ships the B2B plumbing (Partner API keys, webhooks, read-only
analytics, affiliate referrals, embeddable widget) — this is its public
conversion surface. Leads get an instant self-served trial key.
"""

from __future__ import annotations

import html
import json
import os
import secrets as _secrets

from fastapi import Form, Request
from fastapi.responses import HTMLResponse

from api.partner.security import generate_api_key
from api.seo import router
from api.seo._common import BOT_USERNAME, SITE_NAME, _abs, _app_links, _esc, _skeleton
from scraper.config import get_settings
from scraper.db import session_scope
from scraper.logging import get_logger
from scraper.orm import PartnerKeyORM, PartnerLeadORM

logger = get_logger("api.seo")


@router.get("/partners", response_class=HTMLResponse)
async def seo_partners(request: Request):
    """Public B2B / white-label acquisition page (see docs/aigenis/negotiation-guide.md).

    The product already ships the B2B plumbing (Partner API keys, webhooks,
    read-only analytics, affiliate referrals, embeddable widget, demo mode) but
    had no public surface to convert brokers / fintech / EdTech leads. This page
    is that surface: it explains the offer and funnels leads to the bot.
    """
    _web, _bot = _app_links(request)
    partner_bot = f"https://t.me/{BOT_USERNAME}?start=partner" if BOT_USERNAME else _web
    title = f"{SITE_NAME} для бизнеса: white-label аналитика облигаций | B2B"
    desc = (
        "Встройте аналитику облигаций (скоринг, Desk, ML) в своё приложение "
        "или сайт: виджет, Bond API, white-label и партнёрская программа с %."
    )

    features = [
        (
            "Виджет за 1 строку",
            "iframe «Топ облигаций» на вашем сайте или в блоге. "
            "Бесплатно, с вашим дизайном, ведёт трафик в вашу воронку.",
        ),
        (
            "Bond API",
            "Программный доступ к скорингу 0–100, Desk-аналитике "
            "(duration, кривая, RV, carry, РЕПО, стресс-тесты) и ML-рекомендациям.",
        ),
        (
            "White-label",
            "Аналитика под вашим брендом — для брокеров, агрегаторов "
            "котировок и финтех-приложений. Демо-режим для быстрого показа.",
        ),
        (
            "Партнёрская программа",
            "Affiliate: % с приведённых подписок через "
            "реферальный код. Подходит блогерам и каналам по инвестициям.",
        ),
    ]
    cards = "".join(
        f'<div class="card"><h2 style="margin-top:0">{_esc(t)}</h2>'
        f'<p class="sub">{_esc(d)}</p></div>'
        for t, d in features
    )

    body = f"""<h1>{SITE_NAME} для бизнеса</h1>
<p class="sub">Аналитика облигаций фиксированного дохода «под ключ»: встройте за день
через виджет или API и монетизируйте свой трафик.</p>
{cards}
<h2>Кому подходит</h2>
<ul>
  <li><b>Брокеры / агрегаторы котировок</b> — white-label аналитика на вашем бренде.</li>
  <li><b>Финтех-приложения</b> — виджет «Топ облигаций» и Bond API.</li>
  <li><b>EdTech по инвестициям</b> — готовая учебная платформа с реальными данными.</li>
  <li><b>Финансовые медиа и блогеры</b> — партнёрская программа с % с подписок.</li>
</ul>
<div class="card" style="border-color:var(--brand);background:#f0f6f9">
  <h2 style="margin-top:0">Оставить заявку на B2B / white-label</h2>
  <p>Заполните форму — мы пришлём API-ключ, виджет и условия партнёрки в Telegram.
  Или сразу <a href="{_esc(partner_bot)}">напишите боту про B2B →</a>.</p>
  <form method="post" action="/partners/request" class="lead-form">
    <label>Имя *<input name="name" required maxlength="128" placeholder="Как к вам обращаться"></label>
    <label>Email<input name="email" type="email" maxlength="256" placeholder="you@company.com"></label>
    <label>Telegram (без @)<input name="telegram" maxlength="64" placeholder="username"></label>
    <label>Компания<input name="company" maxlength="128" placeholder="Название компании"></label>
    <label>Что интересно
      <select name="interest">
        <option value="white-label">White-label</option>
        <option value="api">Bond API</option>
        <option value="widget">Виджет</option>
        <option value="affiliate">Партнёрская программа</option>
        <option value="license">Лицензия / покупка</option>
      </select>
    </label>
    <label>Сообщение<textarea name="message" maxlength="2000" rows="3" placeholder="Кратко о задаче"></textarea></label>
    <button class="cta" type="submit">Отправить заявку</button>
    <span class="note">Или сразу <a href="{_esc(partner_bot)}">напишите боту →</a>
    · <a href="/bonds">Посмотреть публичные данные →</a></span>
  </form>
</div>
<p class="note">Готовые материалы для buyer/партнёра — <code>docs/aigenis/one-pager.md</code>
и <code>docs/aigenis/negotiation-guide.md</code>.</p>"""

    json_ld = [
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Service",
                "name": f"{SITE_NAME} для бизнеса",
                "description": desc,
                "url": _abs(request, "/partners"),
                "provider": {"@type": "Organization", "name": SITE_NAME},
                "areaServed": "СНГ",
                "offers": {
                    "@type": "Offer",
                    "priceCurrency": "BYN",
                    "price": "0",
                    "availability": "https://schema.org/InStock",
                },
            },
            ensure_ascii=False,
        )
    ]
    body += (
        '<p class="note">Полезные материалы: '
        '<a href="/guides/kak-vybrat-obligaciyu">Как выбрать облигацию</a> · '
        '<a href="/guides/obligacii-vs-depozit">Облигации vs депозит</a> · '
        '<a href="/bonds">Рейтинг облигаций →</a></p>'
    )
    return _skeleton(title, desc, body, request, _abs(request, "/partners"), json_ld)


async def _issue_partner_key(session, lead: PartnerLeadORM) -> tuple[str, PartnerKeyORM]:
    """Create a live Partner API key for the lead (self-serve onboarding).

    Returns ``(raw_key, key)`` — the raw key is shown only once (to the lead and
    the admin alert). Mirrors ``api.partner.router.create_partner_key``.
    """
    raw, key_hash, key_fp = generate_api_key()
    code = _secrets.token_urlsafe(8)[:10]
    key = PartnerKeyORM(
        name=(lead.company or lead.name)[:128],
        owner_user_id=None,
        key_hash=key_hash,
        key_fp=key_fp,
        # Self-served keys are an unauthenticated trial tier: listing + detail
        # work, but premium analysis (RV/ML) requires a paid key tier. The tier
        # is enforced in api/partner/router.py.
        tier="trial",
        rate_limit=30,
        active=True,
        referral_code=code,
    )
    session.add(key)
    await session.flush()
    return raw, key


async def _notify_partner_lead(
    lead: PartnerLeadORM, issued: tuple[str, PartnerKeyORM] | None = None
) -> None:
    """Best-effort Telegram alert (admin) + DM to the lead with the issued key."""
    settings = get_settings()
    tg = settings.telegram
    if not tg.bot_token:
        return
    raw_key, key = issued if issued else (None, None)

    admin_chat = (tg.alert_chat_id or (str(tg.admin_ids[0]) if tg.admin_ids else "")).strip()
    if admin_chat:
        text = (
            f"🤝 <b>Новая B2B-заявка + ключ выдан</b> (#{lead.id})\n"
            f"Имя: {html.escape(lead.name)}\n"
            f"Компания: {html.escape(lead.company or '—')}\n"
            f"Email: {html.escape(lead.email or '—')}\n"
            f"Telegram: @{html.escape(lead.telegram or '—')}\n"
            f"Интерес: {html.escape(lead.interest or '—')}\n"
            f"Ключ: <code>{html.escape(raw_key or '—')}</code>\n"
            f"Реф. код: <code>{html.escape(key.referral_code if key else '—')}</code>"
        )
        try:
            from telegram import Bot

            await Bot(token=tg.bot_token).send_message(
                chat_id=admin_chat, text=text, parse_mode="HTML"
            )
        except Exception as exc:
            logger.warning("partner_lead_admin_notify_failed", id=lead.id, error=str(exc))

    # DM the key to the lead directly (self-serve: they get instant access).
    if lead.telegram and raw_key and key:
        dm = (
            f"✅ <b>Ваш партнёрский доступ {SITE_NAME} готов!</b>\n\n"
            f"API-ключ (покажем один раз):\n<code>{html.escape(raw_key)}</code>\n\n"
            f"Реферальная ссылка (affiliate %):\n"
            f"<code>?referral_code={html.escape(key.referral_code)}</code>\n\n"
            f"Виджет и документацию — в личном кабинете / API."
        )
        try:
            from telegram import Bot

            await Bot(token=tg.bot_token).send_message(
                chat_id="@" + lead.telegram.lstrip("@"), text=dm, parse_mode="HTML"
            )
        except Exception as exc:
            logger.warning("partner_lead_dm_failed", id=lead.id, error=str(exc))


def _lead_thanks_page(
    request: Request, issued: tuple[str, PartnerKeyORM] | None = None
) -> HTMLResponse:
    if issued:
        raw_key, key = issued
        base = _abs(request, "/").rstrip("/")
        widget = f"{base}/widget/embed.js"
        ref_link = f"{base}/?referral_code={html.escape(key.referral_code)}"
        body = (
            "<h1>Доступ готов ✅</h1>"
            "<p class='sub'>Спасибо! Ваш партнёрский ключ создан — используйте его сразу. "
            "Ключ показан один раз, сохраните его.</p>"
            "<div class='card' style='border-color:var(--brand);background:#f0fdf9'>"
            "<h2 style='margin-top:0'>Ваш Partner API-ключ</h2>"
            f"<pre style='overflow:auto'><code>{html.escape(raw_key)}</code></pre>"
            "<h3>Виджет «Топ облигаций» (вставьте 1 строку)</h3>"
            f"<pre style='overflow:auto'><code>&lt;script src=\"{html.escape(widget)}\"&gt;&lt;/script&gt;</code></pre>"
            "<h3>Реферальная ссылка (affiliate % с подписок)</h3>"
            f"<pre style='overflow:auto'><code>{ref_link}</code></pre>"
            "<h3>API</h3>"
            f"<p class='note'>Заголовок <code>X-Aigenis-Api-Key: {html.escape(raw_key)}</code> → "
            f"<code>{html.escape(base)}/api/v1/partner/bonds</code></p>"
            "</div>"
            "<p><a class='cta' href='/bonds'>Открыть публичные данные →</a></p>"
        )
    else:
        body = (
            "<h1>Заявка отправлена ✅</h1>"
            "<p class='sub'>Спасибо! Мы свяжемся с вами в Telegram с API-ключом, "
            "виджетом и условиями партнёрки.</p>"
            "<p><a class='cta' href='/bonds'>Посмотреть публичные данные →</a></p>"
        )
    return _skeleton(
        "Партнёрский доступ | " + SITE_NAME, "", body, request, _abs(request, "/partners")
    )


def _lead_error_page(request: Request, error: str) -> HTMLResponse:
    body = (
        "<h1>Не получилось отправить</h1>"
        f"<p class='alarm'>{html.escape(error)}</p>"
        "<p><a class='cta' href='/partners'>← Вернуться к форме</a></p>"
    )
    resp = _skeleton("Ошибка заявки | " + SITE_NAME, "", body, request, _abs(request, "/partners"))
    resp.status_code = 400
    return resp


_lead_rate_store: dict[str, list[float]] = {}
_lead_rate_lock = __import__("threading").Lock()
_MAX_LEADS_PER_HOUR = 3  # per IP


def _client_ip(request: Request) -> str | None:
    """Resolve the caller IP, honouring a single trusted proxy hop.

    Mirrors api.billing.router._client_ip: with TRUSTED_PROXY=1 we take the
    right-most X-Forwarded-For entry (added by our own reverse proxy),
    otherwise the raw socket peer. Without this the lead-form rate limit keys
    on the shared Cloudflare edge IP and blocks every visitor after 3 leads.
    """
    if os.getenv("TRUSTED_PROXY", "").strip() in ("1", "true", "yes"):
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[-1].strip()
    return request.client.host if request.client else None


def _lead_rate_check(ip: str) -> bool:
    """Per-IP rate limit for partner lead form (3 per hour)."""
    import time as _time

    now = _time.time()
    cutoff = now - 3600
    with _lead_rate_lock:
        # Periodic cleanup to prevent unbounded memory growth.
        if len(_lead_rate_store) > 10000:
            _lead_rate_store.clear()
        hits = _lead_rate_store.get(ip, [])
        hits = [t for t in hits if t > cutoff]
        if len(hits) >= _MAX_LEADS_PER_HOUR:
            return False
        hits.append(now)
        _lead_rate_store[ip] = hits
    return True


@router.post("/partners/request", response_class=HTMLResponse)
async def seo_partners_request(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    telegram: str = Form(""),
    company: str = Form(""),
    interest: str = Form(""),
    message: str = Form(""),
):
    """Capture a B2B lead from the public /partners page and self-serve a key."""
    # Rate-limit: 3 leads per IP per hour to prevent form abuse / key spam.
    client_ip = _client_ip(request) or "unknown"
    if not _lead_rate_check(client_ip):
        return _lead_error_page(request, "Слишком много заявок. Попробуйте позже.")

    name = (name or "").strip()
    email = (email or "").strip() or None
    telegram = ((telegram or "").strip().lstrip("@")) or None
    company = (company or "").strip() or None
    interest = (interest or "").strip() or None
    message = (message or "").strip() or None

    if not name:
        return _lead_error_page(request, "Укажите имя.")
    if len(name) > 128:
        return _lead_error_page(request, "Имя слишком длинное.")
    if not email and not telegram:
        return _lead_error_page(request, "Укажите email или Telegram для связи.")

    issued: tuple[str, PartnerKeyORM] | None = None
    async with session_scope() as session:
        lead = PartnerLeadORM(
            name=name[:128],
            email=email,
            telegram=telegram,
            company=company,
            interest=interest,
            message=message,
        )
        session.add(lead)
        await session.flush()
        lead_id = lead.id
        # Self-serve onboarding: issue a live partner key immediately.
        raw_key, key = await _issue_partner_key(session, lead)
        lead.partner_key_id = key.id
        await session.flush()
        issued = (raw_key, key)
        try:
            await _notify_partner_lead(lead, issued)
        except Exception as exc:
            logger.warning("partner_lead_notify_failed", id=lead_id, error=str(exc))
    logger.info(
        "partner_lead_created", id=lead_id, interest=interest, partner_key_id=lead.partner_key_id
    )
    return _lead_thanks_page(request, issued)
