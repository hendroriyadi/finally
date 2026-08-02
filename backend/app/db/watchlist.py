"""Watchlist data access — list, add, remove, count.

Every statement in this module uses `?` placeholders; no value is ever
interpolated into SQL text, even a ticker that has already passed shape
validation upstream. Parameterization is the mitigation for T-01-01; shape
validation in the route layer is defense in depth, not a substitute.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from .connection import DEFAULT_USER_ID, run_db


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
    ticker: str, user_id: str = DEFAULT_USER_ID
) -> dict[str, str] | None:
    """Insert a new watchlist row for `ticker`.

    Returns the created row's `ticker`/`added_at` dict, or `None` if the
    ticker is already on the watchlist (detected via the (user_id, ticker)
    unique constraint's IntegrityError — the database's own constraint is the
    duplicate detector, which keeps this race-free without a separate read).
    """
    row_id = str(uuid.uuid4())
    added_at = datetime.now(timezone.utc).isoformat()

    def _insert(conn: sqlite3.Connection) -> dict[str, str] | None:
        try:
            conn.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                (row_id, user_id, ticker, added_at),
            )
        except sqlite3.IntegrityError:
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
