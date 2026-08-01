"""Fixtures that isolate every db test in its own temporary SQLite file."""

import pytest

from db import DB_PATH_ENV_VAR, get_db_path, reset_initialization_cache


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the db package at a fresh file per test and clear the init cache."""
    db_file = tmp_path / "finally.db"
    monkeypatch.setenv(DB_PATH_ENV_VAR, str(db_file))
    reset_initialization_cache()
    yield db_file
    reset_initialization_cache()


@pytest.fixture
def db_path(temp_db):
    """The temporary database path (initialization is still lazy)."""
    return get_db_path()
