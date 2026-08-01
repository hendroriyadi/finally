"""CRUD for the positions table (one row per user per ticker)."""

from __future__ import annotations

import sqlite3

from .database import use_connection
from .models import DEFAULT_USER_ID, Position, new_id, utc_now_iso
from .watchlist_repo import normalize_ticker


def list_positions(
    user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> list[Position]:
    """All held positions, alphabetical by ticker."""
    with use_connection(conn) as c:
        rows = c.execute(
            "SELECT * FROM positions WHERE user_id = ? ORDER BY ticker ASC", (user_id,)
        ).fetchall()
    return [Position.from_row(row) for row in rows]


def get_position(
    ticker: str, user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> Position | None:
    """One position, or None if the user holds no shares of it."""
    with use_connection(conn) as c:
        row = c.execute(
            "SELECT * FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, normalize_ticker(ticker)),
        ).fetchone()
    return Position.from_row(row) if row else None


def upsert_position(
    ticker: str,
    quantity: float,
    avg_cost: float,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> Position:
    """Write the absolute quantity and average cost for a ticker.

    Insert if new, overwrite if it exists. Computing the new quantity/avg_cost from a
    fill is the caller's job.
    """
    symbol = normalize_ticker(ticker)
    now = utc_now_iso()
    with use_connection(conn) as c:
        c.execute(
            """
            INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, ticker) DO UPDATE SET
                quantity = excluded.quantity,
                avg_cost = excluded.avg_cost,
                updated_at = excluded.updated_at
            """,
            (new_id(), user_id, symbol, quantity, avg_cost, now),
        )
        row = c.execute(
            "SELECT * FROM positions WHERE user_id = ? AND ticker = ?", (user_id, symbol)
        ).fetchone()
    return Position.from_row(row)


def delete_position(
    ticker: str, user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> bool:
    """Delete a position (e.g. fully sold). Returns True if a row was deleted."""
    with use_connection(conn) as c:
        cursor = c.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, normalize_ticker(ticker)),
        )
        return cursor.rowcount > 0
