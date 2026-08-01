"""Pydantic request and response models for the REST API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TradeRequest(BaseModel):
    """Market order. Fills instantly at the current streaming price."""

    ticker: str = Field(min_length=1, max_length=10)
    quantity: float = Field(gt=0)
    side: Literal["buy", "sell"]


class WatchlistAddRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)


class PositionResponse(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    weight: float


class PortfolioResponse(BaseModel):
    cash_balance: float
    positions: list[PositionResponse]
    positions_value: float
    total_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_percent: float


class TradeResponse(BaseModel):
    success: bool
    ticker: str
    side: str
    quantity: float
    price: float | None = None
    cost: float | None = None
    trade_id: str | None = None
    executed_at: str | None = None
    cash_balance: float | None = None
    position_quantity: float | None = None
    position_avg_cost: float | None = None
    total_value: float | None = None
    reason: str | None = None
    error_code: str | None = None


class SnapshotResponse(BaseModel):
    total_value: float
    recorded_at: str


class WatchlistItemResponse(BaseModel):
    ticker: str
    added_at: str
    price: float | None = None
    previous_price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    direction: str
    timestamp: float | None = None


class HealthResponse(BaseModel):
    status: str
    database: str
    market_data: str
    tracked_tickers: int
    cached_prices: int
