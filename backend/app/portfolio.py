"""Portfolio valuation and trade execution.

Plain functions, no FastAPI types — the HTTP routes and the LLM chat flow both
call these so that "buy N shares of X" has exactly one implementation.

    from app.portfolio import compute_portfolio, execute_trade

    valuation = compute_portfolio()
    result = execute_trade("AAPL", "buy", 10)
    if not result.success:
        show(result.reason)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

import db
from app.market import PriceCache
from app.state import get_price_cache

# Quantities below this are treated as zero — floating point residue from
# fractional-share arithmetic, not a real holding.
EPSILON = 1e-9

VALID_SIDES = ("buy", "sell")


class TradeError:
    """Machine-readable failure codes returned on TradeResult.error_code."""

    INVALID_TICKER = "invalid_ticker"
    INVALID_SIDE = "invalid_side"
    INVALID_QUANTITY = "invalid_quantity"
    NO_PRICE = "no_price"
    INSUFFICIENT_CASH = "insufficient_cash"
    INSUFFICIENT_SHARES = "insufficient_shares"


@dataclass(frozen=True)
class PositionValuation:
    """A holding marked to the live market price."""

    ticker: str
    quantity: float
    avg_cost: float
    current_price: float
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "cost_basis": self.cost_basis,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_percent": self.unrealized_pnl_percent,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class PortfolioValuation:
    """Cash, positions and totals at a point in time."""

    cash_balance: float
    positions: list[PositionValuation]
    positions_value: float
    total_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_percent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash_balance": self.cash_balance,
            "positions": [p.to_dict() for p in self.positions],
            "positions_value": self.positions_value,
            "total_value": self.total_value,
            "cost_basis": self.cost_basis,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_percent": self.unrealized_pnl_percent,
        }


@dataclass(frozen=True)
class TradeResult:
    """Outcome of a trade attempt. Validation failures are results, not exceptions."""

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "ticker": self.ticker,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "cost": self.cost,
            "trade_id": self.trade_id,
            "executed_at": self.executed_at,
            "cash_balance": self.cash_balance,
            "position_quantity": self.position_quantity,
            "position_avg_cost": self.position_avg_cost,
            "total_value": self.total_value,
            "reason": self.reason,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class WatchlistItem:
    """A watched ticker joined with its latest cached price."""

    ticker: str
    added_at: str
    price: float | None
    previous_price: float | None
    change: float | None
    change_percent: float | None
    direction: str
    timestamp: float | None

    @classmethod
    def from_entry(cls, entry: db.WatchlistEntry, cache: PriceCache) -> WatchlistItem:
        update = cache.get(entry.ticker)
        return cls(
            ticker=entry.ticker,
            added_at=entry.added_at,
            price=update.price if update else None,
            previous_price=update.previous_price if update else None,
            change=update.change if update else None,
            change_percent=update.change_percent if update else None,
            direction=update.direction if update else "flat",
            timestamp=update.timestamp if update else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "added_at": self.added_at,
            "price": self.price,
            "previous_price": self.previous_price,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
            "timestamp": self.timestamp,
        }


def _money(value: float) -> float:
    return round(value, 2)


def _cache(price_cache: PriceCache | None) -> PriceCache:
    return price_cache if price_cache is not None else get_price_cache()


def compute_portfolio(
    user_id: str = db.DEFAULT_USER_ID,
    *,
    price_cache: PriceCache | None = None,
    conn: sqlite3.Connection | None = None,
) -> PortfolioValuation:
    """Value every position at the latest cached price and total it with cash.

    A position whose ticker has no cached price falls back to its average cost,
    so it contributes its cost basis and zero P&L rather than vanishing.
    """
    cache = _cache(price_cache)
    profile = db.get_profile(user_id, conn=conn)
    cash_balance = profile.cash_balance if profile else 0.0
    rows = db.list_positions(user_id, conn=conn)

    valued: list[tuple[db.Position, float, float, float]] = []
    positions_value = 0.0
    total_cost_basis = 0.0
    for position in rows:
        price = cache.get_price(position.ticker)
        current_price = price if price is not None else position.avg_cost
        market_value = position.quantity * current_price
        cost_basis = position.quantity * position.avg_cost
        positions_value += market_value
        total_cost_basis += cost_basis
        valued.append((position, current_price, market_value, cost_basis))

    total_value = cash_balance + positions_value

    positions = [
        PositionValuation(
            ticker=position.ticker,
            quantity=position.quantity,
            avg_cost=_money(position.avg_cost),
            current_price=_money(current_price),
            cost_basis=_money(cost_basis),
            market_value=_money(market_value),
            unrealized_pnl=_money(market_value - cost_basis),
            unrealized_pnl_percent=(
                round((market_value - cost_basis) / cost_basis * 100, 4) if cost_basis else 0.0
            ),
            weight=round(market_value / total_value, 6) if total_value else 0.0,
        )
        for position, current_price, market_value, cost_basis in valued
    ]

    unrealized_pnl = positions_value - total_cost_basis
    return PortfolioValuation(
        cash_balance=_money(cash_balance),
        positions=positions,
        positions_value=_money(positions_value),
        total_value=_money(total_value),
        cost_basis=_money(total_cost_basis),
        unrealized_pnl=_money(unrealized_pnl),
        unrealized_pnl_percent=(
            round(unrealized_pnl / total_cost_basis * 100, 4) if total_cost_basis else 0.0
        ),
    )


def total_portfolio_value(
    user_id: str = db.DEFAULT_USER_ID,
    *,
    price_cache: PriceCache | None = None,
    conn: sqlite3.Connection | None = None,
) -> float:
    """Cash plus the marked-to-market value of every position."""
    return compute_portfolio(user_id, price_cache=price_cache, conn=conn).total_value


def record_snapshot(
    user_id: str = db.DEFAULT_USER_ID,
    *,
    price_cache: PriceCache | None = None,
    conn: sqlite3.Connection | None = None,
) -> db.PortfolioSnapshot:
    """Append the current total portfolio value to the P&L series."""
    total = total_portfolio_value(user_id, price_cache=price_cache, conn=conn)
    return db.insert_snapshot(total, user_id, conn=conn)


def execute_trade(
    ticker: str,
    side: str,
    quantity: float,
    user_id: str = db.DEFAULT_USER_ID,
    *,
    price_cache: PriceCache | None = None,
) -> TradeResult:
    """Fill a market order at the current cached price.

    Buys require sufficient cash, sells require sufficient shares; both failures
    come back as ``TradeResult(success=False)`` with a human-readable ``reason``
    suitable for showing to the user or feeding back to the LLM. Cash, position,
    trade log and portfolio snapshot are written in a single transaction.
    """
    symbol = db.normalize_ticker(ticker)
    side = side.strip().lower()

    if not symbol:
        return _rejected(symbol, side, quantity, TradeError.INVALID_TICKER, "Ticker is required.")
    if side not in VALID_SIDES:
        return _rejected(
            symbol, side, quantity, TradeError.INVALID_SIDE, "Side must be 'buy' or 'sell'."
        )
    if quantity <= 0:
        return _rejected(
            symbol, side, quantity, TradeError.INVALID_QUANTITY, "Quantity must be greater than 0."
        )

    price = _cache(price_cache).get_price(symbol)
    if price is None:
        return _rejected(
            symbol,
            side,
            quantity,
            TradeError.NO_PRICE,
            f"No live price for {symbol}. Add it to the watchlist first.",
        )

    with db.transaction() as conn:
        profile = db.get_profile(user_id, conn=conn) or db.create_profile(user_id, conn=conn)
        position = db.get_position(symbol, user_id, conn=conn)
        old_quantity = position.quantity if position else 0.0
        old_avg_cost = position.avg_cost if position else 0.0
        cost = _money(quantity * price)

        if side == "buy":
            if cost > profile.cash_balance + EPSILON:
                return _rejected(
                    symbol,
                    side,
                    quantity,
                    TradeError.INSUFFICIENT_CASH,
                    f"Insufficient cash: {symbol} x{quantity:g} costs ${cost:,.2f} "
                    f"but only ${profile.cash_balance:,.2f} is available.",
                    price=price,
                )
            new_quantity = old_quantity + quantity
            new_avg_cost = (old_quantity * old_avg_cost + quantity * price) / new_quantity
            cash_delta = -cost
        else:
            if quantity > old_quantity + EPSILON:
                return _rejected(
                    symbol,
                    side,
                    quantity,
                    TradeError.INSUFFICIENT_SHARES,
                    f"Insufficient shares: cannot sell {quantity:g} {symbol}, "
                    f"only {old_quantity:g} held.",
                    price=price,
                )
            new_quantity = old_quantity - quantity
            new_avg_cost = old_avg_cost
            cash_delta = cost

        profile = db.adjust_cash_balance(cash_delta, user_id, conn=conn)
        if new_quantity <= EPSILON:
            db.delete_position(symbol, user_id, conn=conn)
            new_quantity = 0.0
            new_avg_cost = 0.0
        else:
            db.upsert_position(symbol, new_quantity, new_avg_cost, user_id, conn=conn)

        trade = db.insert_trade(symbol, side, quantity, price, user_id, conn=conn)
        snapshot = record_snapshot(user_id, price_cache=price_cache, conn=conn)

    return TradeResult(
        success=True,
        ticker=symbol,
        side=side,
        quantity=quantity,
        price=price,
        cost=cost,
        trade_id=trade.id,
        executed_at=trade.executed_at,
        cash_balance=_money(profile.cash_balance),
        position_quantity=new_quantity,
        position_avg_cost=_money(new_avg_cost),
        total_value=snapshot.total_value,
    )


def list_watchlist(
    user_id: str = db.DEFAULT_USER_ID,
    *,
    price_cache: PriceCache | None = None,
) -> list[WatchlistItem]:
    """Watchlist entries joined with the latest cached price for each ticker."""
    cache = _cache(price_cache)
    return [WatchlistItem.from_entry(entry, cache) for entry in db.list_watchlist(user_id)]


def _rejected(
    ticker: str,
    side: str,
    quantity: float,
    error_code: str,
    reason: str,
    price: float | None = None,
) -> TradeResult:
    return TradeResult(
        success=False,
        ticker=ticker,
        side=side,
        quantity=quantity,
        price=price,
        reason=reason,
        error_code=error_code,
    )
