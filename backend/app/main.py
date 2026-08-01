"""FastAPI application: REST API, SSE price stream, and the static frontend.

Run with ``uvicorn app.main:app`` from the ``backend/`` directory.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import db
from app import state
from app.llm import chat_router
from app.market import create_market_data_source, create_stream_router
from app.portfolio import record_snapshot
from app.routes import health_router, portfolio_router, watchlist_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
STATIC_DIR_ENV_VAR = "FINALLY_STATIC_DIR"
SNAPSHOT_INTERVAL_SECONDS = 30.0

# Real environment variables win — Docker passes them with --env-file, and this
# only fills the gaps for local `uvicorn` and pytest runs.
load_dotenv(REPO_ROOT / ".env")

# Built once: create_stream_router registers its route on a module-level router,
# so calling it per app instance would duplicate the endpoint.
stream_router = create_stream_router(state.price_cache)


def resolve_static_dir() -> Path | None:
    """Directory holding the exported frontend, or None if it has not been built.

    Honors FINALLY_STATIC_DIR (set to /app/backend/static in the container) and
    otherwise falls back to the local Next.js export path.
    """
    override = os.environ.get(STATIC_DIR_ENV_VAR, "").strip()
    if override:
        candidates = [Path(override)]
    else:
        candidates = [BACKEND_DIR / "static", REPO_ROOT / "frontend" / "out"]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


async def _snapshot_loop() -> None:
    """Record total portfolio value every 30 seconds for the P&L chart."""
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(record_snapshot)
        except Exception:
            logger.exception("Portfolio snapshot failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    tickers = await asyncio.to_thread(db.list_watchlist_tickers)
    source = create_market_data_source(state.price_cache)
    await source.start(tickers)
    state.set_market_source(source)
    app.state.price_cache = state.price_cache
    app.state.market_source = source
    logger.info("Market data started for %d tickers", len(tickers))

    # Seed the P&L series so the chart has a point before the first 30s tick.
    await asyncio.to_thread(record_snapshot)
    snapshot_task = asyncio.create_task(_snapshot_loop())

    yield

    snapshot_task.cancel()
    await asyncio.gather(snapshot_task, return_exceptions=True)
    await source.stop()
    state.set_market_source(None)
    logger.info("Market data stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="FinAlly",
        description="AI Trading Workstation",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(health_router)
    app.include_router(portfolio_router)
    app.include_router(watchlist_router)
    app.include_router(stream_router)
    app.include_router(chat_router)

    # Mounted last so it never shadows /api/*. html=True resolves directory
    # indexes, which the frontend's trailingSlash export relies on.
    static_dir = resolve_static_dir()
    if static_dir:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
        logger.info("Serving frontend from %s", static_dir)
    else:
        logger.warning("No frontend build found — API only")

    return app


app = create_app()
