"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def event_loop_policy():
    """Use the default event loop policy for all async tests."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point FINALLY_DB_PATH at a tmp_path-derived file so tests never touch
    the developer's real database."""
    db_path = tmp_path / "finally.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(db_path))
    return db_path


@pytest.fixture
def client(temp_db):
    """Yield a TestClient(create_app()) with the lifespan actually run,
    against the temp database."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
