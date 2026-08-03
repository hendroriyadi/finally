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

import asyncio

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


# --- Task 2: the race proof — twenty callers, one finite balance -----------


def _set_cash_balance(cash: float) -> None:
    """Direct write through a fresh connection — seeding through the engine
    would itself consume the balance the test is trying to pin."""
    conn = connect()
    try:
        conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
            (cash, DEFAULT_USER_ID),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_position(ticker: str, quantity: float, avg_cost: float) -> None:
    """Direct row insert through a fresh connection, bypassing `execute_trade`
    entirely so the seeded quantity is exactly what the test pins."""
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"seed-{ticker}",
                DEFAULT_USER_ID,
                ticker,
                quantity,
                avg_cost,
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def test_concurrent_buys_never_overdraw_balance(temp_db):
    """T-02-10: `run_db` hands each call to `asyncio.to_thread` with its own
    connection, and SQLite serializes writers under its own lock in WAL
    mode, so the guard being inside the mutating UPDATE statement is the
    only thing standing between twenty threads and an overdrawn balance."""
    await init_db()
    cache = _FixedPriceCache({"AAPL": 100.0})
    seeded_cash = 1_000.0  # affords exactly one buy of 10 shares @ 100.0
    _set_cash_balance(seeded_cash)

    async def try_buy(_i: int) -> bool:
        try:
            await execute_trade("AAPL", "buy", 10, price_cache=cache)
        except InsufficientCashError:
            return False
        return True

    results = await asyncio.gather(*(try_buy(i) for i in range(20)))

    cash, _, trades = _read_state("AAPL")
    assert sum(results) == 1
    assert cash == seeded_cash - 10 * 100.0
    assert cash >= 0
    assert trades == sum(results)


async def test_concurrent_full_sells_never_oversell(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 100.0})
    _seed_position("AAPL", 10.0, 100.0)

    async def try_sell(_i: int) -> bool:
        try:
            await execute_trade("AAPL", "sell", 10, price_cache=cache)
        except InsufficientSharesError:
            return False
        return True

    results = await asyncio.gather(*(try_sell(i) for i in range(20)))

    _, position, trades = _read_state("AAPL")
    assert sum(results) == 1
    assert position is None
    assert trades == 1


async def test_concurrent_partial_sells_fill_exactly_what_position_affords(temp_db):
    await init_db()
    cache = _FixedPriceCache({"AAPL": 100.0})
    starting_qty = 35.0  # affords exactly 3 sells of 10 shares, 5 left over
    _seed_position("AAPL", starting_qty, 100.0)

    async def try_sell(_i: int) -> bool:
        try:
            await execute_trade("AAPL", "sell", 10, price_cache=cache)
        except InsufficientSharesError:
            return False
        return True

    results = await asyncio.gather(*(try_sell(i) for i in range(20)))

    _, position, _ = _read_state("AAPL")
    remaining_qty = position[0] if position is not None else 0.0
    assert sum(results) == 3
    assert remaining_qty >= 0
    assert remaining_qty == starting_qty - 3 * 10.0


async def test_concurrent_mixed_buys_and_sells_keep_state_non_negative(temp_db):
    """Interleaving order legitimately varies between runs, so only
    invariants are asserted here, not an exact final balance — pinning an
    exact number would produce a test that is flaky by construction, whereas
    non-negativity and a matching trades count are exactly what a real
    double-spend or double-sell would break on any interleaving."""
    await init_db()
    cache = _FixedPriceCache({"AAPL": 100.0})
    seeded_cash = 1_000.0  # affords exactly one buy of 10 @ 100.0
    seeded_qty = 10.0  # affords exactly one sell of 10 @ 100.0
    _set_cash_balance(seeded_cash)
    _seed_position("AAPL", seeded_qty, 100.0)

    async def try_buy(_i: int) -> bool:
        try:
            await execute_trade("AAPL", "buy", 10, price_cache=cache)
        except InsufficientCashError:
            return False
        return True

    async def try_sell(_i: int) -> bool:
        try:
            await execute_trade("AAPL", "sell", 10, price_cache=cache)
        except InsufficientSharesError:
            return False
        return True

    results = await asyncio.gather(
        *([try_buy(i) for i in range(10)] + [try_sell(i) for i in range(10)])
    )

    cash, position, trades = _read_state("AAPL")
    remaining_qty = position[0] if position is not None else 0.0

    assert cash >= 0
    assert remaining_qty >= 0
    assert trades == sum(results)


