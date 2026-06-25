from __future__ import annotations

import pytest
from sqlalchemy import text as sa_text

from scraper.db import check_db_health, dispose, get_engine, session_scope


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    await dispose()


async def test_get_engine():
    engine = get_engine()
    assert engine is not None


async def test_session_scope():
    async with session_scope() as session:
        result = await session.execute(sa_text("SELECT 1 AS val"))
        row = result.one()
        assert row.val == 1


async def test_session_scope_rollback_on_error():
    class TestExceptionError(Exception):
        pass

    with pytest.raises(TestExceptionError):
        async with session_scope() as session:
            await session.execute(sa_text("SELECT 1"))
            raise TestExceptionError("rollback test")


async def test_check_db_health():
    result = await check_db_health()
    assert result["status"] == "ok"
    assert result.get("error") is None


async def test_dispose():
    engine = get_engine()
    assert engine is not None
    await dispose()
    from scraper.db import _engine

    assert _engine is None
