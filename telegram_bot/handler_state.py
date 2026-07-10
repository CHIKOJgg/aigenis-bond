"""Shared, import-cycle-free state for the Telegram handlers.

Kept separate from the handler modules so that `commands`, `menus`,
`bond_picker`, `settings` and `admin` can reference the same pagination sizes,
parse lock and per-user edit state without creating circular imports.
"""
from __future__ import annotations

import asyncio

# Pagination sizes (items per page) for list-style responses.
PAGE_SIZE = 10
BOND_PAGE = 8

# Process-wide lock ensuring only one user runs the scraper at a time.
parse_lock = asyncio.Lock()

# Per-user state for inline settings editing (lightweight FSM, no storage needed).
pending_edit: dict[int, str] = {}
