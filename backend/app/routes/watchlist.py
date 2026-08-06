"""Watchlist REST router.

Ticker normalization runs on every write path before any SQL statement or
market-source call: `raw.strip().upper()`, then a shape check against
`TICKER_PATTERN`. This is the T-01-01/T-01-02 mitigation — malformed input
never reaches the database or the market data source.

The write path has two callers now: the HTTP handlers below and the chat
action executor in `app.routes.chat`. The persist-then-track sequence with
its compensating rollback (`apply_watchlist_add`/`apply_watchlist_remove`)
lives in exactly one place, because two copies of it are how the stored
list and the live stream drift apart (see `04-RESEARCH.md`'s Pitfall 2).
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field

from app.db.watchlist import (
    WatchlistCapReachedError,
    add_watchlist_ticker,
    list_watchlist,
    remove_watchlist_ticker,
)
from app.market.interface import MarketDataSource

logger = logging.getLogger(__name__)

# Requires a leading alphanumeric so bare punctuation ("-", ".", "--") can't
# pass as a "valid" ticker shape (IN-02); still permits the trailing
# `.`/`-` characters real tickers use (e.g. "BRK.B").
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
MAX_WATCHLIST_SIZE = 50


class WatchlistActionError(Exception):
    """Base for the write-path failures both callers must distinguish."""


class DuplicateTickerError(WatchlistActionError):
    """The ticker is already on the watchlist."""


class TickerNotOnWatchlistError(WatchlistActionError):
    """The ticker was not on the watchlist, so nothing was removed."""


class MarketSourceSyncError(WatchlistActionError):
    """The table mutation succeeded but the market source refused to start or
    stop tracking; the mutation has already been compensated."""


class AddTickerRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)


class WatchlistItem(BaseModel):
    ticker: str
    added_at: str


class WatchlistResponse(BaseModel):
    tickers: list[WatchlistItem]


def normalize_ticker(raw: str) -> str:
    """Strip, uppercase, and shape-validate a raw ticker string.

    Raises HTTPException(400) when the normalized value fails TICKER_PATTERN.
    Applied identically to POST body fields and the DELETE path parameter.
    """
    normalized = raw.strip().upper()
    if not TICKER_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {raw!r}")
    return normalized


async def apply_watchlist_add(
    ticker: str, market_source: MarketDataSource, *, max_size: int | None = MAX_WATCHLIST_SIZE
) -> dict:
    """Add `ticker` to the watchlist and start its live price feed.

    `ticker` must already be normalized — the caller owns that step, so this
    function has exactly one reason to fail per branch. Performs the whole
    add: the atomic capped insert, then telling the market source to start
    tracking, then undoing the insert if that second call fails.

    Raises `WatchlistCapReachedError` (from the data-access layer, untouched),
    `DuplicateTickerError`, or `MarketSourceSyncError` — never an
    `HTTPException`, because the two callers need opposite things from a
    failure: a status code for the HTTP handler, a readable sentence for the
    chat transcript.
    """
    # The size cap and the duplicate check are both enforced inside the
    # same atomic INSERT as add_watchlist_ticker's own statement (WR-01)
    # — a separate `count_watchlist()` read-then-insert here would be a
    # check-then-act race between concurrent callers.
    created = await add_watchlist_ticker(ticker, max_size=max_size)
    if created is None:
        raise DuplicateTickerError(f"{ticker} is already on the watchlist")

    # Persist first, then track — but if the market-source call fails,
    # compensate by removing the row we just inserted so the database
    # and the live stream never diverge (WR-02): without this, a
    # downstream failure here would leave `ticker` permanently in the
    # watchlist with no price feed until the process restarts.
    try:
        await market_source.add_ticker(ticker)
    except Exception:
        logger.exception(
            "market_source.add_ticker(%r) failed after watchlist insert; rolling back", ticker
        )
        await remove_watchlist_ticker(ticker)
        raise MarketSourceSyncError(f"Could not start streaming {ticker}") from None
    return created


async def apply_watchlist_remove(ticker: str, market_source: MarketDataSource) -> None:
    """Remove `ticker` from the watchlist and stop its live price feed.

    Mirror image of `apply_watchlist_add`. `ticker` must already be
    normalized. Raises `TickerNotOnWatchlistError` or `MarketSourceSyncError`
    — never an `HTTPException`.
    """
    removed = await remove_watchlist_ticker(ticker)
    if not removed:
        raise TickerNotOnWatchlistError(f"{ticker} is not on the watchlist")

    # Mirror image of the add-path compensation above (WR-02): if the
    # market-source removal fails after the DB delete already committed,
    # re-add the watchlist row (uncapped — the cap only gates net-new
    # additions, not restoring a row we just had) so the DB and the
    # live stream don't diverge.
    try:
        await market_source.remove_ticker(ticker)
    except Exception:
        logger.exception(
            "market_source.remove_ticker(%r) failed after watchlist delete; re-adding", ticker
        )
        await add_watchlist_ticker(ticker)
        raise MarketSourceSyncError(f"Could not stop streaming {ticker}") from None


def create_watchlist_router() -> APIRouter:
    """Create the watchlist router, prefix='/api/watchlist'.

    Handlers reach the running market data source through
    `request.app.state.market_source` — that is how a router built at import
    time gets access to an object created during FastAPI's lifespan startup.
    """
    router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

    @router.get("", response_model=WatchlistResponse)
    async def get_watchlist() -> WatchlistResponse:
        tickers = await list_watchlist()
        return WatchlistResponse(tickers=[WatchlistItem(**row) for row in tickers])

    @router.post("", response_model=WatchlistItem, status_code=201)
    async def add_ticker(body: AddTickerRequest, request: Request) -> WatchlistItem:
        ticker = normalize_ticker(body.ticker)

        try:
            created = await apply_watchlist_add(ticker, request.app.state.market_source)
        except WatchlistCapReachedError:
            raise HTTPException(
                status_code=400,
                detail=f"Watchlist already at the maximum of {MAX_WATCHLIST_SIZE} tickers",
            ) from None
        except DuplicateTickerError:
            raise HTTPException(
                status_code=409, detail=f"{ticker} is already on the watchlist"
            ) from None
        except MarketSourceSyncError:
            raise HTTPException(
                status_code=502, detail=f"Could not start streaming {ticker}; watchlist not updated"
            ) from None
        return WatchlistItem(**created)

    @router.delete("/{ticker}", status_code=204)
    async def remove_ticker(
        request: Request, ticker: str = Path(min_length=1, max_length=10)
    ) -> None:
        normalized = normalize_ticker(ticker)

        try:
            await apply_watchlist_remove(normalized, request.app.state.market_source)
        except TickerNotOnWatchlistError:
            raise HTTPException(
                status_code=404, detail=f"{normalized} is not on the watchlist"
            ) from None
        except MarketSourceSyncError:
            raise HTTPException(
                status_code=502,
                detail=f"Could not stop streaming {normalized}; watchlist not updated",
            ) from None

    return router
