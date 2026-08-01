"""CRUD for the portfolio_snapshots table (P&L chart series)."""

from __future__ import annotations

import sqlite3

from .database import use_connection
from .models import DEFAULT_USER_ID, PortfolioSnapshot, new_id, utc_now_iso


def insert_snapshot(
    total_value: float,
    user_id: str = DEFAULT_USER_ID,
    *,
    recorded_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> PortfolioSnapshot:
    """Record total portfolio value at a point in time."""
    snapshot = PortfolioSnapshot(
        id=new_id(),
        user_id=user_id,
        total_value=total_value,
        recorded_at=recorded_at or utc_now_iso(),
    )
    with use_connection(conn) as c:
        c.execute(
            """
            INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (snapshot.id, snapshot.user_id, snapshot.total_value, snapshot.recorded_at),
        )
    return snapshot


def list_snapshots(
    user_id: str = DEFAULT_USER_ID,
    *,
    since: str | None = None,
    limit: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[PortfolioSnapshot]:
    """Snapshots in chronological order, ready to plot.

    ``since`` is an inclusive ISO timestamp lower bound. ``limit`` keeps the most
    recent N while still returning them oldest-first.
    """
    sql = "SELECT * FROM portfolio_snapshots WHERE user_id = ?"
    params: list[object] = [user_id]
    if since is not None:
        sql += " AND recorded_at >= ?"
        params.append(since)

    if limit is not None:
        sql += " ORDER BY recorded_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
    else:
        sql += " ORDER BY recorded_at ASC, rowid ASC"

    with use_connection(conn) as c:
        rows = c.execute(sql, params).fetchall()
    snapshots = [PortfolioSnapshot.from_row(row) for row in rows]
    return list(reversed(snapshots)) if limit is not None else snapshots


def latest_snapshot(
    user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> PortfolioSnapshot | None:
    """Most recent snapshot, or None if none recorded yet."""
    with use_connection(conn) as c:
        row = c.execute(
            """
            SELECT * FROM portfolio_snapshots WHERE user_id = ?
            ORDER BY recorded_at DESC, rowid DESC LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    return PortfolioSnapshot.from_row(row) if row else None
