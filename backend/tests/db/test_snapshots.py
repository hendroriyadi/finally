"""PORT-06 proof suite: writer correctness, restart durability via an
independent connection, and recorder lifecycle including survival of a
failing iteration.

Uses the `temp_db` fixture (see conftest.py) so nothing here touches the
developer's real database, and a `_FixedPriceCache` double copied from
`tests/db/test_portfolio.py`'s idiom — `record_portfolio_snapshot` calls
only `get_price()`.
"""

from __future__ import annotations

import asyncio

import pytest

import app.snapshot_task as snapshot_task
from app.db.connection import DEFAULT_USER_ID, connect
from app.db.init import init_db
from app.db.snapshots import list_snapshots, record_portfolio_snapshot
from app.snapshot_task import SnapshotRecorder


class _FixedPriceCache:
    """Deterministic stand-in for PriceCache — get_price() is the only
    method record_portfolio_snapshot()'s call chain uses."""

    def __init__(self, prices: dict[str, float]) -> None:
        self._prices = dict(prices)

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)


def _snapshot_count(user_id: str = DEFAULT_USER_ID) -> int:
    conn = connect()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM portfolio_snapshots WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
    finally:
        conn.close()


# --- record_portfolio_snapshot() / list_snapshots() ------------------------


@pytest.mark.asyncio
async def test_writer_inserts_one_row_matching_cash_balance_on_fresh_db(temp_db):
    await init_db()
    cache = _FixedPriceCache({})

    result = await record_portfolio_snapshot(price_cache=cache)

    assert result["total_value"] == pytest.approx(10000.0)
    assert _snapshot_count() == 1


@pytest.mark.asyncio
async def test_writer_includes_position_value_from_the_cache(temp_db):
    await init_db()

    def _seed(conn):
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES ('pos-1', ?, 'AAPL', 10, 100.0, '2026-01-01T00:00:00+00:00')",
            (DEFAULT_USER_ID,),
        )
        conn.execute(
            "UPDATE users_profile SET cash_balance = 9000.0 WHERE id = ?", (DEFAULT_USER_ID,)
        )

    conn = connect()
    try:
        _seed(conn)
        conn.commit()
    finally:
        conn.close()

    cache = _FixedPriceCache({"AAPL": 150.0})
    result = await record_portfolio_snapshot(price_cache=cache)

    # 9000 cash + 10 * 150.0 position value
    assert result["total_value"] == pytest.approx(10500.0)


@pytest.mark.asyncio
async def test_two_calls_produce_two_distinct_rows(temp_db):
    await init_db()
    cache = _FixedPriceCache({})

    await record_portfolio_snapshot(price_cache=cache)
    await record_portfolio_snapshot(price_cache=cache)

    assert _snapshot_count() == 2


# --- Restart durability (D-05, phase success criterion 4) ------------------


@pytest.mark.asyncio
async def test_snapshots_survive_a_fresh_independent_connection(temp_db):
    """Stand-in for a restarted process: nothing about the writing coroutine
    is still alive to serve this read, so a passing assertion can only mean
    the rows are on disk. Reads through a brand-new connect() opened in the
    test body itself, never through run_db and never through the writer."""
    await init_db()
    cache = _FixedPriceCache({})

    await record_portfolio_snapshot(price_cache=cache)
    await record_portfolio_snapshot(price_cache=cache)

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT total_value FROM portfolio_snapshots WHERE user_id = ? ORDER BY recorded_at",
            (DEFAULT_USER_ID,),
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 2
    assert all(row["total_value"] == pytest.approx(10000.0) for row in rows)


@pytest.mark.asyncio
async def test_list_snapshots_returns_oldest_first(temp_db):
    await init_db()
    cache = _FixedPriceCache({})

    await record_portfolio_snapshot(price_cache=cache)
    await record_portfolio_snapshot(price_cache=cache)

    rows = await list_snapshots()

    assert len(rows) == 2
    assert rows[0]["recorded_at"] <= rows[1]["recorded_at"]


# --- SnapshotRecorder lifecycle ---------------------------------------------


@pytest.mark.asyncio
async def test_recorder_writes_more_than_one_row_over_time(temp_db):
    await init_db()
    cache = _FixedPriceCache({})
    recorder = SnapshotRecorder(cache, interval=0.05)

    await recorder.start()
    await asyncio.sleep(0.3)
    await recorder.stop()

    assert _snapshot_count() > 1


@pytest.mark.asyncio
async def test_recorder_stop_is_idempotent(temp_db):
    await init_db()
    cache = _FixedPriceCache({})
    recorder = SnapshotRecorder(cache, interval=0.05)

    await recorder.start()
    await recorder.stop()
    await recorder.stop()  # must not raise


@pytest.mark.asyncio
async def test_no_rows_appear_after_stop(temp_db):
    await init_db()
    cache = _FixedPriceCache({})
    recorder = SnapshotRecorder(cache, interval=0.05)

    await recorder.start()
    await asyncio.sleep(0.2)
    await recorder.stop()

    count_after_stop = _snapshot_count()
    await asyncio.sleep(0.2)

    assert _snapshot_count() == count_after_stop


@pytest.mark.asyncio
async def test_a_failing_iteration_does_not_kill_the_loop(temp_db, monkeypatch):
    await init_db()
    cache = _FixedPriceCache({})

    real_writer = record_portfolio_snapshot
    call_count = {"n": 0}

    async def _flaky(*, price_cache, user_id=DEFAULT_USER_ID):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated transient failure")
        return await real_writer(price_cache=price_cache, user_id=user_id)

    monkeypatch.setattr(snapshot_task, "record_portfolio_snapshot", _flaky)

    recorder = SnapshotRecorder(cache, interval=0.05)
    await recorder.start()
    await asyncio.sleep(0.3)
    await recorder.stop()

    assert call_count["n"] > 1
    assert _snapshot_count() >= 1
