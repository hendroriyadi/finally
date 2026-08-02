"""Tests for the watchlist REST router."""

from __future__ import annotations

from app.db.watchlist import add_watchlist_ticker, count_watchlist
from app.market.seed_prices import SEED_PRICES
from app.routes.watchlist import MAX_WATCHLIST_SIZE


class _SpyMarketSource:
    """Wraps a real MarketDataSource, recording add_ticker/remove_ticker calls."""

    def __init__(self, wrapped):
        self._wrapped = wrapped
        self.added: list[str] = []
        self.removed: list[str] = []

    async def add_ticker(self, ticker: str) -> None:
        self.added.append(ticker)
        await self._wrapped.add_ticker(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.removed.append(ticker)
        await self._wrapped.remove_ticker(ticker)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


def _install_spy(client) -> _SpyMarketSource:
    spy = _SpyMarketSource(client.app.state.market_source)
    client.app.state.market_source = spy
    return spy


def test_get_watchlist_returns_seeded_tickers(client):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    body = response.json()
    tickers = [item["ticker"] for item in body["tickers"]]
    assert tickers == list(SEED_PRICES.keys())


def test_add_ticker_persists_and_calls_source(client):
    spy = _install_spy(client)

    response = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert response.status_code == 201
    assert response.json()["ticker"] == "PYPL"

    tickers = [item["ticker"] for item in client.get("/api/watchlist").json()["tickers"]]
    assert "PYPL" in tickers
    assert spy.added == ["PYPL"]


async def test_add_duplicate_ticker_returns_409_and_does_not_duplicate(client, temp_db):
    before = await count_watchlist()

    response = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert response.status_code == 409

    after = await count_watchlist()
    assert after == before


def test_add_malformed_ticker_returns_400_and_never_calls_source(client):
    spy = _install_spy(client)

    response = client.post("/api/watchlist", json={"ticker": "DROP TABLE"})
    assert response.status_code == 400

    tickers = [item["ticker"] for item in client.get("/api/watchlist").json()["tickers"]]
    assert "DROP TABLE" not in tickers
    assert spy.added == []


async def test_add_ticker_at_cap_returns_400_and_writes_nothing(client, temp_db):
    # Fill the watchlist up to MAX_WATCHLIST_SIZE directly through the data
    # layer (bypassing HTTP) so the test doesn't need MAX_WATCHLIST_SIZE
    # round trips.
    existing = await count_watchlist()
    for i in range(existing, MAX_WATCHLIST_SIZE):
        await add_watchlist_ticker(f"FILL{i}")

    before = await count_watchlist()
    assert before == MAX_WATCHLIST_SIZE

    response = client.post("/api/watchlist", json={"ticker": "OVERCAP"})
    assert response.status_code == 400

    after = await count_watchlist()
    assert after == before


def test_remove_ticker_persists_and_calls_source(client):
    spy = _install_spy(client)

    response = client.delete("/api/watchlist/AAPL")
    assert response.status_code == 204

    tickers = [item["ticker"] for item in client.get("/api/watchlist").json()["tickers"]]
    assert "AAPL" not in tickers
    assert spy.removed == ["AAPL"]


def test_remove_unknown_ticker_returns_404(client):
    response = client.delete("/api/watchlist/ZZZZ")
    assert response.status_code == 404


def test_remove_malformed_ticker_returns_400_before_any_query(client):
    response = client.delete("/api/watchlist/DROP-TABLE-WATCHLIST-TOO-LONG")
    assert response.status_code == 400
