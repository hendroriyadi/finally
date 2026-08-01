"""Portfolio and trading endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import db
from app.portfolio import compute_portfolio, execute_trade
from app.schemas import PortfolioResponse, SnapshotResponse, TradeRequest, TradeResponse

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioResponse)
async def get_portfolio() -> dict:
    """Positions marked to market, cash balance, total value and unrealized P&L."""
    return compute_portfolio().to_dict()


@router.post("/trade", response_model=TradeResponse)
async def post_trade(request: TradeRequest) -> dict:
    """Execute a market order at the current streaming price.

    Validation failures (insufficient cash or shares, untracked ticker) return 400
    with the same payload shape, including a human-readable ``reason``.
    """
    result = execute_trade(request.ticker, request.side, request.quantity)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.to_dict())
    return result.to_dict()


@router.get("/history", response_model=list[SnapshotResponse])
async def get_history(limit: int | None = Query(default=None, gt=0, le=5000)) -> list[dict]:
    """Total portfolio value over time, oldest first — the P&L chart series."""
    snapshots = db.list_snapshots(limit=limit)
    return [
        {"total_value": snapshot.total_value, "recorded_at": snapshot.recorded_at}
        for snapshot in snapshots
    ]
