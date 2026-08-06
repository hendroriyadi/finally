"""Chat conversation storage — the sole reader and writer of `chat_messages`.

This module reads and writes exactly one table, `chat_messages`, and nothing
else — the same "one module, one table, no drift" boundary the snapshot
writer module declares for its own table. It performs no trade, position,
cash, or watchlist mutation of its own; the money-path and watchlist writers
remain the sole mutators of their own tables.

The `role` column is constrained by the schema's own CHECK to `'user'` or
`'assistant'`. Every caller of `append_chat_message()` passes a written-out
string literal for `role` — never a value taken from parsed model output.
This is the one column in this application where "the model decides the
value" would be a genuine integrity problem: a model reply that could talk
its way into writing a `role='user'` row would be indistinguishable from
something the person actually typed the next time the transcript is
replayed into a prompt. The protection here is a convention, not a runtime
guard, and it has to be written down so a later refactor that tries to make
the call "more generic" does not quietly reopen this gap.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone

from .connection import DEFAULT_USER_ID, run_db

logger = logging.getLogger(__name__)

# A conversational turn is one message from the person and one reply from
# the assistant, so twenty rows is roughly ten turns of context. This one
# constant bounds both the prompt window `app/routes/chat.py` sends to the
# model and the response `GET /api/chat/history` returns — there is
# deliberately no second, larger, unbounded read path into this table.
MAX_CONTEXT_MESSAGES = 20


async def append_chat_message(
    *,
    role: str,
    content: str,
    actions: list[dict] | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> dict:
    """Insert one `chat_messages` row and return it as a dict.

    `actions=None` (the default) stores SQL `NULL`: the column does not
    apply to this kind of row (every user row, and any row for which the
    caller has nothing to report). `actions=[]` stores a JSON empty array: a
    real statement that this reply executed nothing, distinct from "actions
    do not apply here". Collapsing the two to `NULL` would erase information
    the transcript needs when it is re-rendered after a reload.

    Returns the row as a dict so a caller that wants to echo what it just
    stored (e.g. the POST handler building its response) does not need a
    second read.
    """
    row_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    actions_json = json.dumps(actions) if actions is not None else None

    def _txn(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (row_id, user_id, role, content, actions_json, created_at),
        )

    await run_db(_txn)
    return {
        "id": row_id,
        "role": role,
        "content": content,
        "actions": actions,
        "created_at": created_at,
    }


async def list_recent_chat_messages(
    *, limit: int = MAX_CONTEXT_MESSAGES, user_id: str = DEFAULT_USER_ID
) -> list[dict]:
    """Return up to `limit` chat messages for `user_id`, oldest first.

    Selects the newest `limit` rows (descending `created_at`, `id`
    descending as a stable tiebreaker — riding `idx_chat_user_time`), then
    reverses them in Python so the caller receives a chronological
    conversation while the cap still keeps the *most recent* window rather
    than the oldest one. Mirrors `db/snapshots.py`'s `list_snapshots()`
    idiom exactly.
    """

    def _query(conn: sqlite3.Connection) -> list[dict]:
        rows = conn.execute(
            "SELECT role, content, actions, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "actions": json.loads(row["actions"]) if row["actions"] is not None else None,
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    rows = await run_db(_query)
    rows.reverse()
    return rows
