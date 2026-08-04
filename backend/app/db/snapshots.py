"""Portfolio history — the sole reader and writer of `portfolio_snapshots`.

This module reads and writes exactly one table, `portfolio_snapshots`, and
deliberately performs no valuation of its own: it calls Phase 2's
`get_portfolio_state()` and `value_portfolio()` (from `app.db.portfolio`) so
the 30-second timer (`app.snapshot_task`) and the post-trade route trigger
can never drift apart in how they value the portfolio (D-01/D-03).
`execute_trade()` remains the sole mutator of cash, positions, and trade
history — this module is not permitted to write any of those three tables.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone

from .connection import DEFAULT_USER_ID, run_db
from .portfolio import get_portfolio_state, value_portfolio

logger = logging.getLogger(__name__)

# At a 30-second recording cadence the table grows about 2,880 rows a day.
# This cap is what keeps GET /api/portfolio/history's response bounded
# without introducing a client-controllable limit/since parameter (T-03-01).
MAX_HISTORY_POINTS = 500


async def record_portfolio_snapshot(*, price_cache, user_id: str = DEFAULT_USER_ID) -> dict:
    """Value the current portfolio and insert one `portfolio_snapshots` row.

    Reads the current state via `get_portfolio_state()`, values it via
    `value_portfolio()` against `price_cache` (the same pair the trade route
    and the 30-second timer both call), and inserts a single row carrying
    `total_value` and `recorded_at`. Returns that pair so a caller that wants
    to echo the recording does not need a second read.
    """
    state = await get_portfolio_state(user_id=user_id)
    valued = value_portfolio(state, price_cache)

    snapshot_id = str(uuid.uuid4())
    recorded_at = datetime.now(timezone.utc).isoformat()
    total_value = float(valued["total_value"])

    def _txn(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
            "VALUES (?, ?, ?, ?)",
            (snapshot_id, user_id, total_value, recorded_at),
        )

    await run_db(_txn)
    return {"total_value": total_value, "recorded_at": recorded_at}


async def list_snapshots(
    *, user_id: str = DEFAULT_USER_ID, limit: int = MAX_HISTORY_POINTS
) -> list[dict]:
    """Return up to `limit` snapshots for `user_id`, oldest first.

    Selects the newest `limit` rows (descending `recorded_at`, `id`
    descending as a stable tiebreaker — riding `idx_snapshots_user_time`),
    then reverses them in Python so the caller receives a chronological
    series while the cap still keeps the *most recent* window rather than
    the oldest one.
    """

    def _query(conn: sqlite3.Connection) -> list[dict]:
        rows = conn.execute(
            "SELECT total_value, recorded_at FROM portfolio_snapshots "
            "WHERE user_id = ? ORDER BY recorded_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [
            {"total_value": float(row["total_value"]), "recorded_at": row["recorded_at"]}
            for row in rows
        ]

    rows = await run_db(_query)
    rows.reverse()
    return rows
