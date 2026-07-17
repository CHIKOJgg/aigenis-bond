"""Централизованная инициализация Sentry.

Раньше ``sentry_dsn`` был прописан в конфиге, но нигде не инициализировался —
ошибки в боевом окружении молча терялись. Теперь Sentry включается по
умолчанию, как только задан ``SENTRY_DSN``. В проде (environment !=
"development") при отсутствии DSN пишется предупреждение, чтобы оператор
заметил отсутствие телеметрии.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_sentry(dsn: str | None, *, environment: str = "production", release: str | None = None) -> bool:
    """Инициализировать Sentry, если задан DSN.

    Возвращает True, если клиент реально включён.
    """
    if not dsn:
        if environment not in ("development", "test", "local"):
            logger.warning(
                "SENTRY_DSN не задан в окружении '%s': ошибки не будут отправляться "
                "в Sentry. Задайте SENTRY_DSN для получения телеметрии в проде.",
                environment,
            )
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.aiohttp import AioHttpIntegration
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:
        logger.warning("sentry_sdk не установлен; телеметрия отключена.")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=[
            AioHttpIntegration(),
            AsyncioIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.0,
        send_default_pii=False,
        attach_stacktrace=True,
    )
    logger.info("Sentry инициализирован (env=%s).", environment)
    return True
