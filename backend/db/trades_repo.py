"""CRUD for the trades table (append-only fill log)."""

from __future__ import annotations

import sqlite3

from .database import use_connection
from .models import DEFAULT_USER_ID, Trade, new_id, utc_now_iso
from .watchlist_repo import normalize_ticker


def insert_trade(
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    user_id: str = DEFAULT_USER_ID,
    *,
    executed_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> Trade:
    """Append a fill to the trade log. ``side`` must be "buy" or "sell"."""
    trade = Trade(
        id=new_id(),
        user_id=user_id,
        ticker=normalize_ticker(ticker),
        side=side.strip().lower(),
        quantity=quantity,
        price=price,
        executed_at=executed_at or utc_now_iso(),
    )
    with use_connection(conn) as c:
        c.execute(
            """
            INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.id,
                trade.user_id,
                trade.ticker,
                trade.side,
                trade.quantity,
                trade.price,
                trade.executed_at,
            ),
        )
    return trade


def list_trades(
    user_id: str = DEFAULT_USER_ID,
    *,
    ticker: str | None = None,
    limit: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[Trade]:
    """Trade history, most recent first. Optionally filtered by ticker."""
    sql = "SELECT * FROM trades WHERE user_id = ?"
    params: list[object] = [user_id]
    if ticker is not None:
        sql += " AND ticker = ?"
        params.append(normalize_ticker(ticker))
    sql += " ORDER BY executed_at DESC, rowid DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    with use_connection(conn) as c:
        rows = c.execute(sql, params).fetchall()
    return [Trade.from_row(row) for row in rows]


def count_trades(
    user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> int:
    """Total number of trades recorded for the user."""
    with use_connection(conn) as c:
        row = c.execute("SELECT COUNT(*) AS n FROM trades WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["n"])
