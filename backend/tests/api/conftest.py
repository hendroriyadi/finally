"""Fixtures for the HTTP route tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.market import MarketDataSource


class FakeMarketDataSource(MarketDataSource):
    """Records add/remove calls so tests can assert the watchlist stays in sync."""

    def __init__(self) -> None:
        self.tickers: list[str] = []
        self.added: list[str] = []
        self.removed: list[str] = []

    async def start(self, tickers: list[str]) -> None:
        self.tickers = list(tickers)

    async def stop(self) -> None:
        self.tickers = []

    async def add_ticker(self, ticker: str) -> None:
        self.added.append(ticker)
        if ticker not in self.tickers:
            self.tickers.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.removed.append(ticker)
        if ticker in self.tickers:
            self.tickers.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self.tickers)


@pytest.fixture
def client():
    """A test client that does not run the lifespan, so no simulator is started."""
    return TestClient(create_app())


@pytest.fixture
def market_source():
    """Register a fake market data source for the duration of the test."""
    from app import state

    source = FakeMarketDataSource()
    state.set_market_source(source)
    yield source
    state.set_market_source(None)
