---
phase: 03-portfolio-visualization
verified: 2026-08-04T02:00:00Z
status: human_needed
score: 4/4 truths present+wired, 4 behavior-unverified (live browser rendering not exercised)
behavior_unverified: 4
behavior_unverified_items:
  - truth: "User sees a treemap where each held position is a rectangle sized by its portfolio weight and colored green or red by its unrealized P&L"
    test: "Start backend and frontend (both backgrounded), buy two or more different tickers, open the app"
    expected: "PortfolioHeatmap panel shows one rectangle per position, areas visibly proportional to market value, colors matching P&L sign in the positions table beside it, a break-even position rendering neutral grey"
    why_human: "Sizing/color/opacity math is source-verified (Recharts Treemap dataKey=marketValue, the 0.45-1.0 opacity band, the zero-division guard) and grep-verified against the plan's acceptance criteria, but actual proportional rendering and color correctness require a real browser paint — no frontend test framework exists yet to assert on rendered SVG geometry"
  - truth: "User sees a line chart of total portfolio value over time that gains a new point automatically every 30 seconds and immediately after every trade"
    test: "Open the app, watch the Portfolio Value panel for over 30 seconds without trading, then make a trade and watch again"
    expected: "A new point appears roughly every 30 seconds unattended, and an additional point appears within a few seconds of a trade without waiting for the next timer tick"
    why_human: "Both triggers (SnapshotRecorder's 30s loop, the post-trade route call) are unit/integration-tested against the database directly (backend/tests/db/test_snapshots.py, backend/tests/routes/test_portfolio.py), and PnLChart's 15s poll + cashBalance-keyed refetch are source-verified, but the actual live chart redraw over real time requires a live session"
  - truth: "Clicking a ticker in the watchlist loads it into the larger main detail chart, which keeps updating from the live stream"
    test: "Click three different watchlist rows in turn, and tab to a row and press Enter"
    expected: "The detail chart's title and content switch to each selected ticker, the clicked row keeps a sticky yellow left-edge indicator, and the chart keeps extending as the stream ticks"
    why_human: "Selection state wiring, the shared usePriceStream accumulator, and the operable-row semantics are all source-verified and grep-checked, but the actual click-to-redraw interaction and visual sticky indicator require a live browser session"
  - truth: "The P&L chart still shows points recorded before the backend was restarted — portfolio history is durable, not in-memory"
    test: "Let the app run and record a few snapshots, stop the backend process, restart it, reload the page"
    expected: "GET /api/portfolio/history still returns every point recorded before the restart"
    why_human: "Durability itself is proven by backend/tests/db/test_snapshots.py's restart-durability test (writes via one code path, reads via a brand-new independent connect() opened in the test body, not through run_db and not through the writer) — this is the strongest form of automated proof available for this claim. What remains unverified is only the full live process-restart + browser-reload round trip, which is a live-session confirmation of an already-proven mechanism, not an open question about correctness."
---

# Phase 3: Portfolio Visualization Verification Report

**Phase Goal:** A user can read their portfolio's shape and performance at a glance through a position heatmap, a value-over-time chart, and a per-ticker detail chart
**Verified:** 2026-08-04T02:00:00Z
**Status:** human_needed

## Goal Achievement

### Observable Truths

| # | Truth (from ROADMAP success criteria) | Status | Evidence |
|---|-------|--------|----------|
| 1 | Treemap: one rectangle per position, sized by weight, colored by P&L | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `frontend/components/PortfolioHeatmap.tsx`: `dataKey="marketValue"`, positions-only weighting (no cash rectangle, grep-verified `'Cash'` count 0), green/red fill scaled `0.45`-`1.0` by `|pnlPercent|/maxAbsPnlPercent`, exact-zero P&L takes the neutral branch, zero-division guarded (`|| 1`). Reads `PortfolioProvider`/`PriceStreamProvider` context, issues no fetch of its own (grep-verified 0 `fetch(`/`useEffect` occurrences). `npm run build` prerenders it with no SSR crash. Live proportional/color rendering not observed. |
| 2 | P&L line chart gains a point every 30s and immediately after every trade | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `backend/app/snapshot_task.py`'s `SnapshotRecorder` (30s timer, independently tested lifecycle including failure survival) and `backend/app/routes/portfolio.py`'s post-trade `record_portfolio_snapshot()` call (guarded so a snapshot failure never fails the trade) are both proven at the database layer — `backend/tests/routes/test_portfolio.py` proves a successful buy increases the snapshot count by exactly one; `backend/tests/db/test_snapshots.py` proves the timer fires repeatedly and survives a failing iteration. `frontend/components/PnLChart.tsx` polls `GET /api/portfolio/history` every 15s and refetches on `cashBalance` change. Live chart redraw over real time not observed. |
| 3 | Clicking a watchlist ticker loads it into the detail chart, which keeps updating live | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `frontend/components/DetailChart.tsx` reads `usePriceStreamContext().history[ticker]` directly (grep-verified 0 `EventSource`/`fetch(` occurrences — no new connection, no new endpoint). `WatchlistRow.tsx`'s clickable region (`<button onClick={onSelect}>`) and keyboard path drive `selectedTicker` state lifted to `app/page.tsx`. Default-on-load and removal-reconciliation logic verified via grep against `WatchlistPanel.tsx`. Live click-to-redraw interaction and the sticky selected-row indicator not observed. |
| 4 | Portfolio history survives a backend restart | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `backend/tests/db/test_snapshots.py::test_snapshots_survive_a_fresh_independent_connection` writes two snapshots, then reads them back through a brand-new `connect()` opened in the test body itself — not through `run_db()`, not through the writer helper — which is the strongest automated proof of SQLite persistence available without literally restarting a process. `portfolio_snapshots` is a persisted table (WAL + busy_timeout, unchanged schema since Phase 1). Only the full live process-restart + browser-reload round trip is unobserved, not the underlying durability claim. |

**Score:** 4/4 truths present and wired; all 4 flagged as behavior-unverified pending a live browser session (not a gap — the underlying logic and durability for every one is directly verified in source and by automated tests, consistent with Phase 1 and Phase 2's verification pattern).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/db/snapshots.py` | `record_portfolio_snapshot()`/`list_snapshots()`, sole reader/writer of `portfolio_snapshots` | ✓ EXISTS + SUBSTANTIVE | Writes no other table (grep-verified); reuses `get_portfolio_state()`/`value_portfolio()`, no second valuation path |
| `backend/app/snapshot_task.py` | 30s lifespan-managed `SnapshotRecorder` | ✓ EXISTS + SUBSTANTIVE | `start()`/`stop()`/`_tick()`/`_run_loop()` mirror `SimulatorDataSource`'s lifecycle shape; failure-survival and restart-durability both test-covered |
| `backend/app/routes/portfolio.py` (`GET /history`) | `{"snapshots": [...]}` oldest-first, server-bounded, no client input | ✓ EXISTS + SUBSTANTIVE | `MAX_HISTORY_POINTS=500` cap now test-covered (added in review-fix); handler declares no query/path/body parameter |
| `frontend/components/PnLChart.tsx` | Value-over-time chart with loading/empty/error/single-point states | ✓ EXISTS + SUBSTANTIVE | All branches present with UI-SPEC-exact copy; `"use client"` present; builds cleanly |
| `frontend/components/PortfolioHeatmap.tsx` | Treemap with loading/empty/error states, no fetch of its own | ✓ EXISTS + SUBSTANTIVE | Tooltip added in review-fix so every cell is discoverable regardless of size |
| `frontend/components/DetailChart.tsx` | Full-width per-ticker chart driven by the shared SSE accumulator | ✓ EXISTS + SUBSTANTIVE | No new `EventSource`, no new endpoint; flat-baseline placeholder below 2 points |
| `frontend/lib/useSseStream.ts` | `MAX_SPARKLINE_POINTS` raised 60→300, one shared accumulator | ✓ EXISTS + SUBSTANTIVE | Exactly one history ref; serves both the sparkline and the detail chart |
| `frontend/components/WatchlistRow.tsx` | Operable, keyboard-accessible, sticky-indicator row | ✓ EXISTS + SUBSTANTIVE | Restructured in review-fix: clickable region is a sibling `<button>` of the remove control (not a nested interactive element), `aria-current` replaces the originally-implemented `aria-pressed` |

**Artifacts:** 8/8 verified

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `routes/portfolio.py` `POST /trade` | `snapshots.py` | `record_portfolio_snapshot()` after `execute_trade()` succeeds, guarded | ✓ WIRED | Exception-guarded so a snapshot failure never fails the trade response |
| `snapshot_task.py` | `snapshots.py` | 30s loop calls the same writer the route calls | ✓ WIRED | No second valuation path |
| `main.py` lifespan | `SnapshotRecorder` | started after market source, stopped before it on shutdown | ✓ WIRED | `recorder.stop()` precedes `source.stop()` |
| `PnLChart.tsx` | `GET /api/portfolio/history` | `fetchPortfolioHistory()` unwraps `{snapshots}` | ✓ WIRED | Mirrors `fetchWatchlist`'s envelope-unwrap convention |
| `PortfolioHeatmap.tsx` | `PortfolioProvider`/`PriceStreamProvider` | reads shared context, no fetch of its own | ✓ WIRED | Can never disagree with `PositionsTable` |
| `DetailChart.tsx` | `PriceStreamProvider` | reads `history[ticker]` from the one shared accumulator | ✓ WIRED | No second buffer |
| `app/page.tsx` | `WatchlistPanel`/`DetailChart` | lifted `selectedTicker` state, no new context | ✓ WIRED | Both consumers are direct children of `page.tsx` |
| `WatchlistPanel.tsx` | selection default/reconciliation | ref-guarded one-time default; `removeItem` reassigns on removal | ✓ WIRED | No new `useEffect` added (grep-verified: exactly 1 in the file) |

**Wiring:** 8/8 connections verified

## Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|-----------------|
| PORT-06 (30s + post-trade snapshot recording) | ✓ SATISFIED | Both triggers independently test-proven |
| PORT-07 (P&L value-over-time chart) | ✓ SATISFIED | `GET /api/portfolio/history` + `PnLChart` |
| PORT-08 (position heatmap sized/colored by P&L) | ✓ SATISFIED | `PortfolioHeatmap`, positions-only weighting |
| UI-02 (click watchlist ticker → detail chart) | ✓ SATISFIED | `DetailChart` + `WatchlistRow`/`WatchlistPanel` selection wiring |

**Coverage:** 4/4 requirements satisfied (all pending the same live-browser confirmation noted above — none are code-level gaps)

## Anti-Patterns Found

None. No `TODO`, no placeholder returns, no stub components found in the reviewed source. The Phase 3 code review (`03-REVIEW.md`) found 0 Critical, 6 Warning, 5 Info findings — 9 fixed, 2 accepted as documented tradeoffs (both explicitly offered "accept" as a valid disposition in the review itself); see `03-REVIEW-FIX.md`.

**Anti-patterns:** 0 found

## Human Verification Required

All 4 items below stem from the same root cause as Phase 1 and Phase 2: **no live browser session was exercised during this phase's execution**, consistent with this project's established pattern (foreground dev-server starts hang the tool call in this environment; static/automated-test verification is used instead throughout).

### 1. Treemap proportional sizing and P&L coloring
**Test:** Buy two or more different tickers, open the app, compare the Portfolio Heatmap panel against the positions table beside it.
**Expected:** Rectangle areas visibly proportional to market value; colors/opacity match each position's P&L sign and magnitude; a break-even position renders neutral grey; hovering a cell shows its ticker/value/P&L in a tooltip regardless of cell size.
**Why human:** Visual sizing/color rendering requires a real browser paint.

### 2. P&L chart live point accumulation
**Test:** Watch the Portfolio Value panel for over 30 seconds unattended, then make a trade.
**Expected:** A new point appears roughly every 30 seconds on its own, and an additional point appears within a few seconds of the trade.
**Why human:** Live chart redraw over real elapsed time.

### 3. Click-to-select detail chart interaction
**Test:** Click three different watchlist rows in turn; tab to a row and press Enter; click a row's remove control.
**Expected:** The detail chart's title and content switch to each selected ticker; the clicked row keeps a sticky yellow left-edge indicator after the mouse moves away; keyboard selection works identically to a click; removing a ticker never also selects it.
**Why human:** Live interaction, focus behavior, and persistent visual state.

### 4. Full-process restart durability
**Test:** Let a few snapshots record, stop the backend process, restart it, reload the page.
**Expected:** `GET /api/portfolio/history` still returns every point recorded before the restart.
**Why human:** The durability mechanism itself is already proven by an independent-connection test (see truth #4 above); this step is a live confirmation of an already-proven mechanism, included for completeness alongside the other 3 items.

## Gaps Summary

**No gaps found.** Every observable truth is present, wired, requirement-mapped, and free of anti-patterns. Status is `human_needed` rather than `passed` solely because live-browser confirmation of visual/timing/interaction behavior was not performed in this unattended session — this is an honest recording of an unverified-but-implemented state, not a defect. Recommend running `/gsd-verify-work 3` (or a manual pass through the 4 items above) with a real browser session before considering Phase 3 fully closed, but there is no code-level reason to block progress to Phase 4 in the meantime — Phase 4 (AI Copilot) builds on Phase 2's `execute_trade()` contract and Phase 1's price cache, both unaffected by whether Phase 3's charts have been eyeballed yet.

## Verification Metadata

**Verification approach:** Goal-backward (derived from ROADMAP.md Phase 3 success criteria), performed via direct source-code reading and automated test suite runs (not by a fresh subagent — consistent with Phases 1-2's pattern of the orchestrator writing this directly after the code-review-fix pass, given prior sessions' consistent stalls on live-browser verification attempts in this environment).
**Must-haves source:** ROADMAP.md Phase 3 section + all 3 plans' `must_haves` blocks
**Automated checks:** backend `uv run --extra dev pytest -q` → 143/143 passed (run 3x consecutively, 0 flakes), `ruff check` clean; frontend `npm run lint` clean, `npm run build` → static export completes with no prerender error
**Human checks required:** 4 (all live-browser confirmations, none blocking)
**Total verification time:** ~10 min (direct source inspection, no subagent dispatch)

---
*Verified: 2026-08-04T02:00:00Z*
*Verifier: Claude (orchestrator, direct — see Verification Metadata)*
