"""Watchlist REST router.

Ticker normalization runs on every write path before any SQL statement or
market-source call: `raw.strip().upper()`, then a shape check against
`TICKER_PATTERN`. This is the T-01-01/T-01-02 mitigation — malformed input
never reaches the database or the market data source.
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

logger = logging.getLogger(__name__)

# Requires a leading alphanumeric so bare punctuation ("-", ".", "--") can't
# pass as a "valid" ticker shape (IN-02); still permits the trailing
# `.`/`-` characters real tickers use (e.g. "BRK.B").
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
MAX_WATCHLIST_SIZE = 50


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

        # The size cap and the duplicate check are both enforced inside the
        # same atomic INSERT as add_watchlist_ticker's own statement (WR-01)
        # — a separate `count_watchlist()` read-then-insert here would be a
        # check-then-act race between concurrent POSTs.
        try:
            created = await add_watchlist_ticker(ticker, max_size=MAX_WATCHLIST_SIZE)
        except WatchlistCapReachedError:
            raise HTTPException(
                status_code=400,
                detail=f"Watchlist already at the maximum of {MAX_WATCHLIST_SIZE} tickers",
            ) from None
        if created is None:
            raise HTTPException(status_code=409, detail=f"{ticker} is already on the watchlist")

        # Persist first, then track — but if the market-source call fails,
        # compensate by removing the row we just inserted so the database
        # and the live stream never diverge (WR-02): without this, a
        # downstream failure here would leave `ticker` permanently in the
        # watchlist with no price feed until the process restarts.
        try:
            await request.app.state.market_source.add_ticker(ticker)
        except Exception:
            logger.exception(
                "market_source.add_ticker(%r) failed after watchlist insert; rolling back", ticker
            )
            await remove_watchlist_ticker(ticker)
            raise HTTPException(
                status_code=502, detail=f"Could not start streaming {ticker}; watchlist not updated"
            ) from None
        return WatchlistItem(**created)

    @router.delete("/{ticker}", status_code=204)
    async def remove_ticker(
        request: Request, ticker: str = Path(min_length=1, max_length=10)
    ) -> None:
        normalized = normalize_ticker(ticker)

        removed = await remove_watchlist_ticker(normalized)
        if not removed:
            raise HTTPException(status_code=404, detail=f"{normalized} is not on the watchlist")

        # Mirror image of the add-path compensation above (WR-02): if the
        # market-source removal fails after the DB delete already committed,
        # re-add the watchlist row (uncapped — the cap only gates net-new
        # additions, not restoring a row we just had) so the DB and the
        # live stream don't diverge.
        try:
            await request.app.state.market_source.remove_ticker(normalized)
        except Exception:
            logger.exception(
                "market_source.remove_ticker(%r) failed after watchlist delete; re-adding",
                normalized,
            )
            await add_watchlist_ticker(normalized)
            raise HTTPException(
                status_code=502,
                detail=f"Could not stop streaming {normalized}; watchlist not updated",
            ) from None

    return router
