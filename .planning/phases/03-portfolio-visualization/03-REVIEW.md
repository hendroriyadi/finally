---
phase: 03-portfolio-visualization
reviewed: 2026-08-04T01:27:59Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - backend/app/db/snapshots.py
  - backend/app/main.py
  - backend/app/routes/portfolio.py
  - backend/app/snapshot_task.py
  - backend/tests/db/test_snapshots.py
  - backend/tests/routes/test_portfolio.py
  - frontend/app/page.tsx
  - frontend/components/DetailChart.tsx
  - frontend/components/PnLChart.tsx
  - frontend/components/PortfolioHeatmap.tsx
  - frontend/components/WatchlistPanel.tsx
  - frontend/components/WatchlistRow.tsx
  - frontend/lib/api.ts
  - frontend/lib/types.ts
  - frontend/lib/useSseStream.ts
findings:
  critical: 0
  warning: 6
  info: 5
  total: 11
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-08-04T01:27:59Z
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Phase 3 adds a `portfolio_snapshots` writer (trade-triggered + 30s timer), `GET /api/portfolio/history`, and three new Recharts-based frontend panels (`PnLChart`, `PortfolioHeatmap`, `DetailChart`) plus watchlist row click-to-select wiring. The backend money/transaction discipline established in earlier phases (Decimal-derived arithmetic, atomic rowcount guards, one `run_db()` call per unit of work) is respected — `snapshots.py` never touches `cash_balance`/`positions`/`trades`, and `execute_trade()` remains untouched. SQL is fully parameterized throughout; no injection, secret, or unsafe-eval patterns were found in any of the 15 files. No BLOCKER/Critical-severity defects were found.

The issues found are all Warning/Info tier: an `asyncio.to_thread` cancellation race in `SnapshotRecorder.stop()` that can let a write land after "stop" returns, a pre-existing (not introduced by this phase, but present in the reviewed file) watchlist-reset bug in `main.py`'s ticker fallback, an accessibility regression in the new clickable watchlist row (nested interactive elements, and a heatmap with zero information available on small cells), a test assertion that doesn't actually verify what its name claims, and some minor duplication/coverage gaps.

## Warnings

### WR-01: `SnapshotRecorder.stop()` cannot guarantee no write lands after it returns

**File:** `backend/app/snapshot_task.py:50-58`
**Issue:** `stop()` cancels `self._task` and awaits it, which is the correct pattern for a pure-asyncio loop. But `_tick()` (called from `_run_loop()`) awaits `record_portfolio_snapshot()`, which ultimately awaits `asyncio.to_thread(_run)` in `connection.py`. Cancelling the *awaiting* coroutine does not stop the underlying `ThreadPoolExecutor` worker thread that is already running `_run()` — the thread keeps executing (including `conn.commit()`) to completion regardless of the cancellation; only the coroutine's `await` point raises `CancelledError`. If `stop()` is called while a tick's DB write is already in flight on the worker thread, that write can still land in the database after `stop()` has returned, silently violating the "no rows after stop" invariant the class's docstring and `test_no_rows_appear_after_stop` assume. In production this produces at most one harmless extra snapshot row, but it is a real correctness gap in the shutdown contract and a source of test flakiness under load.
**Fix:** Either document that `stop()` only guarantees no *new* tick will be scheduled (not that an in-flight write is aborted), or track in-flight writes explicitly (e.g. an `asyncio.Event`/counter set inside `_tick()`) and have `stop()` wait on that instead of relying on task cancellation timing:
```python
async def stop(self) -> None:
    if self._task and not self._task.done():
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
    # NOTE: cancellation does not abort an in-flight asyncio.to_thread()
    # write already dispatched to the executor; a tick that was mid-write
    # when stop() was called can still commit after this returns.
    self._task = None
```

### WR-02: Empty watchlist silently falls back to the default 10 tickers on restart

**File:** `backend/app/main.py:40`
**Issue:** `tickers = [row["ticker"] for row in watchlist] or list(SEED_PRICES.keys())`. If a user deliberately removes every ticker from their watchlist and the container restarts, `list_watchlist()` returns `[]`, which is falsy, so `or` silently substitutes the full default ticker list. The market data source (and therefore the SSE stream and the price cache the new `SnapshotRecorder`/`/api/portfolio/history` valuation depend on) starts tracking tickers the user explicitly removed, even though `GET /api/watchlist` correctly reports an empty list. This line predates Phase 3 (unchanged by this diff) but is present in a file in this review's scope and directly feeds the new snapshot-recording path's price lookups.
**Fix:** Distinguish "no watchlist rows at all" (first-ever boot) from "watchlist intentionally emptied" — e.g. seed the default watchlist rows into the DB on first run instead of using this runtime fallback, or track first-run state explicitly:
```python
tickers = [row["ticker"] for row in watchlist]
if watchlist is None:  # only true before the table has ever been seeded
    tickers = list(SEED_PRICES.keys())
```

### WR-03: `WatchlistRow` nests a real `<button>` inside a `role="button"` div, and provides no keyboard-focus separation

**File:** `frontend/components/WatchlistRow.tsx:92-122`
**Issue:** The whole row is now `role="button" tabIndex={0}` with an `onClick`/`onKeyDown` handler (lines 92-101), and it directly contains `removeControl`, an actual `<button>` (line 120). Nesting an interactive control inside another interactive control is an ARIA/HTML anti-pattern: screen readers and keyboard users get two overlapping "buttons" at the same DOM depth, and `Tab` order silently jumps from the row into the remove button with no indication they are related-but-distinct controls. `stopRowSelect` (line 88-90) only stops click/keydown *bubbling* — it does not fix the semantic nesting.
**Fix:** Make only the ticker/price/sparkline region the clickable "select" target (e.g. wrap that inner content in its own `<button>` or apply `role="button"` there), and leave `removeControl` as a sibling at the row's top level, not a descendant of the selectable element:
```tsx
<div className="group flex h-9 items-center border-b border-edge px-2 ...">
  <button type="button" className="flex flex-1 items-center ..." onClick={onSelect} aria-pressed={selected}>
    {/* ticker, price, change%, sparkline */}
  </button>
  <div className="flex w-[60px] items-center justify-end">{removeControl}</div>
</div>
```

### WR-04: `PortfolioHeatmap`'s `Treemap` has no `Tooltip` — small cells expose zero information

**File:** `frontend/components/PortfolioHeatmap.tsx:111-119`
**Issue:** `HeatmapCell` only renders the ticker/P&L text when `width >= 44 && height >= 20` (`showLabel`) and `height >= 38` (`showPnl`) (lines 33-34, 46-55). For any position whose treemap cell falls below that size (a small holding among several larger ones — a very plausible portfolio composition), the cell is a bare colored rectangle: no name, no value, and — unlike `PnLChart`/`DetailChart`, which both wire up `<Tooltip>` — there is no hover/tap affordance to recover that information either. That position becomes effectively unidentifiable in the UI purely from a sizing accident, not user choice, and color remains the *only* signal (fails "don't convey information by color alone" for those cells).
**Fix:** Add a `<Tooltip>` (or a custom `onMouseEnter`/`onFocus` overlay) to the `Treemap` so every cell's ticker/P&L is discoverable regardless of its rendered size:
```tsx
<Treemap data={data} dataKey="marketValue" stroke="none" isAnimationActive={false} content={<HeatmapCell />}>
  <Tooltip
    contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #30363d" }}
    formatter={(value, _name, item) => [`${item.payload.pnlPercent.toFixed(2)}%`, item.payload.name]}
  />
</Treemap>
```

### WR-05: `test_history_on_fresh_database_returns_empty_list_with_200` doesn't actually test emptiness

**File:** `backend/tests/routes/test_portfolio.py:317-323`
**Issue:** `assert body == {"snapshots": []} or ("snapshots" in body and isinstance(body["snapshots"], list))`. The second disjunct is true for essentially any 200 response with a `snapshots` list key, populated or not — and given the `client` fixture's lifespan runs `SnapshotRecorder.start()`, which synchronously records one snapshot at startup (per `snapshot_task.py:34-48`), `body["snapshots"]` is *never actually empty* by the time this test runs. The test's name and first disjunct claim to verify an empty-list response, but the assertion as written passes regardless, silently testing only "the response has the right shape."
**Fix:** Assert what actually happens (at least one row from the startup tick, not literal emptiness), or explicitly stop the recorder / read the true pre-any-write state if "empty" behavior needs its own proof:
```python
def test_history_returns_a_list_shape_with_200(client):
    response = client.get("/api/portfolio/history")
    assert response.status_code == 200
    assert isinstance(response.json()["snapshots"], list)
```

### WR-06: Timing-based `SnapshotRecorder` lifecycle tests are inherently flaky under load

**File:** `backend/tests/db/test_snapshots.py:143-153, 167-180, 183-205`
**Issue:** `test_recorder_writes_more_than_one_row_over_time`, `test_no_rows_appear_after_stop`, and `test_a_failing_iteration_does_not_kill_the_loop` all assert on real wall-clock behavior (`interval=0.05`, `asyncio.sleep(0.2)`/`asyncio.sleep(0.3)`) rather than controlling the clock. On a loaded CI runner or under `pytest -n auto` parallelism, the scheduler may not get the assumed number of loop iterations within the sleep window, producing intermittent, non-deterministic failures unrelated to any real regression — undermining trust in genuine failures from this suite.
**Fix:** Inject a fake clock / use `asyncio` test utilities that let ticks be driven deterministically (e.g. monkeypatch `asyncio.sleep` to a controllable event, or expose a `tick()` method the test calls directly a fixed number of times) instead of asserting on elapsed real time.

## Info

### IN-01: `formatCurrency` is duplicated verbatim across two new components

**File:** `frontend/components/PnLChart.tsx:19-21`, `frontend/components/DetailChart.tsx:6-8`
**Issue:** Both files define an identical `function formatCurrency(value: number): string { return \`$${value.toFixed(2)}\`; }`. Any future change (e.g. locale-aware formatting, thousands separators) requires editing both call sites and risks drift.
**Fix:** Move `formatCurrency` into `frontend/lib/` (e.g. `lib/format.ts`) and import it from both components.

### IN-02: Redundant `float()` re-conversion in `record_portfolio_snapshot`

**File:** `backend/app/db/snapshots.py:44`
**Issue:** `total_value = float(valued["total_value"])` — `value_portfolio()` (in `app/db/portfolio.py`) already returns `total_value` as a Python `float` (`float(total)`), so this re-wrap is a no-op. Harmless, but slightly misleading about what type is actually flowing through.
**Fix:** Drop the redundant `float()` call, or if defensive typing is the intent, note that in a comment.

### IN-03: No test exercises the `MAX_HISTORY_POINTS` (500-row) cap

**File:** `backend/tests/db/test_snapshots.py` (whole file), `backend/app/db/snapshots.py:27,57-82`
**Issue:** The module's docstring explicitly frames `MAX_HISTORY_POINTS = 500` as the mechanism that "keeps GET /api/portfolio/history's response bounded" (T-03-01), but no test inserts more than a handful of rows and asserts `list_snapshots()` returns at most 500, in the correct (most-recent) window, oldest-first. This is a documented, testable acceptance criterion with no coverage.
**Fix:** Add a test that seeds >500 rows directly (bypassing the 30s cadence) and asserts `len(list_snapshots()) == 500` and that the returned window is the *most recent* 500, still oldest-first.

### IN-04: `PnLChart` can issue two near-simultaneous `GET /api/portfolio/history` requests on initial mount

**File:** `frontend/components/PnLChart.tsx:37-62`
**Issue:** The effect's dependency array is `[cashBalance]` (line 62). On mount, the effect fires once with whatever `cashBalance` initial/default value `PortfolioProvider` supplies; when that provider's own fetch resolves and `cashBalance` updates to the real value shortly after, this effect re-runs and fires a second `fetchPortfolioHistory()` call. Both requests are harmless (idempotent GET) and the flagged pattern is not a correctness bug, but it's an avoidable duplicate network call baked into every page load.
**Fix:** Gate the initial load separately from the `cashBalance`-driven refresh, e.g. track a `hasLoadedOnceRef` and only treat subsequent `cashBalance` changes (not the first render) as a trigger for a second fetch — or accept the duplicate call as intentional and note it in the comment.

### IN-05: `aria-pressed` is a semantic mismatch for "this row is the currently-viewed ticker"

**File:** `frontend/components/WatchlistRow.tsx:96`
**Issue:** `aria-pressed={selected}` communicates a toggle-button's on/off state to assistive tech, but the row isn't a toggle — it's one item in a single-selection list (selecting a different ticker deselects the previous one). `aria-pressed` on every row will read confusingly ("AAPL, pressed" / "GOOGL, not pressed") to screen reader users, since nothing was actually "pressed" in the toggle sense.
**Fix:** Use a pattern suited to single-selection lists, e.g. `aria-current="true"` on the selected row, or restructure the watchlist as a proper `role="listbox"`/`role="option"` (with `aria-selected`) pair.

---

_Reviewed: 2026-08-04T01:27:59Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
