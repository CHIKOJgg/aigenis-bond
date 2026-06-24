from __future__ import annotations


class ScraperError(Exception):
    """Базовый класс ошибок парсера."""


class TransientError(ScraperError):
    """Временная ошибка: таймаут, 5xx, сетевая. Подлежит retry."""


class FatalError(ScraperError):
    """Неустранимая ошибка: капча, блокировка, изменение структуры. Алерт + стоп."""


class NotFoundError(ScraperError):
    """Запрашиваемая сущность не найдена (например, облигация снята с торгов)."""


class HistoryUnavailable(ScraperError):
    """История недоступна для данной облигации (не отдаётся API)."""


class ParseError(ScraperError):
    """Не удалось распарсить ответ — структура изменилась или данные грязные."""
