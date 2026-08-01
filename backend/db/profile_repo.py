"""CRUD for the users_profile table (cash balance)."""

from __future__ import annotations

import sqlite3

from .database import use_connection
from .models import DEFAULT_USER_ID, UserProfile, utc_now_iso


def get_profile(
    user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> UserProfile | None:
    """Fetch the profile row, or None if it does not exist."""
    with use_connection(conn) as c:
        row = c.execute("SELECT * FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    return UserProfile.from_row(row) if row else None


def create_profile(
    user_id: str = DEFAULT_USER_ID,
    cash_balance: float = 10000.0,
    *,
    conn: sqlite3.Connection | None = None,
) -> UserProfile:
    """Insert a profile row. Returns the existing row if one is already there."""
    with use_connection(conn) as c:
        c.execute(
            "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (user_id, cash_balance, utc_now_iso()),
        )
        row = c.execute("SELECT * FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    return UserProfile.from_row(row)


def set_cash_balance(
    cash_balance: float,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> UserProfile | None:
    """Overwrite the cash balance. Returns the updated profile, or None if absent."""
    with use_connection(conn) as c:
        c.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
            (cash_balance, user_id),
        )
        row = c.execute("SELECT * FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    return UserProfile.from_row(row) if row else None


def adjust_cash_balance(
    delta: float,
    user_id: str = DEFAULT_USER_ID,
    *,
    conn: sqlite3.Connection | None = None,
) -> UserProfile | None:
    """Add ``delta`` to the cash balance in a single statement (no read-modify-write).

    Does not validate the result — an overdraft is the caller's concern.
    """
    with use_connection(conn) as c:
        c.execute(
            "UPDATE users_profile SET cash_balance = cash_balance + ? WHERE id = ?",
            (delta, user_id),
        )
        row = c.execute("SELECT * FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    return UserProfile.from_row(row) if row else None
