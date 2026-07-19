"""Lightweight API-side localization for CIS markets.

The partner API is consumed by B2B integrators across the CIS, so its
human-readable messages are localized via ``Accept-Language`` (or an explicit
``?lang=`` query param). Data fields are locale-neutral JSON; only status /
error text is translated. Supported languages: Russian (default), English,
Kazakh.
"""

from __future__ import annotations

from fastapi import Request

SUPPORTED = ("ru", "en", "kz")
DEFAULT_LANG = "ru"

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "not_authenticated": "Отсутствует заголовок X-Aigenis-Api-Key",
        "invalid_api_key": "Неверный или неактивный API-ключ",
        "rate_limited": "Превышен лимит запросов партнёра",
        "key_created": "API-ключ создан. Сохраните его — он больше не показывается.",
        "key_revoked": "API-ключ отозван",
        "webhook_registered": "Webhook зарегистрирован",
        "webhook_deleted": "Webhook удалён",
        "invalid_url": "URL webhook должен начинаться с http:// или https://",
        "event_unsupported": "Неподдерживаемый тип события: {event}",
        "event_dispatched": "Событие отправлено в {count} webhook(ов)",
        "bond_not_found": "Облигация {bond} не найдена",
        "partner_only": "Этот эндпоинт доступен только по партнёрскому ключу",
    },
    "en": {
        "not_authenticated": "Missing X-Aigenis-Api-Key header",
        "invalid_api_key": "Invalid or inactive API key",
        "rate_limited": "Partner rate limit exceeded",
        "key_created": "API key created. Store it safely — it will not be shown again.",
        "key_revoked": "API key revoked",
        "webhook_registered": "Webhook registered",
        "webhook_deleted": "Webhook deleted",
        "invalid_url": "Webhook URL must start with http:// or https://",
        "event_unsupported": "Unsupported event type: {event}",
        "event_dispatched": "Event dispatched to {count} webhook(s)",
        "bond_not_found": "Bond {bond} not found",
        "partner_only": "This endpoint is available only with a partner key",
    },
    "kz": {
        "not_authenticated": "X-Aigenis-Api-Key тақырыпшасы жоқ",
        "invalid_api_key": "Қате немесе белсенді емес API кілті",
        "rate_limited": "Серіктес сұраныстарының шегі асып кетті",
        "key_created": "API кілті жасалды. Оны сақтаңыз — ол қайта көрсетілмейді.",
        "key_revoked": "API кілті кері қайтарылды",
        "webhook_registered": "Webhook тіркелді",
        "webhook_deleted": "Webhook жойылды",
        "invalid_url": "Webhook URL http:// немесе https:// басталуы керек",
        "event_unsupported": "Қолдау көрсетілмейтін оқиға түрі: {event}",
        "event_dispatched": "Оқиға {count} webhook-қа жіберілді",
        "bond_not_found": "{bond} облигациясы табылмады",
        "partner_only": "Бұл эндпоинт тек серіктес кілтімен қол жетімді",
    },
}


def get_lang(request: Request | None = None, lang: str | None = None) -> str:
    if lang and lang.lower() in SUPPORTED:
        return lang.lower()
    if request is not None:
        accept = request.headers.get("accept-language", "")
        for part in accept.split(","):
            code = part.split(";")[0].strip().lower()
            if code in SUPPORTED:
                return code
    return DEFAULT_LANG


def tr(lang: str, key: str, **kwargs: object) -> str:
    table = _TRANSLATIONS.get(lang, _TRANSLATIONS[DEFAULT_LANG])
    msg = table.get(key) or _TRANSLATIONS[DEFAULT_LANG].get(key, key)
    return msg.format(**kwargs) if kwargs else msg
