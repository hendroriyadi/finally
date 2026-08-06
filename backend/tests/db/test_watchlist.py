"""Tests for the watchlist data-access layer's race-safety and logging."""

from __future__ import annotations

import asyncio
import logging
import sqlite3

import pytest

from app.db import connection as connection_module
from app.db.init import init_db
from app.db.watchlist import (
    WatchlistCapReachedError,
    add_watchlist_ticker,
    count_watchlist,
)


async def test_concurrent_adds_never_exceed_cap(temp_db):
    """WR-01: a size cap enforced via a separate count-then-insert is a
    check-then-act race; the atomic `INSERT ... SELECT ... WHERE COUNT(*) <
    max_size` must not let concurrent callers overrun the cap."""
    await init_db()
    baseline = await count_watchlist()
    cap = baseline + 1  # room for exactly one more ticker

    async def try_add(i: int) -> bool:
        try:
            await add_watchlist_ticker(f"X{i}", max_size=cap)
        except WatchlistCapReachedError:
            return False
        return True

    results = await asyncio.gather(*(try_add(i) for i in range(20)))

    assert sum(results) == 1
    assert await count_watchlist() == cap


async def test_add_watchlist_ticker_cap_not_enforced_when_max_size_none(temp_db):
    """Compensating re-inserts (WR-02) pass `max_size=None` (the default) to
    skip the cap entirely, since the row being restored already passed the
    cap check the first time it was inserted."""
    await init_db()
    baseline = await count_watchlist()

    with pytest.raises(WatchlistCapReachedError):
        await add_watchlist_ticker("ATCAP", max_size=baseline)

    # max_size=None (the default) never raises, regardless of the cap above.
    created = await add_watchlist_ticker("UNCAPPED")
    assert created is not None
    assert await count_watchlist() == baseline + 1


async def test_duplicate_ticker_logs_at_debug_not_error(temp_db, caplog):
    """WR-03: the expected duplicate-ticker path should not be logged as an
    error — only genuinely unexpected IntegrityErrors should be."""
    await init_db()
    await add_watchlist_ticker("ZZZZ")

    with caplog.at_level(logging.DEBUG, logger="app.db.watchlist"):
        result = await add_watchlist_ticker("ZZZZ")

    assert result is None
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    assert any("duplicate ticker" in record.message for record in caplog.records)


async def test_unexpected_integrity_error_is_logged_at_error_level(monkeypatch, caplog):
    """WR-03: an IntegrityError that is NOT the (user_id, ticker) unique
    violation must be logged loudly rather than silently reported as a
    409 duplicate, so a genuinely different integrity failure isn't hidden
    from the logs."""

    class _FakeConn:
        def execute(self, *_args, **_kwargs):
            raise sqlite3.IntegrityError("NOT NULL constraint failed: watchlist.ticker")

        def commit(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(connection_module, "connect", lambda: _FakeConn())

    with caplog.at_level(logging.ERROR, logger="app.db.watchlist"):
        result = await add_watchlist_ticker("AAPL")

    assert result is None
    assert any(
        record.levelno >= logging.ERROR and "unexpected IntegrityError" in record.message
        for record in caplog.records
    )
