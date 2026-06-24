"""Notifications модуль: формирование и доставка алертов."""

from __future__ import annotations

from notifications.repository import add_alert, list_recent

__all__ = ["add_alert", "list_recent"]
