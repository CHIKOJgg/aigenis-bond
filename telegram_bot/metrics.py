"""Prometheus метрики для Telegram-бота."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

bot_commands = Counter("bot_commands_total", "Commands by type", ["command"])
bot_errors = Counter("bot_errors_total", "Errors by type", ["error_type"])
bot_latency = Histogram("bot_command_seconds", "Command latency", ["command"])
db_query_time = Histogram(
    "db_query_seconds", "DB query latency", buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)
