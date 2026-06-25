from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

# Simple in-process metrics without external dependency
# In production, replace with prometheus_client

_metrics: dict[str, float | int | dict[str, Any]] = {
    "scrape_total": 0,
    "scrape_errors": 0,
    "api_requests": 0,
    "api_errors": 0,
    "bot_commands": 0,
    "bot_errors": 0,
    "last_scrape_duration_ms": 0,
    "last_scrape_at": 0,
    "bonds_total": 0,
    "started_at": time.time(),
}


def inc(name: str, value: float = 1) -> None:
    _metrics[name] = _metrics.get(name, 0) + value


def set_metric(name: str, value: float | int) -> None:
    _metrics[name] = value


def get_metrics() -> dict[str, Any]:
    return {**_metrics, "uptime_seconds": time.time() - _metrics.get("started_at", time.time())}


def timed(name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.monotonic()
            try:
                return fn(*args, **kwargs)
            finally:
                set_metric(f"last_{name}_duration_ms", (time.monotonic() - start) * 1000)

        return wrapper

    return decorator


async def timed_async(name: str, coro):
    start = time.monotonic()
    try:
        return await coro
    finally:
        set_metric(f"last_{name}_duration_ms", (time.monotonic() - start) * 1000)
