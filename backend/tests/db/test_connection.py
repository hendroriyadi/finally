"""Tests for the WAL + busy_timeout connection factory."""

from __future__ import annotations

from app.db.connection import connect


def test_wal_and_busy_timeout(temp_db):
    conn = connect()
    try:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        conn.close()

    assert journal_mode.lower() == "wal"
    assert busy_timeout == 5000
