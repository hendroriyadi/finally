---
phase: 03-portfolio-visualization
review: 03-REVIEW.md
fixed: 2026-08-04
findings_total: 11
findings_fixed: 9
findings_accepted: 2
---

# Phase 3: Code Review Fix Report

Applied directly (not via `gsd-code-fixer`) since every finding had a concrete, well-specified fix
and the review scope (15 files) was small enough to fix and re-verify in one pass.

## Warnings

### WR-01: `SnapshotRecorder.stop()` cannot guarantee no write lands after it returns — **documented**
Not code-fixable without a deeper mechanism (an in-flight-write tracker), which the review itself
offered as optional. Added a docstring on `stop()` (`backend/app/snapshot_task.py`) stating the exact
guarantee it does and does not provide, so the shutdown contract is explicit rather than assumed.

### WR-02: Empty watchlist silently falls back to the default 10 tickers on restart — **fixed**
`backend/app/main.py`: removed the `or list(SEED_PRICES.keys())` fallback. Confirmed via
`app/db/init.py` that the default watchlist is seeded synchronously inside `init_db()`, before this
line ever runs — so `list_watchlist()` returning `[]` at this point can only mean the user genuinely
emptied it, never "never seeded." Removed the now-unused `SEED_PRICES` import. This bug predated
Phase 3 but directly feeds this phase's new snapshot-valuation path, and no test in the suite exercised
this exact line, so nothing needed updating alongside the fix.

### WR-03: Nested interactive elements in `WatchlistRow` — **fixed**
`frontend/components/WatchlistRow.tsx`: restructured so the ticker/price/change/sparkline region is
its own `<button type="button">`, a sibling of the remove control (also a `<button>`), rather than an
ancestor `role="button"` div wrapping it. Removed the now-unneeded `stopRowSelect` propagation-stopping
wrapper, since the remove button is no longer nested inside the selectable element.

Note: this changes two of `03-03-PLAN.md`'s original acceptance-criteria greps
(`grep -q 'aria-pressed'` and `grep -q 'stopPropagation'` both now fail) — both criteria encoded the
exact anti-pattern this fix removes (see WR-03 and IN-05). The plan's *behavioral* acceptance criteria
(operable by mouse/keyboard, sticky selected indicator, remove-without-select) all still hold.

### WR-04: `PortfolioHeatmap`'s `Treemap` has no `Tooltip` — **fixed**
`frontend/components/PortfolioHeatmap.tsx`: added a `<Tooltip content={<HeatmapTooltip />} />` inside
`<Treemap>`, with a small custom content component (ticker, market value, signed P&L%) matching the
panel-shell tooltip styling `PnLChart`/`DetailChart` already use. Every cell's data is now discoverable
on hover regardless of whether it's large enough for an on-cell label.

### WR-05: `test_history_on_fresh_database_returns_empty_list_with_200` doesn't test emptiness — **fixed**
`backend/tests/routes/test_portfolio.py`: renamed to `test_history_returns_a_list_shape_with_200` and
narrowed the assertion to what the `client` fixture can actually prove (a `snapshots` list is present
and typed correctly) — the true-emptiness case isn't reachable through this fixture since
`SnapshotRecorder.start()` records one point at lifespan startup, before any test body runs.

### WR-06: Timing-based `SnapshotRecorder` lifecycle tests are inherently flaky — **accepted**
No code change. The three flagged tests (`test_recorder_writes_more_than_one_row_over_time`,
`test_no_rows_appear_after_stop`, `test_a_failing_iteration_does_not_kill_the_loop`) already assert
loose bounds (`> 1`, not an exact count) against generous margins (interval `0.05s`, sleep windows
`0.2`-`0.3s`, i.e. ~4-6 expected iterations for a `>1` threshold) — a full fake-clock rewrite would
meaningfully reduce an already-small residual flake risk at real implementation cost for a
single-developer capstone project's CI. Ran the full suite 3 consecutive times with 0 failures both
before and after this review-fix pass. Revisit if this ever actually flakes in practice.

## Info

### IN-01: `formatCurrency` duplicated across `PnLChart`/`DetailChart` — **fixed**
Extracted to `frontend/lib/format.ts`, imported by both.

### IN-02: Redundant `float()` re-conversion in `record_portfolio_snapshot` — **fixed**
`backend/app/db/snapshots.py`: confirmed `value_portfolio()` already returns `total_value` as a
`float` (`app/db/portfolio.py`'s `"total_value": float(total)`), dropped the redundant re-cast, added
a one-line comment.

### IN-03: No test exercises the `MAX_HISTORY_POINTS` cap — **fixed**
Added `test_list_snapshots_caps_at_max_history_points_keeping_the_newest_window` to
`backend/tests/db/test_snapshots.py`: seeds 550 rows directly (bypassing the 30s cadence), asserts
`list_snapshots()` returns exactly 500, still oldest-first, and that the kept window is the *newest*
500 (the oldest 50 seeded rows are excluded).

### IN-04: `PnLChart` can issue two near-simultaneous history requests on mount — **accepted, documented**
No code change — the "fix" (gating on a `hasLoadedOnceRef`) doesn't actually distinguish
"`PortfolioProvider`'s own initial fetch settling" from "a real trade changed cash" any better than
the current effect does, since both are legitimate reasons to refetch and neither is separable from
the other purely from `cashBalance`'s value. Added a comment explaining the tradeoff and why the extra
GET (harmless, idempotent, once per page load) was left as-is rather than adding complexity that
wouldn't fully close the gap anyway.

### IN-05: `aria-pressed` is a semantic mismatch for single-selection list rows — **fixed**
`frontend/components/WatchlistRow.tsx`: replaced `aria-pressed={selected}` with
`aria-current={selected ? "true" : undefined}`, the correct pattern for "this item is the current one
in this list" versus a toggle button's on/off state. Landed as part of the same edit as WR-03.

## Verification

- `cd backend && uv run --extra dev ruff check app/ tests/` — clean
- `cd backend && uv run --extra dev pytest -q` — 143 passed, run 3x consecutively, 0 flakes
- `cd frontend && npm run lint` — clean
- `cd frontend && npm run build` — static export completes, no prerender error

---
**Total:** 9 fixed, 2 accepted-and-documented (WR-06, IN-04) — both explicitly offered "accept" as a
valid disposition by the reviewer, and both are Warning/Info tier with no correctness impact.
