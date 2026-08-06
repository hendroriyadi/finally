"""Idempotent lazy schema creation and seeding.

``init_db()`` is safe to call on every backend startup, including
concurrently: the DDL is entirely ``CREATE TABLE IF NOT EXISTS`` /
``CREATE INDEX IF NOT EXISTS``, and the seed step uses ``INSERT OR IGNORE``
on the ``users_profile`` primary key so a database that already has a
``users_profile`` row is never re-seeded. Because the "already seeded?"
check and the insert are the same atomic statement (rather than a separate
``SELECT COUNT(*)`` followed by an ``INSERT``), two concurrent ``init_db()``
calls against the same database file can never both observe "not yet
seeded" and both attempt the insert — SQLite serializes the writes, and the
loser's ``INSERT OR IGNORE`` simply no-ops instead of raising an unhandled
``IntegrityError``.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.market.seed_prices import SEED_PRICES

from .connection import DEFAULT_USER_ID, run_db

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
DEFAULT_CASH_BALANCE = 10000.0


async def init_db() -> None:
    """Create the schema (if missing) and seed default data (if not already seeded)."""

    def _init(conn: sqlite3.Connection) -> None:
        conn.executescript(SCHEMA_PATH.read_text())

        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, now),
        )
        if cur.rowcount > 0:
            # This connection won the race to seed — no other concurrent
            # init_db() call can also reach here for the same user_id, since
            # the INSERT above is what settles who seeds (see module doc).
            for ticker in SEED_PRICES:  # dict preserves insertion order (Python 3.7+)
                conn.execute(
                    "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, now),
                )
            logger.info("Database seeded: %d default watchlist tickers", len(SEED_PRICES))
        else:
            logger.info("Database already initialized; skipping seed")

    await run_db(_init)
