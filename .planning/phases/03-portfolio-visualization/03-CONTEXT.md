# Phase 3: Portfolio Visualization - Context

**Gathered:** 2026-08-03
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run — grey areas resolved directly from PLAN.md/REQUIREMENTS.md/codebase state rather than interactive discussion, per explicit user direction to build the full project without interactive check-ins)

<domain>
## Phase Boundary

This phase delivers portfolio legibility: a treemap heatmap of positions, a P&L-over-time line chart backed by durable snapshots, and a main detail chart that shows a clicked watchlist ticker's live price history. It is the first writer to `portfolio_snapshots` (schema already exists since Phase 1, unwritten until now) and introduces the project's first real charting library.

Out of scope: trading (Phase 2, already built), AI chat (Phase 4), Docker packaging (Phase 5).

</domain>

<decisions>
## Implementation Decisions

### Snapshot Recording (PORT-06)
- A background task, started in `backend/app/main.py`'s `lifespan` alongside the existing market-source startup, records a `portfolio_snapshots` row every 30 seconds using the already-built `get_portfolio_state()` + `value_portfolio()` functions from Phase 2 (`backend/app/db/portfolio.py`) — no new valuation logic, just a new writer calling the existing read path on a timer.
- **Immediate post-trade snapshot:** recorded in the trade route (`backend/app/routes/portfolio.py`'s `POST /api/portfolio/trade` handler), right after `execute_trade()` succeeds, using the same `get_portfolio_state()`/`value_portfolio()` pair. This is a deliberate separation of concerns: `execute_trade()` remains the sole mutator of cash/positions/trades (the CHAT-03 contract Phase 4 depends on, unchanged) and does not also become a `portfolio_snapshots` writer — snapshot recording is triggered by the route layer, not baked into the trade engine itself.
- New function: `record_portfolio_snapshot(user_id=DEFAULT_USER_ID)` in `backend/app/db/portfolio.py` (or a new `snapshots.py` — planner's discretion), inserting one row with `total_value` and `recorded_at`.
- `GET /api/portfolio/history` — new route returning snapshots ordered by `recorded_at`, for the P&L chart to consume.
- Durability (success criterion 4 — "history survives a backend restart") is automatic: `portfolio_snapshots` is a persisted SQLite table (existing schema, WAL+busy_timeout already configured), not an in-memory buffer. The 30-second background task is the only thing that needs to restart cleanly on process restart, which it does since it's started fresh in `lifespan` every time.

### Charting Library (new dependency this phase)
- **Introduce `recharts`** for the treemap and the P&L line chart. PLAN.md §10 names "Lightweight Charts or Recharts" as the recommended options; Recharts has a native `Treemap` component (D3-based squarified layout under the hood), which a hand-rolled implementation would otherwise require re-deriving — Lightweight Charts (TradingView's library) is time-series/candlestick-focused and has no treemap primitive, so Recharts is the correct pick specifically because this phase needs both a treemap AND a line chart from one library.
- The **main detail chart** (per-ticker price history, success criterion 3) also uses Recharts' `LineChart`, for consistency — one charting dependency for the whole app, not two.
- The existing hand-rolled inline-SVG `Sparkline` component (Phase 1, watchlist rows) is **unchanged** — it's intentionally lightweight for a small, per-row indicator and does not need Recharts' features; do not replace it.
- Package legitimacy: `recharts` is an extremely popular (multi-million weekly downloads), long-established, official-repo (`recharts/recharts`) package — expect a "too-new-publish" false-positive SUS flag from the legitimacy gate on its latest patch version, same pattern already established and resolved in Phase 1's research/`01-02-PLAN.md` for the initial frontend dependency set. Treat it the same way: verify the registry/repo match, do not block on the recency heuristic.

### Treemap (PORT-08)
- Rectangle size: portfolio weight = `position_market_value / total_portfolio_value` (cash is excluded from the weight denominator's rectangles — cash has no position to render as a rectangle, but should arguably still factor into what "100% of the treemap" represents; **Claude's discretion**: either size rectangles purely relative to each other (positions-only, most common treemap-for-portfolio pattern) or include an explicit "Cash" rectangle — PLAN.md doesn't specify, and either is a defensible reading of "sized by portfolio weight").
- Color: green tint for positive unrealized P&L, red tint for negative — reuse the existing `--color-positive`/`--color-destructive` tokens, do not introduce a new color scale.
- Data source: reads from the same `PortfolioProvider` context Phase 2 built (positions + live prices), not a separate fetch — the treemap is a new *view* of already-live-updating portfolio state, not a new data pipeline.
- Empty state: zero positions renders empty-state copy (mirroring the watchlist/positions-table precedent), not a blank panel.

### P&L Chart (PORT-07)
- Line chart of `total_value` over time from `GET /api/portfolio/history`. Given the 30-second recording interval, a reasonable refetch/poll cadence for the chart itself is Claude's discretion (e.g. refetch on mount + after every trade + a light poll, mirroring `PortfolioProvider`'s existing polling pattern from Phase 2) — no need to invent a new streaming mechanism for a 30-second-granularity value.
- Empty state (no snapshots yet, e.g. immediately after a fresh install before 30 seconds have elapsed and before any trade): show empty-state copy, not a broken/blank chart.

### Main Detail Chart (UI-02)
- Clicking a ticker row in the watchlist grid (Phase 1's `WatchlistPanel`/`WatchlistRow`) selects it as the "active" ticker for a new, larger detail-chart panel. This requires a new piece of shared client state (which ticker is selected) — introduce it as a small new context or lift state to a shared parent in `app/page.tsx`, whichever the planner finds cleaner; there is no existing "selected ticker" concept anywhere in the codebase yet.
- The detail chart's price history is accumulated the same way the sparkline's is — from the existing SSE stream since page load (`useSseStream`'s `historyRef`/`baselinesRef` accumulators already exist per-ticker) — not a new server-side history endpoint. Reuse this existing accumulation; do not duplicate it.
- Default selected ticker on first load: Claude's discretion (e.g. the first watchlist ticker, or no selection with a placeholder prompt) — PLAN.md doesn't specify.

### Claude's Discretion
- Exact module/file layout for the new snapshot-recording code (new file vs. extending `backend/app/db/portfolio.py`).
- Whether the treemap includes an explicit "Cash" rectangle.
- P&L chart refetch/poll cadence.
- Default main-detail-chart selection state on first load.
- Exact Recharts component composition/props for the treemap and line charts, following Recharts' documented API.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/db/portfolio.py` — `get_portfolio_state()`, `value_portfolio()` (Phase 2) — this phase's snapshot writer calls these, does not reimplement valuation.
- `backend/app/db/connection.py` — `run_db()` — same seam every DB write in this codebase uses.
- `frontend/components/PortfolioProvider.tsx` (Phase 2) — already fetches positions/cash and derives live total value from the SSE price stream; the treemap and header both should read from this shared context rather than each fetching independently.
- `frontend/lib/useSseStream.ts` — `historyRef`/`baselinesRef` per-ticker accumulation — the main detail chart's data source.
- `frontend/components/Sparkline.tsx` — existing hand-rolled chart, left unchanged; not the pattern to follow for the treemap/P&L/detail charts (those use the new Recharts dependency instead).

### Established Patterns
- `from __future__ import annotations`, full type hints, `snake_case`/`PascalCase`, module-level `logger`, prose docstrings, `asyncio.to_thread()` via `run_db()` for all blocking I/O.
- Background-task-in-lifespan pattern already established for the market data source (`backend/app/main.py`'s `lifespan`) — the 30-second snapshot task follows the same shape (start on startup, stop on shutdown).
- Non-optimistic frontend mutations, in-flight disable, WR-06-style non-`ApiError` error handling — apply to any new mutating UI this phase introduces (unlikely to be much, since this phase is read-only visualization).

### Integration Points
- New `GET /api/portfolio/history` route mounts on the existing `create_portfolio_router()` (Phase 2) or a new router — planner's call.
- Frontend: new components (Treemap/Heatmap, PnLChart, DetailChart) render on `app/page.tsx` alongside the existing `TradeBar`/`PositionsTable`/`WatchlistPanel`.

</code_context>

<specifics>
## Specific Ideas

- The 30-second snapshot interval and the "immediately after each trade" trigger are both explicit requirements (PORT-06) — do not merge them into a single mechanism (e.g. don't skip the timer-based snapshot just because trades also trigger one; both must independently fire).
- Success criterion 4 ("history survives a backend restart") is really a statement about SQLite persistence, already guaranteed by the existing schema/connection layer — the planner should verify this with a test that inserts snapshots, "restarts" (re-opens a connection), and confirms the rows are still there, rather than treating it as a new mechanism to build.

</specifics>

<deferred>
## Deferred Ideas

- AI chat panel — Phase 4.
- Docker packaging — Phase 5.

</deferred>
