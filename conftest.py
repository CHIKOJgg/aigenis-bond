"""Root conftest: makes the project packages importable when running pytest
from the repository root without an editable install.

It also pins the test database to an in-memory SQLite instance so the suite is
hermetic (the project's ``.env`` points ``DATABASE_URL`` at a Docker Postgres
that is not reachable from CI or a dev checkout). Environment variables take
precedence over the ``.env`` file in pydantic-settings, so setting them here —
before any ``scraper.config`` settings are instantiated — is sufficient.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")
os.environ.setdefault("RATE_LIMIT_BACKEND", "memory")

# SQLite only autoincrements a plain INTEGER PRIMARY KEY, not BIGINT. Render the
# ORM's BigInteger primary keys as INTEGER on the sqlite dialect so the test
# suite can exercise the real ORM against in-memory SQLite. (Postgres keeps
# BIGINT in production.)
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import Function


@compiles(BigInteger, "sqlite")
def _compile_bigint_as_integer(type_, compiler, **kw):  # noqa: ARG001
    return "INTEGER"


# The ORM uses ``func.true()`` / ``func.false()`` as server defaults, which
# Postgres understands natively but SQLite does not (it has no ``true()`` /
# ``false()`` functions). Render them as ``1`` / ``0`` on the sqlite dialect so
# the hermetic test suite can insert rows. Production DDL on Postgres is
# unaffected.
@compiles(Function, "sqlite")
def _compile_bool_functions_sqlite(element, compiler, **kw):
    name = (getattr(element, "name", "") or "").lower()
    if name == "true":
        return "1"
    if name == "false":
        return "0"
    return compiler.visit_function(element, **kw)

