"""CHAT-01 durability proof suite for `app.db.chat`.

Uses the `temp_db` fixture (see conftest.py) so nothing here touches the
developer's real database, mirroring `tests/db/test_snapshots.py`'s fixture
usage, fresh-`connect()` durability idiom, and assertion style.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.chat import MAX_CONTEXT_MESSAGES, append_chat_message, list_recent_chat_messages
from app.db.connection import DEFAULT_USER_ID, connect
from app.db.init import init_db

# --- append_chat_message() ---------------------------------------------------


@pytest.mark.asyncio
async def test_writer_inserts_one_row_readable_back_with_role_content_and_timestamp(temp_db):
    await init_db()

    row = await append_chat_message(role="user", content="buy 10 AAPL")

    assert row["role"] == "user"
    assert row["content"] == "buy 10 AAPL"
    assert row["created_at"]

    conn = connect()
    try:
        db_row = conn.execute(
            "SELECT role, content, created_at FROM chat_messages WHERE user_id = ?",
            (DEFAULT_USER_ID,),
        ).fetchone()
    finally:
        conn.close()

    assert db_row["role"] == "user"
    assert db_row["content"] == "buy 10 AAPL"
    assert db_row["created_at"] == row["created_at"]


@pytest.mark.asyncio
async def test_assistant_row_with_actions_reads_back_with_nested_numeric_fields_intact(temp_db):
    await init_db()
    actions = [
        {"kind": "trade", "status": "success", "ticker": "AAPL", "side": "buy", "quantity": 10.0, "price": 190.32}
    ]

    row = await append_chat_message(role="assistant", content="Done.", actions=actions)

    assert row["actions"] == actions

    rows = await list_recent_chat_messages()
    assert rows[-1]["actions"] == actions
    assert rows[-1]["actions"][0]["quantity"] == 10.0
    assert rows[-1]["actions"][0]["price"] == 190.32


@pytest.mark.asyncio
async def test_assistant_row_with_empty_action_list_reads_back_as_empty_list(temp_db):
    await init_db()

    await append_chat_message(role="assistant", content="Nothing to do.", actions=[])

    rows = await list_recent_chat_messages()
    assert rows[-1]["actions"] == []


@pytest.mark.asyncio
async def test_user_row_with_no_actions_reads_back_as_none(temp_db):
    await init_db()

    await append_chat_message(role="user", content="how am I doing?")

    rows = await list_recent_chat_messages()
    assert rows[-1]["actions"] is None


# --- list_recent_chat_messages() --------------------------------------------


@pytest.mark.asyncio
async def test_writing_more_than_the_cap_and_reading_returns_exactly_the_cap_of_newest(temp_db):
    await init_db()
    total = MAX_CONTEXT_MESSAGES + 10
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    conn = connect()
    try:
        for i in range(total):
            created_at = (base + timedelta(seconds=i)).isoformat()
            conn.execute(
                "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), DEFAULT_USER_ID, "user", f"message {i}", None, created_at),
            )
        conn.commit()
    finally:
        conn.close()

    rows = await list_recent_chat_messages()

    assert len(rows) == MAX_CONTEXT_MESSAGES
    # The kept window is the newest MAX_CONTEXT_MESSAGES rows, still returned
    # oldest-first — mirrors test_snapshots.py's cap-window assertion.
    assert rows[0]["content"] == f"message {total - MAX_CONTEXT_MESSAGES}"
    assert rows[-1]["content"] == f"message {total - 1}"


@pytest.mark.asyncio
async def test_messages_come_back_oldest_first_regardless_of_write_count(temp_db):
    await init_db()

    await append_chat_message(role="user", content="first")
    await append_chat_message(role="assistant", content="second", actions=[])
    await append_chat_message(role="user", content="third")

    rows = await list_recent_chat_messages()

    assert [r["content"] for r in rows] == ["first", "second", "third"]
    created_ats = [r["created_at"] for r in rows]
    assert created_ats == sorted(created_ats)


@pytest.mark.asyncio
async def test_fresh_database_returns_an_empty_list(temp_db):
    await init_db()

    rows = await list_recent_chat_messages()

    assert rows == []


# --- Restart durability (CHAT-01) -------------------------------------------


@pytest.mark.asyncio
async def test_messages_survive_a_fresh_independent_connection(temp_db):
    """Stand-in for a restarted process: nothing about the writing coroutines
    is still alive to serve this read, so a passing assertion can only mean
    the rows are on disk. Reads through a brand-new connect() opened in the
    test body itself — never through run_db, and never through
    list_recent_chat_messages (the helper that wrote had no part in this
    read)."""
    await init_db()

    await append_chat_message(role="user", content="buy 10 AAPL")
    await append_chat_message(
        role="assistant",
        content="Done.",
        actions=[{"kind": "trade", "status": "success", "ticker": "AAPL"}],
    )

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT role, content, actions FROM chat_messages WHERE user_id = ? ORDER BY created_at",
            (DEFAULT_USER_ID,),
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    assert rows[0]["role"] == "user"
    assert rows[0]["content"] == "buy 10 AAPL"
    assert rows[1]["role"] == "assistant"
    assert rows[1]["actions"] is not None


# --- Module boundary ----------------------------------------------------------


def test_module_touches_only_chat_messages_table():
    import inspect
    import re

    import app.db.chat as chat_module

    source = inspect.getsource(chat_module)
    pattern = re.compile(r"\b(users_profile|positions|trades|portfolio_snapshots)\b")
    assert not pattern.search(source), "app/db/chat.py must reference only chat_messages"
