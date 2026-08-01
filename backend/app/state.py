"""Process-wide market data runtime.

The ``PriceCache`` is a module-level singleton so that every consumer — routes,
the SSE stream, the LLM chat flow, the snapshot loop — reads the same prices
without threading a handle through every call site. The ``MarketDataSource`` is
registered by the app lifespan and is absent in tests and scripts.
"""

from __future__ import annotations

from app.market import MarketDataSource, PriceCache

price_cache = PriceCache()

_market_source: MarketDataSource | None = None


def set_market_source(source: MarketDataSource | None) -> None:
    """Register (or clear) the running market data source."""
    global _market_source
    _market_source = source


def get_market_source() -> MarketDataSource | None:
    """The running market data source, or None when the app is not started."""
    return _market_source


def get_price_cache() -> PriceCache:
    """The shared price cache."""
    return price_cache


def reset_prices() -> None:
    """Drop every cached price. Tests only."""
    for ticker in list(price_cache.get_all()):
        price_cache.remove(ticker)
