"""The PORT-06 timer half — a 30-second periodic portfolio_snapshots writer.

This is an application-lifecycle concern, not a data-access concern, so it
sits beside `main.py` rather than under `app/db/`. It deliberately shares
`record_portfolio_snapshot` with the trade route (`app.routes.portfolio`) so
the two triggers can never value the portfolio differently. Both triggers
are independently required: the timer must keep recording on a portfolio
nobody is trading, and a trade must record immediately without waiting up
to 30 seconds (D-06).
"""

from __future__ import annotations

import asyncio
import logging

from app.db.snapshots import record_portfolio_snapshot

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SECONDS = 30.0


class SnapshotRecorder:
    """Periodic task recording a portfolio_snapshots row every `interval`
    seconds. Mirrors `SimulatorDataSource`'s start/stop/_run_loop lifecycle
    shape member-for-member."""

    def __init__(self, price_cache, interval: float = SNAPSHOT_INTERVAL_SECONDS) -> None:
        self._cache = price_cache
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Record one point immediately (awaited, synchronously, before this
        returns) so a fresh process shows a chart point right away rather
        than an empty one for the first `interval` seconds — then hand
        subsequent ticks to a background task. The initial write is awaited
        deliberately rather than left to the loop's first iteration: a
        fire-and-forget `asyncio.Task` only runs on some later event-loop
        iteration of the caller's choosing, which (observed under
        `TestClient`) can land mid-request instead of during startup,
        turning any delta-based assertion racy. Awaiting it here makes the
        startup snapshot happen exactly once, deterministically, before
        `start()` returns."""
        await self._tick()
        self._task = asyncio.create_task(self._run_loop(), name="snapshot-loop")
        logger.info("Snapshot recorder started (interval=%.1fs)", self._interval)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Snapshot recorder stopped")

    async def _tick(self) -> None:
        """One recording attempt. The exception guard is the whole reason
        this recorder is reliable: an unguarded write failure inside a
        fire-and-forget `asyncio.Task` would complete the task silently,
        and snapshots would simply stop appearing with no error anywhere
        (T-03-03). Catches Exception, not BaseException, so
        asyncio.CancelledError still propagates and stop() works."""
        try:
            await record_portfolio_snapshot(price_cache=self._cache)
        except Exception:
            logger.exception("Snapshot recording failed")

    async def _run_loop(self) -> None:
        """Sleep, then tick — `start()` already recorded the immediate
        startup point, so this loop only needs to keep recording every
        `interval` seconds after that."""
        while True:
            await asyncio.sleep(self._interval)
            await self._tick()
