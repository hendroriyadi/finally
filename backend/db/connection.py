"""Low-level SQLite connection handling.

The database file location resolves in this order:

1. ``FINALLY_DB_PATH`` environment variable (absolute path to the .db file)
2. ``<repo root>/db/finally.db`` — the Docker volume mount target from PLAN.md section 4

Docker images that copy ``backend/`` to a different prefix should set
``FINALLY_DB_PATH=/app/db/finally.db`` explicitly.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH_ENV_VAR = "FINALLY_DB_PATH"

# backend/db/connection.py -> backend/db -> backend -> <repo root>
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "db" / "finally.db"


def get_db_path() -> Path:
    """Resolve the SQLite file path for this process."""
    override = os.environ.get(DB_PATH_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return DEFAULT_DB_PATH


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open a raw connection with the pragmas this app needs.

    Callers are responsible for closing it; prefer ``database.get_connection()``.
    """
    db_path = path or get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL lets the snapshot writer and request handlers read/write concurrently.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
