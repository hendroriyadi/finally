"""TEST-01: proof suite for `execute_trade()` — money math, state integrity,
and concurrency races.

This file exercises the engine directly (`app.db.portfolio.execute_trade`),
below the HTTP layer, using the `temp_db` fixture so it never touches the
developer's real database. Every persisted-state assertion reads through a
brand-new `connect()` (`_read_state`), never through the dict `execute_trade`
returns — the returned dict is the engine's claim; the fresh connection is
the evidence.
"""

from __future__ import annotations

import pytest

from app.db.connection import DEFAULT_USER_ID, connect
from app.db.init import init_db
from app.db.portfolio import (
    InsufficientCashError,
    InsufficientSharesError,
    NoPriceAvailableError,
    execute_trade,
)


class _FixedPriceCache:
    """Deterministic stand-in for PriceCache — get_price() is the only method
    execute_trade() calls, so the double implements exactly that."""

    def __init__(self, prices: dict[str, float]) -> None:
        self._prices = dict(prices)

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    def set_price(self, ticker: str, price: float) -> None:
        self._prices[ticker] = price


def _read_state(ticker: str) -> tuple[float, tuple[float, float] | None, int]:
    """Read cash, the (quantity, avg_cost) of one position, and the trades row
    count from a brand-new connection. Returns None for the position when no
    row exists, which is how a full-position sell is distinguished from a
    zero-quantity row."""
    conn = connect()
    try:
        cash = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
        ).fetchone()[0]
        row = conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
            (DEFAULT_USER_ID, ticker),
        ).fetchone()
        trades = conn.execute(
            "SELECT COUNT(*) FROM trades WHERE user_id = ?", (DEFAULT_USER_ID,)
        ).fetchone()[0]
    finally:
        conn.close()
    return cash, (None if row is None else (row[0], row[1])), trades


# --- Task 1: money math and state integrity — the exact-value suite --------


async def test_fractional_buy_debits_exact_cash_and_creates_position(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 200.0})

    await execute_trade("AAPL", "buy", 0.5, price_cache=cache)

    cash, position, trades = _read_state("AAPL")
    assert cash == 9900.0
    assert position == (0.5, 200.0)
    assert trades == 1


async def test_fractional_sell_credits_exact_cash_and_reduces_quantity(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 200.0})
    await execute_trade("AAPL", "buy", 0.5, price_cache=cache)

    await execute_trade("AAPL", "sell", 0.25, price_cache=cache)

    cash, position, trades = _read_state("AAPL")
    assert cash == 9950.0
    assert position == (0.25, 200.0)
    assert trades == 2


async def test_buy_spending_exact_balance_succeeds_and_lands_on_zero(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 200.0})

    await execute_trade("AAPL", "buy", 50, price_cache=cache)

    cash, position, _ = _read_state("AAPL")
    assert cash == 0.0
    assert position == (50.0, 200.0)


async def test_buy_one_cent_over_balance_raises_and_leaves_state_untouched(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 200.0})
    before = _read_state("AAPL")

    with pytest.raises(InsufficientCashError):
        await execute_trade("AAPL", "buy", 50.01, price_cache=cache)

    assert _read_state("AAPL") == before


async def test_second_buy_produces_exact_weighted_average_cost(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 100.0})

    await execute_trade("AAPL", "buy", 10, price_cache=cache)
    cache.set_price("AAPL", 130.0)
    await execute_trade("AAPL", "buy", 5, price_cache=cache)

    _, position, _ = _read_state("AAPL")
    assert position == (15.0, 110.0)  # (10*100 + 5*130) / 15 == 110.0 exactly

    conn = connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM positions WHERE user_id = ? AND ticker = ?",
            (DEFAULT_USER_ID, "AAPL"),
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1  # one updated row, not a second lot row


async def test_full_position_sell_leaves_no_row(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 100.0})
    await execute_trade("AAPL", "buy", 10, price_cache=cache)
    cache.set_price("AAPL", 130.0)
    await execute_trade("AAPL", "buy", 5, price_cache=cache)

    await execute_trade("AAPL", "sell", 15.0, price_cache=cache)

    _, position, _ = _read_state("AAPL")
    assert position is None  # absence of the row, not a zero quantity


async def test_oversell_raises_and_leaves_state_untouched(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 100.0})
    await execute_trade("AAPL", "buy", 15.0, price_cache=cache)
    before = _read_state("AAPL")

    with pytest.raises(InsufficientSharesError):
        await execute_trade("AAPL", "sell", 15.000001, price_cache=cache)

    assert _read_state("AAPL") == before


async def test_sell_of_unheld_ticker_raises_and_leaves_state_untouched(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 100.0})
    before = _read_state("AAPL")

    with pytest.raises(InsufficientSharesError):
        await execute_trade("AAPL", "sell", 1, price_cache=cache)

    assert _read_state("AAPL") == before


async def test_trade_with_no_cached_price_raises_and_leaves_state_untouched(temp_db):
    await init_db()
    cache = _FixedPriceCache({})
    before = _read_state("AAPL")

    with pytest.raises(NoPriceAvailableError):
        await execute_trade("AAPL", "buy", 1, price_cache=cache)

    assert _read_state("AAPL") == before


async def test_trade_log_records_one_row_per_successful_trade(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 200.0})

    await execute_trade("AAPL", "buy", 10, price_cache=cache)
    await execute_trade("AAPL", "sell", 4, price_cache=cache)

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT side, quantity, price FROM trades WHERE user_id = ? "
            "ORDER BY executed_at, rowid",
            (DEFAULT_USER_ID,),
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    assert rows[0]["side"] == "buy"
    assert rows[0]["quantity"] == 10.0
    assert rows[0]["price"] == 200.0
    assert rows[1]["side"] == "sell"
    assert rows[1]["quantity"] == 4.0
    assert rows[1]["price"] == 200.0


