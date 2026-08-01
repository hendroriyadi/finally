"""CRUD for the watchlist table.

Tickers are normalized to stripped uppercase so "aapl" and "AAPL" hit the same
UNIQUE (user_id, ticker) row.
"""

from __future__ import annotations

import sqlite3

from .database import use_connection
from .models import DEFAULT_USER_ID, WatchlistEntry, new_id, utc_now_iso


def normalize_ticker(ticker: str) -> str:
    """Stripped uppercase form used for all watchlist/position/trade lookups."""
    return ticker.strip().upper()


def list_watchlist(
    user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> list[WatchlistEntry]:
    """All watchlist entries, oldest first."""
    with use_connection(conn) as c:
        rows = c.execute(
            "SELECT * FROM watchlist WHERE user_id = ? ORDER BY added_at ASC, rowid ASC",
            (user_id,),
        ).fetchall()
    return [WatchlistEntry.from_row(row) for row in rows]


def list_watchlist_tickers(
    user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> list[str]:
    """Just the ticker symbols, in watchlist order."""
    return [entry.ticker for entry in list_watchlist(user_id, conn=conn)]


def is_watching(
    ticker: str, user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> bool:
    """True if the ticker is already on the watchlist."""
    with use_connection(conn) as c:
        row = c.execute(
            "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, normalize_ticker(ticker)),
        ).fetchone()
    return row is not None


def add_watchlist_ticker(
    ticker: str, user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> WatchlistEntry:
    """Add a ticker. Idempotent — returns the existing entry if already watched.

    Use ``is_watching`` first if the caller needs to distinguish the two cases.
    """
    symbol = normalize_ticker(ticker)
    with use_connection(conn) as c:
        c.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (new_id(), user_id, symbol, utc_now_iso()),
        )
        row = c.execute(
            "SELECT * FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, symbol)
        ).fetchone()
    return WatchlistEntry.from_row(row)


def remove_watchlist_ticker(
    ticker: str, user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> bool:
    """Remove a ticker. Returns True if a row was deleted."""
    with use_connection(conn) as c:
        cursor = c.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, normalize_ticker(ticker)),
        )
        return cursor.rowcount > 0
