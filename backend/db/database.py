"""Lazy database initialization and connection scoping.

Everything in the repository layer goes through ``get_connection`` / ``transaction``
here, so the first database access of the process creates and seeds the file.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .connection import connect, get_db_path
from .schema import apply_schema, missing_tables
from .seed import seed_defaults

_init_lock = threading.Lock()
_initialized: set[Path] = set()


def init_db(path: Path | None = None) -> Path:
    """Create any missing tables and seed defaults if the database is empty.

    Idempotent: safe to call on an existing, populated database — it never drops
    tables and never re-seeds once a profile row exists.
    """
    db_path = path or get_db_path()
    conn = connect(db_path)
    try:
        if missing_tables(conn):
            apply_schema(conn)
        seed_defaults(conn)
        conn.commit()
    finally:
        conn.close()
    return db_path


def ensure_initialized(path: Path | None = None) -> Path:
    """Run ``init_db`` once per database path per process."""
    db_path = path or get_db_path()
    if db_path in _initialized:
        return db_path
    with _init_lock:
        if db_path not in _initialized:
            init_db(db_path)
            _initialized.add(db_path)
    return db_path


def reset_initialization_cache() -> None:
    """Forget which paths were initialized. For tests that swap database files."""
    with _init_lock:
        _initialized.clear()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Short-lived connection to the initialized database. Does not commit."""
    db_path = ensure_initialized()
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Short-lived connection that commits on success and rolls back on error."""
    with get_connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


@contextmanager
def use_connection(conn: sqlite3.Connection | None) -> Iterator[sqlite3.Connection]:
    """Reuse the caller's connection, or open a self-committing one if given None.

    This is what lets every repository function accept an optional ``conn`` and
    still be composable inside a single ``transaction()`` block.
    """
    if conn is not None:
        yield conn
    else:
        with transaction() as owned:
            yield owned
