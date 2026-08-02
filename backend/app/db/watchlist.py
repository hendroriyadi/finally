"""Watchlist data access — list, add, remove, count.

Every statement in this module uses `?` placeholders; no value is ever
interpolated into SQL text, even a ticker that has already passed shape
validation upstream. Parameterization is the mitigation for T-01-01; shape
validation in the route layer is defense in depth, not a substitute.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone

from .connection import DEFAULT_USER_ID, run_db

logger = logging.getLogger(__name__)

# Substring of the sqlite3 error message raised for the (user_id, ticker)
# UNIQUE constraint on `watchlist`. Used to distinguish an expected duplicate
# from any other integrity violation on the same INSERT (WR-03) — sqlite3
# does not give a structured error code here, only a formatted message, so a
# substring match is the only way to tell them apart short of parsing
# `sqlite_master` for the constraint name ourselves.
_DUPLICATE_TICKER_CONSTRAINT = "UNIQUE constraint failed: watchlist.user_id, watchlist.ticker"


class WatchlistCapReachedError(Exception):
    """Raised when an `add_watchlist_ticker(..., max_size=...)` call is
    blocked by the size cap rather than a duplicate-ticker conflict."""


async def list_watchlist(user_id: str = DEFAULT_USER_ID) -> list[dict[str, str]]:
    """Return the persisted watchlist for `user_id`, ordered by added_at then rowid."""

    def _query(conn: sqlite3.Connection) -> list[dict[str, str]]:
        cur = conn.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at, rowid",
            (user_id,),
        )
        return [{"ticker": row["ticker"], "added_at": row["added_at"]} for row in cur.fetchall()]

    return await run_db(_query)


async def count_watchlist(user_id: str = DEFAULT_USER_ID) -> int:
    """Return the number of watchlist rows for `user_id`."""

    def _count(conn: sqlite3.Connection) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM watchlist WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

    return await run_db(_count)


async def add_watchlist_ticker(
    ticker: str,
    user_id: str = DEFAULT_USER_ID,
    *,
    max_size: int | None = None,
) -> dict[str, str] | None:
    """Insert a new watchlist row for `ticker`.

    Returns the created row's `ticker`/`added_at` dict, or `None` if the
    ticker is already on the watchlist (detected via the (user_id, ticker)
    unique constraint's IntegrityError — the database's own constraint is the
    duplicate detector, which keeps this race-free without a separate read).

    When `max_size` is given, the cap is enforced as part of the same atomic
    statement as the insert: `INSERT ... SELECT ... WHERE (SELECT COUNT(*)
    ...) < max_size`. SQLite executes this single compound statement under
    its writer lock, so two concurrent callers can never both observe room
    under the cap and both insert — unlike a separate `count_watchlist()`
    check followed by an insert, which is a check-then-act race. If the
    WHERE clause blocks the insert, 0 rows are affected and
    `WatchlistCapReachedError` is raised. Pass `max_size=None` (the default)
    to skip cap enforcement entirely — used for compensating re-inserts after
    a downstream failure, where the original insert already passed the cap.
    """
    row_id = str(uuid.uuid4())
    added_at = datetime.now(timezone.utc).isoformat()

    def _insert(conn: sqlite3.Connection) -> dict[str, str] | None:
        try:
            if max_size is None:
                conn.execute(
                    "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                    (row_id, user_id, ticker, added_at),
                )
            else:
                cur = conn.execute(
                    """
                    INSERT INTO watchlist (id, user_id, ticker, added_at)
                    SELECT ?, ?, ?, ?
                    WHERE (SELECT COUNT(*) FROM watchlist WHERE user_id = ?) < ?
                    """,
                    (row_id, user_id, ticker, added_at, user_id, max_size),
                )
                if cur.rowcount == 0:
                    raise WatchlistCapReachedError(
                        f"watchlist for {user_id!r} is already at max_size={max_size}"
                    )
        except sqlite3.IntegrityError as exc:
            if _DUPLICATE_TICKER_CONSTRAINT not in str(exc):
                # Not the (user_id, ticker) uniqueness violation we expect —
                # log the original exception at error level so a genuinely
                # different integrity failure isn't silently misreported to
                # the caller as "already on the watchlist" (WR-03).
                logger.error(
                    "add_watchlist_ticker(%r, %r): unexpected IntegrityError, "
                    "not the duplicate-ticker constraint: %s",
                    ticker,
                    user_id,
                    exc,
                )
            else:
                logger.debug("add_watchlist_ticker(%r, %r): duplicate ticker", ticker, user_id)
            return None
        return {"ticker": ticker, "added_at": added_at}

    return await run_db(_insert)


async def remove_watchlist_ticker(ticker: str, user_id: str = DEFAULT_USER_ID) -> bool:
    """Delete the watchlist row for `ticker`. Returns True if a row was removed."""

    def _delete(conn: sqlite3.Connection) -> bool:
        cur = conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        )
        return cur.rowcount > 0

    return await run_db(_delete)
