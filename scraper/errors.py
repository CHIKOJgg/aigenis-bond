from __future__ import annotations

from typing import Any


class ScraperError(Exception):
    """Base scraper exception."""

    def __init__(
        self, message: str, *, cause: Exception | None = None, context: dict[str, Any] | None = None
    ) -> None:
        self.message = message
        self.cause = cause
        self.context = context or {}
        super().__init__(message)


class TransientError(ScraperError):
    """Temporary: timeout, 5xx, network. Eligible for retry."""


class FatalError(ScraperError):
    """Permanent: captcha, block, structural change. Alert + stop."""


class NotFoundError(ScraperError):
    """Entity not found (bond delisted, missing page)."""


class HistoryUnavailableError(ScraperError):
    """History API unavailable for this bond."""


HistoryUnavailable = HistoryUnavailableError


class ParseError(ScraperError):
    """Failed to parse response — structure changed or data dirty."""


class ValidationError(ScraperError):
    """Data validation failed."""


class DatabaseError(ScraperError):
    """Database operation error."""


class ConfigError(ScraperError):
    """Configuration error (missing env, bad value)."""


class CircuitBreakerOpenError(ScraperError):
    """Circuit breaker is open — service unavailable."""


class RateLimitError(TransientError):
    """Rate limited by upstream."""


class BrowserNotAvailableError(TransientError):
    """Playwright browser not available."""


BrowserNotAvailable = BrowserNotAvailableError
