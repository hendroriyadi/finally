"""Database layer for FinAlly: lazy schema init, WAL-mode SQLite access.

Public API:
    run_db          - async seam that every read/write goes through
    connect         - open a fresh WAL-mode, busy_timeout-configured connection
    DEFAULT_USER_ID - the single hardcoded user id ("default")
    init_db         - idempotent lazy schema creation + seeding
"""

from .connection import DEFAULT_USER_ID, connect, run_db
from .init import init_db

__all__ = [
    "run_db",
    "connect",
    "DEFAULT_USER_ID",
    "init_db",
]
