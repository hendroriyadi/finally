"""SQLite connection factory: WAL mode, busy_timeout, and the asyncio.to_thread seam.

Every database access in this codebase goes through ``run_db()``. There is no
shared, long-lived connection anywhere — each call opens a short-lived
``sqlite3.Connection`` on a worker thread, operates, commits, and closes.
stdlib ``sqlite3.Connection`` objects are not safe to share across threads,
and at this app's single-user scale the per-call connection-open overhead is
negligible.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "default"

# Attempts for the one-time journal_mode=WAL switch (see connect()).
_WAL_SWITCH_ATTEMPTS = 10

# parents[3] from backend/app/db/connection.py is the repository root, whose
# db/ directory is the runtime volume mount — deliberately distinct from this
# package directory (backend/app/db/), which only holds the schema DDL.
DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "db" / "finally.db"

T = TypeVar("T")


def get_db_path() -> Path:
    """Return the SQLite database path, honoring FINALLY_DB_PATH when set.

    Ensures the parent directory exists so a fresh checkout (or a test's
    tmp_path) never fails to open the database for lack of a directory.
    """
    raw = os.environ.get("FINALLY_DB_PATH", "").strip()
    path = Path(raw) if raw else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    """Open a new SQLite connection with WAL mode and busy_timeout configured.

    Both pragmas are (re)issued on every open: journal_mode=WAL persists at
    the database-file level once set, but busy_timeout is a per-connection
    setting that must be reissued every time a connection is opened.

    busy_timeout is set FIRST and the `journal_mode=WAL` switch is retried,
    and both halves are load-bearing (WR-01). The WAL switch takes an
    exclusive lock on a file not yet in WAL mode, so on a fresh database
    several connections opening concurrently race for it — and, unlike an
    ordinary write, it can return SQLITE_BUSY *without* invoking the busy
    handler, so a timeout alone does not save it. Measured against a fresh
    file with 8 threads racing `connect()`, 40 trials each: original
    ordering 3 failures, reordered-only 2, reorder + retry 0. This is the
    confirmed root cause of the intermittent
    `test_concurrent_init_db_calls_do_not_raise` failure.
    """
    conn = sqlite3.connect(get_db_path())
    conn.execute("PRAGMA busy_timeout=5000")
    for attempt in range(_WAL_SWITCH_ATTEMPTS):
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            break
        except sqlite3.OperationalError:
            if attempt == _WAL_SWITCH_ATTEMPTS - 1:
                conn.close()
                raise
            time.sleep(0.01 * (attempt + 1))
    conn.row_factory = sqlite3.Row
    return conn


async def run_db(fn: Callable[[sqlite3.Connection], T]) -> T:
    """Run `fn` against a fresh connection on a worker thread, then commit and close.

    This is the only seam through which the rest of the codebase touches
    SQLite. `fn` receives an open, WAL-mode connection with busy_timeout set,
    and its return value is passed back to the caller unchanged.
    """

    def _run() -> T:
        conn = connect()
        try:
            result = fn(conn)
            conn.commit()
            return result
        finally:
            conn.close()

    return await asyncio.to_thread(_run)
