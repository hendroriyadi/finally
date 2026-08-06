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
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db import init_db
from app.db.watchlist import list_watchlist
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.routes.chat import create_chat_router
from app.routes.portfolio import create_portfolio_router
from app.routes.watchlist import create_watchlist_router
from app.snapshot_task import SnapshotRecorder

logger = logging.getLogger(__name__)

# Resolves to two different places on purpose:
#   - `backend/static` in a checkout — normally ABSENT, so a bare
#     `uv run uvicorn app.main:app` serves the API only and does not crash.
#   - `/app/static` inside the image — PRESENT, because the Dockerfile's
#     frontend-builder stage copies `frontend/out` there.
# That second path and the Dockerfile's COPY destination are a matched pair.
# Change either one alone and the container still starts cleanly, still logs,
# and serves the frontend nowhere — a silent degradation, not a crash.
# Resolved from `__file__` rather than the CWD so it does not depend on the
# working directory uvicorn happens to be launched from.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app() -> FastAPI:
    """Assemble the FastAPI application object."""
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()

        source = create_market_data_source(cache)
        watchlist = await list_watchlist()
        # No `or list(SEED_PRICES.keys())` fallback here: init_db() seeds the
        # default watchlist synchronously above on first-ever boot, before
        # this line runs, so an empty result here can only mean the user
        # deliberately removed every ticker — starting the market source
        # (and therefore this phase's snapshot valuation) against the full
        # default list in that case would silently resurrect tickers the
        # user removed on every restart.
        tickers = [row["ticker"] for row in watchlist]
        await source.start(tickers)

        app.state.price_cache = cache
        app.state.market_source = source

        recorder = SnapshotRecorder(cache)
        await recorder.start()
        app.state.snapshot_recorder = recorder

        yield

        await recorder.stop()
        await source.stop()

    app = FastAPI(title="FinAlly", lifespan=lifespan)

    # Dev-only CORS: the frontend runs on :3000 via `next dev` while the
    # backend runs on :8000, since output: 'export' disables next.config
    # rewrites-based proxying. Exact-origin allowlist, never a wildcard
    # (T-01-04).
    #
    # Kept deliberately now that the container serves both surfaces from one
    # origin: the middleware is inert there (same-origin requests never carry
    # an Origin the browser checks against this list), while `npm run dev` on
    # a separate port still needs it. An exact-origin allowlist costs nothing
    # to leave in place, and deleting it would break the dev workflow every
    # future contributor uses. If this ever looks unused, widen nothing —
    # a wildcard here would be a real regression (T-05-05).
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
    app.include_router(create_chat_router())

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # MUST be the last thing registered on this app (T-05-03). Starlette
    # matches routes and mounts in declaration order, and a mount at "/"
    # matches everything — anything registered after it is unreachable, so
    # adding a route below this line would silently 404 in production while
    # still passing an import-time check.
    #
    # The directory guard is equally load-bearing: StaticFiles defaults to
    # check_dir=True and raises at CONSTRUCTION time on a missing directory.
    # Guarding means the constructor is never reached in a checkout without a
    # built frontend, so there is nothing to suppress and no try/except.
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
        logger.info("Serving static frontend from %s", STATIC_DIR)
    else:
        logger.info("No static directory at %s — running API-only", STATIC_DIR)

    return app


app = create_app()
