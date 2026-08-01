"""Pytest configuration and shared fixtures."""

import pytest

from app import state
from db import DB_PATH_ENV_VAR, reset_initialization_cache


@pytest.fixture(scope="session", autouse=True)
def _litellm_imported_before_any_monkeypatching():
    """Import litellm once, up front.

    litellm calls load_dotenv() at import time, so it repopulates the repo-root .env
    into os.environ. app/llm/client.py imports it lazily inside complete(), which means
    that would otherwise happen *during* a test and silently undo a fixture's
    monkeypatch.delenv("LLM_MOCK") — a test asking for the real code path would get
    mock replies instead. Importing here makes the side effect happen before any
    fixture runs; the cached import can't re-trigger it later.
    """
    import litellm  # noqa: F401


@pytest.fixture
def event_loop_policy():
    """Use the default event loop policy for all async tests."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the db package at a fresh file per test so nothing touches real data."""
    db_file = tmp_path / "finally.db"
    monkeypatch.setenv(DB_PATH_ENV_VAR, str(db_file))
    reset_initialization_cache()
    yield db_file
    reset_initialization_cache()


@pytest.fixture(autouse=True)
def clean_price_cache():
    """Empty the shared price cache around every test."""
    state.reset_prices()
    yield
    state.reset_prices()


@pytest.fixture
def prices():
    """Seed the shared price cache with a couple of known prices."""
    cache = state.get_price_cache()
    cache.update("AAPL", 100.0)
    cache.update("GOOGL", 200.0)
    return cache
