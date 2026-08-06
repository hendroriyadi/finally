"""Tests for idempotent lazy schema creation and seeding."""

from __future__ import annotations

import asyncio

from app.db.connection import connect
from app.db.init import init_db
from app.market.seed_prices import SEED_PRICES

EXPECTED_TABLES = {
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
}


async def test_all_tables_created(temp_db):
    await init_db()

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        conn.close()

    table_names = {row["name"] for row in rows}
    assert EXPECTED_TABLES.issubset(table_names)


async def test_seeds_ten_default_tickers(temp_db):
    await init_db()

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ticker FROM watchlist ORDER BY added_at, rowid"
        ).fetchall()
    finally:
        conn.close()

    tickers = [row["ticker"] for row in rows]
    assert tickers == list(SEED_PRICES.keys())


async def test_init_is_idempotent(temp_db):
    await init_db()

    conn = connect()
    try:
        users_before = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0]
        watchlist_before = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
    finally:
        conn.close()

    await init_db()

    conn = connect()
    try:
        users_after = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0]
        watchlist_after = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
    finally:
        conn.close()

    assert users_after == users_before == 1
    assert watchlist_after == watchlist_before == len(SEED_PRICES)


async def test_concurrent_init_db_calls_do_not_raise(temp_db):
    """WR-04: init_db()'s own doc comment claims it is safe to call on every
    startup. Before the INSERT OR IGNORE fix, two concurrent calls against
    the same fresh database file could both observe `existing == 0` and
    both attempt the seed INSERT, and the loser would raise an unhandled
    `sqlite3.IntegrityError` on the `users_profile` primary key. Running
    several `init_db()` calls concurrently (via asyncio.to_thread's real
    thread pool, hitting the same on-disk file) must not raise, and must
    leave exactly one seeded copy of the data."""
    await asyncio.gather(*(init_db() for _ in range(8)))

    conn = connect()
    try:
        users = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0]
        watchlist = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
    finally:
        conn.close()

    assert users == 1
    assert watchlist == len(SEED_PRICES)
