"""Fixtures: isolated database, empty price cache, explicit LLM_MOCK state."""

import pytest

from app.state import get_price_cache, reset_prices
from db import DB_PATH_ENV_VAR, reset_initialization_cache

SEED_PRICES = {"AAPL": 190.0, "GOOGL": 175.0, "TSLA": 250.0, "NVDA": 500.0}


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the db package at a fresh file per test."""
    monkeypatch.setenv(DB_PATH_ENV_VAR, str(tmp_path / "finally.db"))
    reset_initialization_cache()
    yield
    reset_initialization_cache()


@pytest.fixture(autouse=True)
def clean_prices():
    """The price cache is a process-wide singleton — empty it around each test."""
    reset_prices()
    yield
    reset_prices()


@pytest.fixture(autouse=True)
def llm_env(monkeypatch):
    """Default to real-LLM code paths with a key present; the API call is stubbed."""
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


@pytest.fixture
def mock_mode(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")


@pytest.fixture
def prices():
    """Live prices for a handful of default tickers."""
    cache = get_price_cache()
    for ticker, price in SEED_PRICES.items():
        cache.update(ticker, price)
    return cache
