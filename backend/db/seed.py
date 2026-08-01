"""Default data written into a brand-new database."""

from __future__ import annotations

import sqlite3

from .models import DEFAULT_USER_ID, new_id, utc_now_iso

DEFAULT_CASH_BALANCE = 10000.0

DEFAULT_TICKERS = (
    "AAPL",
    "GOOGL",
    "MSFT",
    "AMZN",
    "TSLA",
    "NVDA",
    "META",
    "JPM",
    "V",
    "NFLX",
)


def is_seeded(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> bool:
    """True once a profile row exists — the marker that seeding already happened.

    Deliberately does not look at the watchlist: a user who removes every ticker
    must not have the defaults reappear on the next start.
    """
    row = conn.execute("SELECT 1 FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    return row is not None


def seed_defaults(conn: sqlite3.Connection, user_id: str = DEFAULT_USER_ID) -> bool:
    """Insert the default profile and watchlist. No-op if already seeded.

    Returns True if rows were written.
    """
    if is_seeded(conn, user_id):
        return False

    now = utc_now_iso()
    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (user_id, DEFAULT_CASH_BALANCE, now),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        [(new_id(), user_id, ticker, now) for ticker in DEFAULT_TICKERS],
    )
    return True
