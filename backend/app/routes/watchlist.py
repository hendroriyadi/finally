"""Watchlist REST router.

Ticker normalization runs on every write path before any SQL statement or
market-source call: `raw.strip().upper()`, then a shape check against
`TICKER_PATTERN`. This is the T-01-01/T-01-02 mitigation — malformed input
never reaches the database or the market data source.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.watchlist import (
    add_watchlist_ticker,
    count_watchlist,
    list_watchlist,
    remove_watchlist_ticker,
)

logger = logging.getLogger(__name__)

TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,10}$")
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

        if await count_watchlist() >= MAX_WATCHLIST_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Watchlist already at the maximum of {MAX_WATCHLIST_SIZE} tickers",
            )

        created = await add_watchlist_ticker(ticker)
        if created is None:
            raise HTTPException(status_code=409, detail=f"{ticker} is already on the watchlist")

        # Persist first, then track — a database failure never leaves the
        # stream tracking a ticker the database does not know about.
        await request.app.state.market_source.add_ticker(ticker)
        return WatchlistItem(**created)

    @router.delete("/{ticker}", status_code=204)
    async def remove_ticker(ticker: str, request: Request) -> None:
        normalized = normalize_ticker(ticker)

        removed = await remove_watchlist_ticker(normalized)
        if not removed:
            raise HTTPException(status_code=404, detail=f"{normalized} is not on the watchlist")

        await request.app.state.market_source.remove_ticker(normalized)

    return router
