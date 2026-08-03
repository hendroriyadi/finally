"""Portfolio data access — the single entry point for every mutation of
cash, positions, and trade history.

`execute_trade()` is the only code in this project permitted to mutate
`users_profile.cash_balance`, `positions`, or `trades` (the CHAT-03
contract: Phase 4's AI copilot must call this exact function, unchanged).
Every statement in this module uses `?` placeholders; no value is ever
interpolated into SQL text. All arithmetic is `Decimal` — constructed via
`Decimal(str(value))`, never from a raw float directly, since that would
import the float's binary imprecision into every downstream sum — with
`float` appearing only at the SQLite `REAL` write boundary and the
dict-return boundary consumed by the route layer.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from .connection import DEFAULT_USER_ID, run_db

logger = logging.getLogger(__name__)


class TradeRejectedError(Exception):
    """Base class for every reason execute_trade() can refuse a trade."""


class InsufficientCashError(TradeRejectedError):
    """Raised when a buy's atomic cash guard blocks the UPDATE (rowcount == 0)."""


class InsufficientSharesError(TradeRejectedError):
    """Raised when a sell's atomic quantity guard blocks the UPDATE (rowcount == 0)."""


class NoPriceAvailableError(TradeRejectedError):
    """Raised when the price cache has no cached price for the requested ticker."""


async def execute_trade(
    ticker: str,
    side: str,
    quantity: float,
    *,
    price_cache,
    user_id: str = DEFAULT_USER_ID,
) -> dict:
    """Execute a single buy or sell atomically, or raise a TradeRejectedError subclass.

    Reads the fill price from `price_cache` before touching the database or
    doing any arithmetic — a missing price is rejected immediately (D-03).
    The cash mutation, the position upsert, and the trade-log insert all
    happen inside one `run_db()` unit of work, so a rejection anywhere
    inside `_txn` rolls all three back together and leaves zero trace.
    """
    price = price_cache.get_price(ticker)
    if price is None:
        raise NoPriceAvailableError(f"No live price available for {ticker}")

    # Route every float through str() before Decimal() — constructing a
    # Decimal directly from a float would import that float's binary
    # imprecision into every downstream sum (D-01).
    price_dec = Decimal(str(price))
    quantity_dec = Decimal(str(quantity))
    cost = quantity_dec * price_dec
    now = datetime.now(timezone.utc).isoformat()
    trade_id = str(uuid.uuid4())

    def _txn(conn: sqlite3.Connection) -> dict:
        if side == "buy":
            _apply_buy(conn, user_id=user_id, cost=cost)
            _upsert_position_on_buy(
                conn,
                user_id=user_id,
                ticker=ticker,
                quantity_dec=quantity_dec,
                price_dec=price_dec,
                now=now,
            )
        elif side == "sell":
            _apply_sell(
                conn,
                user_id=user_id,
                ticker=ticker,
                quantity_dec=quantity_dec,
                proceeds=cost,
            )
        else:
            # A caller bypassing the Pydantic layer (Phase 4's copilot parsing
            # model output) must not be able to reach the database with an
            # unexpected side.
            raise TradeRejectedError(f"Unrecognized trade side: {side!r}")

        conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (trade_id, user_id, ticker, side, float(quantity_dec), float(price_dec), now),
        )

        cash_row = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
        ).fetchone()
        position_row = conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        ).fetchone()

        position = None
        if position_row is not None:
            position = {
                "ticker": ticker,
                "quantity": position_row["quantity"],
                "avg_cost": position_row["avg_cost"],
            }

        return {
            "ticker": ticker,
            "side": side,
            "quantity": float(quantity_dec),
            "price": float(price_dec),
            "cash_balance": cash_row["cash_balance"],
            "position": position,
        }

    return await run_db(_txn)


def _apply_buy(conn: sqlite3.Connection, *, user_id: str, cost: Decimal) -> None:
    """Atomic cash guard: the sufficiency test and the debit are the same
    statement, checked via `cursor.rowcount` (D-02, T-02-01). No balance is
    ever read into Python and compared there — that is the check-then-act
    race PORT-04 exists to prevent."""
    cur = conn.execute(
        "UPDATE users_profile SET cash_balance = cash_balance - ? WHERE id = ? AND cash_balance >= ?",
        (float(cost), user_id, float(cost)),
    )
    if cur.rowcount == 0:
        raise InsufficientCashError(f"Insufficient cash to buy for {user_id!r}")


def _upsert_position_on_buy(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    ticker: str,
    quantity_dec: Decimal,
    price_dec: Decimal,
    now: str,
) -> None:
    """Weighted-average-cost upsert (D-04) — first buy inserts, later buys
    recompute `new_avg_cost` as the weighted average of the old and new
    lots, all in Decimal."""
    existing = conn.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()

    if existing is None:
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, ticker, float(quantity_dec), float(price_dec), now),
        )
        return

    old_qty = Decimal(str(existing["quantity"]))
    old_avg = Decimal(str(existing["avg_cost"]))
    new_qty = old_qty + quantity_dec
    new_avg = (old_qty * old_avg + quantity_dec * price_dec) / new_qty
    conn.execute(
        "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? "
        "WHERE user_id = ? AND ticker = ?",
        (float(new_qty), float(new_avg), now, user_id, ticker),
    )


def _apply_sell(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    ticker: str,
    quantity_dec: Decimal,
    proceeds: Decimal,
) -> None:
    """Atomic share guard (mirror of `_apply_buy`'s cash guard, D-02, T-02-02):
    the sufficiency test and the debit are the same statement, checked via
    `cursor.rowcount`. A missing position row and an insufficient one both
    fall out as zero affected rows, so one guard covers both without a
    separate existence check. This raise happens before the cash credit, so
    a rejected sell can never mint proceeds.

    Full-position sell deletes the row rather than leaving `quantity == 0`
    (D-05) — compared against exact zero, no tolerance window, since the
    subtrahend is bit-identical to the stored value when the caller sells
    exactly what is held. `avg_cost` is left untouched on every sell path.
    """
    cur = conn.execute(
        "UPDATE positions SET quantity = quantity - ? WHERE user_id = ? AND ticker = ? AND quantity >= ?",
        (float(quantity_dec), user_id, ticker, float(quantity_dec)),
    )
    if cur.rowcount == 0:
        raise InsufficientSharesError(f"Insufficient shares to sell {ticker} for {user_id!r}")

    remaining_row = conn.execute(
        "SELECT quantity FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()
    remaining = Decimal(str(remaining_row["quantity"]))
    if remaining == Decimal("0"):
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        )

    conn.execute(
        "UPDATE users_profile SET cash_balance = cash_balance + ? WHERE id = ?",
        (float(proceeds), user_id),
    )


async def get_portfolio_state(user_id: str = DEFAULT_USER_ID) -> dict:
    """Read cash balance and every open position in one transaction.

    One `run_db()` call for both reads matters: a concurrent trade between
    two separate reads would produce a cash figure and a position list that
    never coexisted.
    """

    def _read(conn: sqlite3.Connection) -> dict:
        cash_row = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
        ).fetchone()
        position_rows = conn.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker",
            (user_id,),
        ).fetchall()
        return {
            "cash_balance": cash_row["cash_balance"] if cash_row is not None else 0.0,
            "positions": [
                {
                    "ticker": row["ticker"],
                    "quantity": row["quantity"],
                    "avg_cost": row["avg_cost"],
                }
                for row in position_rows
            ],
        }

    return await run_db(_read)


def value_portfolio(state: dict, price_cache) -> dict:
    """Pure valuation function — no I/O, no `await`. Values `state` (as
    returned by `get_portfolio_state()`) against `price_cache`.

    A position whose ticker has no cached price reports `None` for
    `current_price`, `unrealized_pnl`, and `change_percent`, and its cost
    basis (quantity * avg_cost) still contributes to `total_value` so the
    total stays defined instead of crashing. Kept here rather than in the
    route so Phase 4's copilot can build its portfolio context from the
    same two calls the HTTP route uses.
    """
    total = Decimal(str(state["cash_balance"]))
    positions_out = []

    for holding in state["positions"]:
        qty_dec = Decimal(str(holding["quantity"]))
        avg_dec = Decimal(str(holding["avg_cost"]))
        price = price_cache.get_price(holding["ticker"])

        if price is None:
            total += qty_dec * avg_dec
            positions_out.append(
                {
                    "ticker": holding["ticker"],
                    "quantity": float(qty_dec),
                    "avg_cost": float(avg_dec),
                    "current_price": None,
                    "unrealized_pnl": None,
                    "change_percent": None,
                }
            )
            continue

        price_dec = Decimal(str(price))
        pnl = (price_dec - avg_dec) * qty_dec
        change_percent = (
            (price_dec - avg_dec) / avg_dec * Decimal("100") if avg_dec != 0 else Decimal("0")
        )
        total += qty_dec * price_dec
        positions_out.append(
            {
                "ticker": holding["ticker"],
                "quantity": float(qty_dec),
                "avg_cost": float(avg_dec),
                "current_price": float(price_dec),
                "unrealized_pnl": float(pnl),
                "change_percent": float(change_percent),
            }
        )

    return {
        "cash_balance": float(Decimal(str(state["cash_balance"]))),
        "total_value": float(total),
        "positions": positions_out,
    }
