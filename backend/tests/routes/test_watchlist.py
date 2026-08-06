"""Tests for the watchlist REST router."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.db.init import init_db
from app.db.watchlist import (
    WatchlistCapReachedError,
    add_watchlist_ticker,
    count_watchlist,
    list_watchlist,
)
from app.market.seed_prices import SEED_PRICES
from app.routes.watchlist import (
    MAX_WATCHLIST_SIZE,
    DuplicateTickerError,
    MarketSourceSyncError,
    TickerNotOnWatchlistError,
    apply_watchlist_add,
    apply_watchlist_remove,
)


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


class _FailingMarketSource:
    """Wraps a real MarketDataSource, raising instead of delegating for
    whichever of add_ticker/remove_ticker is configured to fail — used to
    exercise the WR-02 compensation paths."""

    def __init__(self, wrapped, *, fail_add: bool = False, fail_remove: bool = False):
        self._wrapped = wrapped
        self._fail_add = fail_add
        self._fail_remove = fail_remove

    async def add_ticker(self, ticker: str) -> None:
        if self._fail_add:
            raise RuntimeError("simulated market-source failure")
        await self._wrapped.add_ticker(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        if self._fail_remove:
            raise RuntimeError("simulated market-source failure")
        await self._wrapped.remove_ticker(ticker)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


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


def test_add_ticker_rolls_back_watchlist_row_when_market_source_fails(client, temp_db):
    """WR-02: a market-source failure after the DB insert must not leave a
    ticker permanently in the watchlist with no live price feed."""
    client.app.state.market_source = _FailingMarketSource(
        client.app.state.market_source, fail_add=True
    )

    response = client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert response.status_code == 502

    tickers = [item["ticker"] for item in client.get("/api/watchlist").json()["tickers"]]
    assert "PYPL" not in tickers


def test_remove_ticker_restores_watchlist_row_when_market_source_fails(client, temp_db):
    """WR-02: a market-source failure after the DB delete must not leave the
    watchlist claiming a ticker is gone while it is still streaming."""
    client.app.state.market_source = _FailingMarketSource(
        client.app.state.market_source, fail_remove=True
    )

    response = client.delete("/api/watchlist/AAPL")
    assert response.status_code == 502

    tickers = [item["ticker"] for item in client.get("/api/watchlist").json()["tickers"]]
    assert "AAPL" in tickers


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
    # Invalid shape (contains a space) but within the path length bound, so
    # this exercises TICKER_PATTERN rejection in normalize_ticker rather than
    # the Path(max_length=10) validator below.
    response = client.delete("/api/watchlist/DROP TBL")
    assert response.status_code == 400


def test_remove_ticker_exceeding_max_length_returns_422_before_any_query(client):
    # IN-03: the DELETE path parameter now declares the same length bound
    # (min_length=1, max_length=10) as AddTickerRequest.ticker's Field, for
    # symmetry between the two write paths. FastAPI/Pydantic enforces this
    # at the routing layer before normalize_ticker ever runs, so an
    # over-length path segment is a 422 (request shape rejected), distinct
    # from TICKER_PATTERN's 400 (value shape rejected after normalization).
    spy = _install_spy(client)

    response = client.delete("/api/watchlist/DROP-TABLE-WATCHLIST-TOO-LONG")
    assert response.status_code == 422
    assert spy.removed == []


# --- Plan 04-03 Task 1: helper-level tests for the extracted add/remove -----
#
# These exercise apply_watchlist_add/apply_watchlist_remove directly, below
# the HTTP layer, proving the persist-then-track-then-compensate sequence
# behaves correctly for the chat caller too — which never goes through a
# route handler and so would not be covered by any test above.


class _RecordingSource:
    """Standalone market-source stand-in (no real source to wrap): records
    what it was told to track, and can be configured to raise on either
    call to exercise the compensation branches."""

    def __init__(self, *, fail_add: bool = False, fail_remove: bool = False) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []
        self._fail_add = fail_add
        self._fail_remove = fail_remove

    async def add_ticker(self, ticker: str) -> None:
        if self._fail_add:
            raise RuntimeError("simulated add_ticker failure")
        self.added.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        if self._fail_remove:
            raise RuntimeError("simulated remove_ticker failure")
        self.removed.append(ticker)


async def _tickers() -> list[str]:
    return [row["ticker"] for row in await list_watchlist()]


@pytest.mark.asyncio
async def test_apply_add_inserts_row_and_starts_tracking(temp_db):
    await init_db()
    source = _RecordingSource()

    created = await apply_watchlist_add("PYPL", source)

    assert created["ticker"] == "PYPL"
    assert "PYPL" in await _tickers()
    assert source.added == ["PYPL"]


@pytest.mark.asyncio
async def test_apply_add_duplicate_raises_and_never_calls_source(temp_db):
    await init_db()
    source = _RecordingSource()

    with pytest.raises(DuplicateTickerError) as exc_info:
        # AAPL is one of the seeded default tickers.
        await apply_watchlist_add("AAPL", source)

    # The extraction's whole point: the chat caller must never have to
    # unwrap a web-framework error type to build a chat message.
    assert not isinstance(exc_info.value, HTTPException)
    assert source.added == []


@pytest.mark.asyncio
async def test_apply_add_at_cap_raises_cap_error_and_never_calls_source(temp_db):
    await init_db()
    source = _RecordingSource()

    with pytest.raises(WatchlistCapReachedError) as exc_info:
        await apply_watchlist_add("PYPL", source, max_size=1)

    assert not isinstance(exc_info.value, HTTPException)
    assert source.added == []
    assert "PYPL" not in await _tickers()


@pytest.mark.asyncio
async def test_apply_add_compensates_when_starting_the_feed_fails(temp_db):
    await init_db()
    source = _RecordingSource(fail_add=True)

    with pytest.raises(MarketSourceSyncError) as exc_info:
        await apply_watchlist_add("PYPL", source)

    assert not isinstance(exc_info.value, HTTPException)
    # Asserting on the stored list, not just the exception: without the
    # compensating delete this passes anyway, which is the bug being guarded.
    assert "PYPL" not in await _tickers()


@pytest.mark.asyncio
async def test_apply_remove_deletes_row_and_stops_tracking(temp_db):
    await init_db()
    source = _RecordingSource()

    await apply_watchlist_remove("AAPL", source)

    assert "AAPL" not in await _tickers()
    assert source.removed == ["AAPL"]


@pytest.mark.asyncio
async def test_apply_remove_unknown_raises_and_never_calls_source(temp_db):
    await init_db()
    source = _RecordingSource()

    with pytest.raises(TickerNotOnWatchlistError) as exc_info:
        await apply_watchlist_remove("ZZZZ", source)

    assert not isinstance(exc_info.value, HTTPException)
    assert source.removed == []


@pytest.mark.asyncio
async def test_apply_remove_compensates_when_stopping_the_feed_fails(temp_db):
    await init_db()
    source = _RecordingSource(fail_remove=True)

    with pytest.raises(MarketSourceSyncError) as exc_info:
        await apply_watchlist_remove("AAPL", source)

    assert not isinstance(exc_info.value, HTTPException)
    # The row must be back: a failed stop leaves the ticker listed and live.
    assert "AAPL" in await _tickers()
