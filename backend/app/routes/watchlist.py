"""Watchlist endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.portfolio import list_watchlist
from app.schemas import WatchlistAddRequest, WatchlistItemResponse
from app.watchlist_service import add_ticker, remove_ticker

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItemResponse])
async def get_watchlist() -> list[dict]:
    """Watched tickers joined with their latest streamed prices."""
    return [item.to_dict() for item in list_watchlist()]


@router.post("", response_model=WatchlistItemResponse)
async def post_watchlist(request: WatchlistAddRequest, response: Response) -> dict:
    """Watch a ticker and start streaming it. 201 when added, 200 when already watched."""
    try:
        item, newly_added = await add_ticker(request.ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response.status_code = 201 if newly_added else 200
    return item.to_dict()


@router.delete("/{ticker}")
async def delete_watchlist(ticker: str) -> dict:
    """Stop watching a ticker and stop streaming it."""
    try:
        removed = await remove_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not removed:
        raise HTTPException(status_code=404, detail=f"{ticker.strip().upper()} is not watched.")
    return {"ticker": ticker.strip().upper(), "removed": True}
