"""Portfolio data access — the single entry point for every mutation of
cash, positions, and trade history.

`execute_trade()` is the only code in this project permitted to mutate
`users_profile.cash_balance`, `positions`, or `trades` (the CHAT-03
contract: Phase 4's AI copilot must call this exact function, unchanged).
Every statement in this module uses `?` placeholders; no value is ever
interpolated into SQL text.

Every operand handed to SQL is *derived* via `Decimal(str(value))` —
never from a raw float directly, since that would import the float's
binary imprecision into every downstream sum (D-01) — and every result
read back is *re-checked* the same way. But the mutating arithmetic itself
(`cash_balance - ?`, `quantity - ?`, `cash_balance + ?`) runs as native
SQLite `REAL` (double-precision float) subtraction/addition inside the
UPDATE statement, not as Decimal arithmetic — Decimal never touches the
database layer directly, since SQLite has no Decimal type. This round trip
(Decimal-derive -> float write -> float read -> Decimal-recheck) is exact
for any value both sides can represent with the same string, which is why
`positions.quantity` is quantized to a fixed 6-decimal precision at every
write (`_quantize_quantity`, CR-01/WR-01): it keeps the stored value and
the frontend's `toFixed(6)` display bit-identical, so a full-position sell
of the displayed quantity always lands on (Decimal-exact-zero plus, at
most, float subtraction noise many orders of magnitude below the smallest
representable share unit) rather than drifting relative to the display.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from .connection import DEFAULT_USER_ID, run_db

logger = logging.getLogger(__name__)

# `positions.quantity` is quantized to this many decimal places at every
# write (buy upsert and post-sell remainder) so the stored value is always
# bit-identical to what the frontend's `formatQuantity()` (`toFixed(6)`)
# displays (CR-01). This is the root-cause fix: rather than tolerating
# drift between "what's stored" and "what's shown", the two are made the
# same representation, so a user who reads the displayed quantity and
# sells it back is always selling the exact stored value.
_QUANTITY_SCALE = Decimal("0.000001")

# Below this threshold, a post-sell remainder is treated as a fully-closed
# position rather than a real fractional holding. This is deliberately
# HALF of `_QUANTITY_SCALE` (not equal to it): any *legitimate* quantized
# position differs from zero by at least `_QUANTITY_SCALE` (1e-6), so a
# tolerance of half that value only ever absorbs genuine floating-point
# subtraction noise (typically ~1e-13 to 1e-16 in magnitude) from the raw
# SQLite float arithmetic — it can never mistake a real minimal position
# for dust.
_DUST_TOLERANCE = Decimal("0.0000005")


def _quantize_quantity(value: Decimal) -> Decimal:
    """Round a share quantity to `_QUANTITY_SCALE` decimal places, matching
    the frontend's `toFixed(6)` display precision (CR-01's root-cause fix)."""
    return value.quantize(_QUANTITY_SCALE, rounding=ROUND_HALF_UP)


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

    # CR-02: the HTTP route's Pydantic `Field(gt=0, ...)` is NOT a
    # substitute for a guard here — this function is the documented
    # CHAT-03 entry point Phase 4's AI copilot calls directly, bypassing
    # that layer entirely. A non-positive, NaN, or infinite quantity must
    # be rejected before it reaches any arithmetic: a negative buy would
    # increase cash_balance via `cash_balance - (negative cost)`, and a
    # negative sell would increase the held quantity via
    # `quantity - (negative quantity)` while debiting cash — both mint
    # value from nothing.
    if not quantity_dec.is_finite() or quantity_dec <= 0:
        raise TradeRejectedError(f"Invalid trade quantity: {quantity!r}")

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
        stored_qty = _quantize_quantity(quantity_dec)
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, ticker, float(stored_qty), float(price_dec), now),
        )
        return

    old_qty = Decimal(str(existing["quantity"]))
    old_avg = Decimal(str(existing["avg_cost"]))
    new_qty = old_qty + quantity_dec
    new_avg = (old_qty * old_avg + quantity_dec * price_dec) / new_qty
    # CR-01: quantize the stored quantity (not `new_avg`) to
    # `_QUANTITY_SCALE` so it stays bit-identical to the frontend's
    # `toFixed(6)` display no matter how many decimal digits this buy or
    # the prior stored quantity carried.
    stored_qty = _quantize_quantity(new_qty)
    conn.execute(
        "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? "
        "WHERE user_id = ? AND ticker = ?",
        (float(stored_qty), float(new_avg), now, user_id, ticker),
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
    (D-05, CR-01) — checked against `_DUST_TOLERANCE`, not exact zero. The
    subtraction itself is raw SQLite float arithmetic, so even a bit-for-bit
    identical sell can leave a residual many orders of magnitude below the
    smallest representable share unit (`_QUANTITY_SCALE`); the tolerance
    check absorbs that noise. The root cause is fixed one layer up
    (`_upsert_position_on_buy` quantizes every stored quantity to
    `_QUANTITY_SCALE`), so the *displayed* quantity and the *stored*
    quantity are always the same number — a sell of the displayed quantity
    is a sell of the stored quantity, not an approximation of it. Any
    non-dust remainder is itself re-quantized before being written back, so
    quantization never regresses across a chain of partial sells. `avg_cost`
    is left untouched on every sell path.
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
    if remaining <= _DUST_TOLERANCE:
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        )
    else:
        quantized_remaining = _quantize_quantity(remaining)
        if quantized_remaining != remaining:
            conn.execute(
                "UPDATE positions SET quantity = ? WHERE user_id = ? AND ticker = ?",
                (float(quantized_remaining), user_id, ticker),
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
