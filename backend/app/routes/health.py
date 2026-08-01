"""Health check endpoint — polled by the Docker HEALTHCHECK and the start scripts."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

import db
from app.schemas import HealthResponse
from app.state import get_market_source, get_price_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> dict:
    """Confirm the process is up and the database is reachable.

    The database touch also triggers lazy schema creation and seeding, so the
    first successful health check means the app is genuinely ready to serve.
    """
    try:
        db.get_profile()
    except Exception as exc:
        logger.exception("Health check failed: database unreachable")
        raise HTTPException(status_code=503, detail=f"Database unreachable: {exc}") from exc

    source = get_market_source()
    cache = get_price_cache()
    return {
        "status": "ok",
        "database": "ok",
        "market_data": type(source).__name__ if source else "stopped",
        "tracked_tickers": len(source.get_tickers()) if source else 0,
        "cached_prices": len(cache),
    }
