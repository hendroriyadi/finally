"""Watchlist mutations that keep the database and the market data source in sync.

Adding a ticker to the database is not enough — the running MarketDataSource has
its own tracked set, and a ticker it does not track never produces a price. Always
go through these helpers rather than calling ``db.add_watchlist_ticker`` directly.
"""

from __future__ import annotations

import re

import db
from app.market import PriceCache
from app.portfolio import WatchlistItem
from app.state import get_market_source, get_price_cache

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def validate_ticker(ticker: str) -> str:
    """Normalize to a stripped, uppercase symbol. Raises ValueError if malformed."""
    symbol = db.normalize_ticker(ticker or "")
    if not TICKER_PATTERN.match(symbol):
        raise ValueError(
            f"Invalid ticker {ticker!r}: expected 1-10 letters, digits, dots or dashes "
            "starting with a letter."
        )
    return symbol


async def add_ticker(
    ticker: str,
    user_id: str = db.DEFAULT_USER_ID,
    *,
    price_cache: PriceCache | None = None,
) -> tuple[WatchlistItem, bool]:
    """Watch a ticker and start streaming it. Returns (item, newly_added)."""
    symbol = validate_ticker(ticker)
    newly_added = not db.is_watching(symbol, user_id)
    entry = db.add_watchlist_ticker(symbol, user_id)

    source = get_market_source()
    if source is not None:
        await source.add_ticker(symbol)

    cache = price_cache if price_cache is not None else get_price_cache()
    return WatchlistItem.from_entry(entry, cache), newly_added


async def remove_ticker(ticker: str, user_id: str = db.DEFAULT_USER_ID) -> bool:
    """Stop watching a ticker and stop streaming it. False if it was not watched."""
    symbol = validate_ticker(ticker)
    removed = db.remove_watchlist_ticker(symbol, user_id)

    source = get_market_source()
    if source is not None:
        await source.remove_ticker(symbol)

    return removed
