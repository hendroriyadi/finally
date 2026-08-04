"""Portfolio REST router.

Every wire-facing numeric field is annotated `float`, never `Decimal` —
Pydantic v2 serializes a `Decimal`-annotated field to a JSON *string* in the
`mode="json"` FastAPI's response serialization uses, which would silently
poison any downstream arithmetic consumer (e.g. the frontend's
`current_price * quantity`) rather than raise. The route stays a thin
translator of `execute_trade()`'s outcomes to status codes — it performs no
balance or position read of its own before calling the engine, trusting the
engine's atomic guard as the single source of rejection truth, exactly as
the watchlist POST handler trusts `add_watchlist_ticker`.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.portfolio import (
    InsufficientCashError,
    InsufficientSharesError,
    NoPriceAvailableError,
    TradeRejectedError,
    execute_trade,
    get_portfolio_state,
    value_portfolio,
)
from app.db.snapshots import list_snapshots, record_portfolio_snapshot
from app.routes.watchlist import normalize_ticker

logger = logging.getLogger(__name__)


class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    side: Literal["buy", "sell"]
    # Lower bound rejects zero/negative quantities (a negative buy would
    # manufacture cash) and a NaN payload (a NaN comparison is always
    # false); upper bound rejects a positive-infinity payload. Both run at
    # the Pydantic layer, before the handler body (T-02-03).
    quantity: float = Field(gt=0, le=1_000_000_000)


class HoldingOut(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float


class PositionOut(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None
    unrealized_pnl: float | None
    change_percent: float | None


class PortfolioResponse(BaseModel):
    cash_balance: float
    total_value: float
    positions: list[PositionOut]


class TradeResponse(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    cash_balance: float
    position: HoldingOut | None


class SnapshotOut(BaseModel):
    total_value: float
    recorded_at: str


class PortfolioHistoryResponse(BaseModel):
    snapshots: list[SnapshotOut]


def create_portfolio_router() -> APIRouter:
    """Create the portfolio router, prefix='/api/portfolio'.

    Handlers reach the live price cache through
    `request.app.state.price_cache` — the same DI pattern the watchlist
    router uses for `app.state.market_source`.
    """
    router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

    @router.get("", response_model=PortfolioResponse)
    async def get_portfolio(request: Request) -> PortfolioResponse:
        state = await get_portfolio_state()
        valued = value_portfolio(state, request.app.state.price_cache)
        return PortfolioResponse(**valued)

    @router.get("/history", response_model=PortfolioHistoryResponse)
    async def get_portfolio_history() -> PortfolioHistoryResponse:
        rows = await list_snapshots()
        return PortfolioHistoryResponse(snapshots=[SnapshotOut(**row) for row in rows])

    @router.post("/trade", response_model=TradeResponse)
    async def trade(body: TradeRequest, request: Request) -> TradeResponse:
        ticker = normalize_ticker(body.ticker)

        # No preflight balance/position read here — the route trusts
        # execute_trade()'s atomic guard as the single source of rejection
        # truth (Pitfall 4 / T-02-*), exactly as the watchlist POST handler
        # trusts add_watchlist_ticker rather than pre-checking count_watchlist().
        try:
            result = await execute_trade(
                ticker,
                body.side,
                body.quantity,
                price_cache=request.app.state.price_cache,
            )
        except NoPriceAvailableError:
            raise HTTPException(
                status_code=400, detail=f"No live price available for {ticker}"
            ) from None
        except InsufficientCashError:
            raise HTTPException(
                status_code=409, detail=f"Insufficient cash to buy {ticker}"
            ) from None
        except InsufficientSharesError:
            raise HTTPException(
                status_code=409, detail=f"Insufficient shares to sell {ticker}"
            ) from None
        except TradeRejectedError as exc:
            raise HTTPException(
                status_code=400, detail=f"Trade rejected for {ticker}: {exc}"
            ) from None

        # The trade has already committed at this point (D-02, D-06). A
        # failure here must never turn an already-filled trade into an
        # error response — log and continue, exactly as it would if the
        # 30-second timer's own iteration failed (T-03-04).
        try:
            await record_portfolio_snapshot(price_cache=request.app.state.price_cache)
        except Exception:
            logger.exception("record_portfolio_snapshot failed after trade on %s", ticker)

        return TradeResponse(**result)

    return router
