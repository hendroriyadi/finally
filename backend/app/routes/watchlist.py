"""Watchlist REST router.

Ticker normalization runs on every write path before any SQL statement or
market-source call: `raw.strip().upper()`, then a shape check against
`TICKER_PATTERN`. This is the T-01-01/T-01-02 mitigation — malformed input
never reaches the database or the market data source.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.watchlist import list_watchlist

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

    return router
