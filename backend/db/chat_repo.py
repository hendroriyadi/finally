"""CRUD for the chat_messages table.

``actions`` is stored as a JSON string but crosses this boundary as a plain Python
object (list/dict/None) — callers never serialize it themselves.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .database import use_connection
from .models import DEFAULT_USER_ID, ChatMessage, new_id, utc_now_iso


def insert_chat_message(
    role: str,
    content: str,
    actions: Any | None = None,
    user_id: str = DEFAULT_USER_ID,
    *,
    created_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> ChatMessage:
    """Append a message. ``role`` must be "user" or "assistant"."""
    message = ChatMessage(
        id=new_id(),
        user_id=user_id,
        role=role.strip().lower(),
        content=content,
        actions=actions,
        created_at=created_at or utc_now_iso(),
    )
    with use_connection(conn) as c:
        c.execute(
            """
            INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.user_id,
                message.role,
                message.content,
                json.dumps(actions) if actions is not None else None,
                message.created_at,
            ),
        )
    return message


def list_chat_messages(
    user_id: str = DEFAULT_USER_ID,
    *,
    limit: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[ChatMessage]:
    """Conversation history oldest-first. ``limit`` keeps the most recent N."""
    if limit is None:
        sql = "SELECT * FROM chat_messages WHERE user_id = ? ORDER BY created_at ASC, rowid ASC"
        params: list[object] = [user_id]
    else:
        sql = (
            "SELECT * FROM chat_messages WHERE user_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?"
        )
        params = [user_id, limit]

    with use_connection(conn) as c:
        rows = c.execute(sql, params).fetchall()
    messages = [ChatMessage.from_row(row) for row in rows]
    return list(reversed(messages)) if limit is not None else messages


def clear_chat_messages(
    user_id: str = DEFAULT_USER_ID, *, conn: sqlite3.Connection | None = None
) -> int:
    """Delete the whole conversation. Returns the number of rows removed."""
    with use_connection(conn) as c:
        cursor = c.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))
        return cursor.rowcount
