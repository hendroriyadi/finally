"""FastAPI application factory for FinAlly.

`create_app()` constructs exactly one `PriceCache`, wires a lifespan that
lazily initializes the database and starts the market data source seeded
from the persisted watchlist, and mounts the frozen SSE stream router
alongside the watchlist router. No module-level `PriceCache` singleton is
created; the cache is an explicit value closed over by the lifespan and the
router factories.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.db.watchlist import list_watchlist
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.market.seed_prices import SEED_PRICES
from app.routes.portfolio import create_portfolio_router
from app.routes.watchlist import create_watchlist_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Assemble the FastAPI application object."""
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()

        source = create_market_data_source(cache)
        watchlist = await list_watchlist()
        tickers = [row["ticker"] for row in watchlist] or list(SEED_PRICES.keys())
        await source.start(tickers)

        app.state.price_cache = cache
        app.state.market_source = source

        yield

        await source.stop()

    app = FastAPI(title="FinAlly", lifespan=lifespan)

    # Dev-only CORS: the frontend runs on :3000 via `next dev` while the
    # backend runs on :8000, since output: 'export' disables next.config
    # rewrites-based proxying. Exact-origin allowlist, never a wildcard
    # (T-01-04). Phase 5's single-origin Docker container removes this.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )

    app.include_router(create_stream_router(cache))
    app.include_router(create_watchlist_router())
    app.include_router(create_portfolio_router())

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
