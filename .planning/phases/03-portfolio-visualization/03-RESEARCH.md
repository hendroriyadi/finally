# Phase 3: Portfolio Visualization - Research

**Researched:** 2026-08-03
**Domain:** FastAPI asyncio background tasks (30s snapshot recorder) + Recharts (Treemap, LineChart) in a Next.js 16 / React 19 static-export frontend
**Confidence:** HIGH (backend task pattern, DB durability) / MEDIUM (Recharts API surface) / LOW (React 19 edge-case risk, unverified until executed)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Snapshot Recording (PORT-06)**
- A background task, started in `backend/app/main.py`'s `lifespan` alongside the existing market-source startup, records a `portfolio_snapshots` row every 30 seconds using the already-built `get_portfolio_state()` + `value_portfolio()` functions from Phase 2 (`backend/app/db/portfolio.py`) — no new valuation logic, just a new writer calling the existing read path on a timer.
- **Immediate post-trade snapshot:** recorded in the trade route (`backend/app/routes/portfolio.py`'s `POST /api/portfolio/trade` handler), right after `execute_trade()` succeeds, using the same `get_portfolio_state()`/`value_portfolio()` pair. `execute_trade()` remains the sole mutator of cash/positions/trades (the CHAT-03 contract Phase 4 depends on, unchanged) and does not also become a `portfolio_snapshots` writer.
- New function: `record_portfolio_snapshot(user_id=DEFAULT_USER_ID)` in `backend/app/db/portfolio.py` (or a new `snapshots.py` — planner's discretion), inserting one row with `total_value` and `recorded_at`.
- `GET /api/portfolio/history` — new route returning snapshots ordered by `recorded_at`, for the P&L chart to consume.
- Durability (success criterion 4 — "history survives a backend restart") is automatic: `portfolio_snapshots` is a persisted SQLite table (existing schema, WAL+busy_timeout already configured), not an in-memory buffer. The 30-second background task is the only thing that needs to restart cleanly on process restart, which it does since it's started fresh in `lifespan` every time.

**Charting Library**
- Introduce `recharts` for the treemap, the P&L line chart, AND the main detail chart (per-ticker price history) — one charting dependency for the whole app, not two.
- The existing hand-rolled inline-SVG `Sparkline` component (Phase 1, watchlist rows) is unchanged — do not replace it.
- Package legitimacy: `recharts` is expected to trip the legitimacy gate's "too-new-publish" heuristic as a false positive (same pattern already resolved in Phase 1). Treat it the same way: verify the registry/repo match, do not block on the recency heuristic.

**Treemap (PORT-08)**
- Rectangle size: portfolio weight = `position_market_value / total_portfolio_value`. Cash-rectangle inclusion was left as Claude's discretion in CONTEXT.md but has since been **resolved by the approved 03-UI-SPEC.md**: positions-only weight, no separate "Cash" rectangle (see UI-SPEC's "populated | treemap" row). Treat this as locked, not open.
- Color: green tint for positive unrealized P&L, red tint for negative — reuse `--color-positive`/`--color-destructive` tokens, no new color scale.
- Data source: reads from the existing `PortfolioProvider` context (positions + live prices), not a separate fetch.
- Empty state: zero positions renders empty-state copy, not a blank panel.

**P&L Chart (PORT-07)**
- Line chart of `total_value` over time from `GET /api/portfolio/history`. Refetch/poll cadence is Claude's discretion (e.g. refetch on mount + after every trade + a light poll, mirroring `PortfolioProvider`'s existing polling pattern).
- Empty state (no snapshots yet): show empty-state copy, not a broken/blank chart.

**Main Detail Chart (UI-02)**
- Clicking a ticker row in the watchlist grid selects it as the "active" ticker for a new, larger detail-chart panel. Requires new shared client state (which ticker is selected) — introduce as a small new context or lift state to a shared parent in `app/page.tsx`. No existing "selected ticker" concept anywhere in the codebase yet.
- The detail chart's price history is accumulated the same way the sparkline's is — from the existing SSE stream since page load (`usePriceStream`'s `historyRef`/`baselinesRef` accumulators, exported from `frontend/lib/useSseStream.ts`) — not a new server-side history endpoint.
- Default selected ticker on first load was left as Claude's discretion in CONTEXT.md but has since been **resolved by the approved 03-UI-SPEC.md**: first watchlist entry (seed order), not "no selection." "No ticker selected" only applies if the watchlist is emptied entirely. Treat this as locked, not open.

### Claude's Discretion (remaining, not resolved by UI-SPEC)
- Exact module/file layout for the new snapshot-recording code (new file vs. extending `backend/app/db/portfolio.py`).
- P&L chart refetch/poll cadence.
- Exact Recharts component composition/props for the treemap and line charts, following Recharts' documented API.
- Whether "selected ticker" state is a new React context or lifted `useState` in `app/page.tsx`.

### Deferred Ideas (OUT OF SCOPE)
- AI chat panel — Phase 4.
- Docker packaging — Phase 5.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PORT-06 | System records a portfolio value snapshot every 30 seconds and immediately after each trade | Backend asyncio-lifespan pattern verified against `SimulatorDataSource`/`MarketDataSource` (§ Architecture Patterns, Pattern 1); route-layer trigger point verified in `backend/app/routes/portfolio.py` |
| PORT-07 | User can view portfolio value over time as a P&L line chart | Recharts `LineChart`/`Area`/`ResponsiveContainer` API (§ Code Examples); new `GET /api/portfolio/history` route pattern mirrors existing `GET /api/portfolio` |
| PORT-08 | User can view a heatmap/treemap of positions sized by portfolio weight and colored by P&L | Recharts `Treemap` `content` render-prop API (§ Code Examples); UI-SPEC's opacity-scaling and neutral-fill rules |
| UI-02 | Clicking a ticker in the watchlist selects it for the main detail chart | Selected-ticker state placement analysis (§ Architecture Patterns, Pattern 3); `usePriceStream`'s existing `historyRef` accumulator as the data source |
</phase_requirements>

## Summary

This phase is architecturally thin but touches three new surfaces at once: a backend timer task, a new persisted-data read endpoint, and the project's first real charting library. None of the three requires inventing a new pattern — each has a direct precedent already in the codebase or in Recharts' own documented composition model.

The backend piece is the most mechanical: `backend/app/main.py`'s `lifespan` already runs exactly the shape needed (`asyncio.create_task` on startup, `task.cancel()` + `await task` swallowing `CancelledError` on shutdown), demonstrated verbatim by `SimulatorDataSource.start()`/`.stop()`/`._run_loop()` in `backend/app/market/simulator.py`. The 30-second snapshot task is a second instance of this exact shape, not a new pattern — a `while True: ... ; await asyncio.sleep(30)` loop with an internal `try/except Exception` (so one failed write doesn't kill the task) calling `get_portfolio_state()` + `value_portfolio()` + a new insert function.

The frontend piece introduces `recharts` (verified: npm registry, `3.10.1`, published 2026-07-25, 54.8M weekly downloads, official `recharts/recharts` repo, no postinstall script, peerDependencies explicitly include `react/react-dom/react-is: ^19.0.0`). The package-legitimacy gate flags it `SUS` on a "too-new" heuristic exactly as CONTEXT.md predicted — this is a false positive to note and move past, not a blocker. Recharts' `Treemap` supports a `content` render-prop that receives the full source data node (spread, so custom fields like `unrealizedPnl` are directly readable) plus computed `x/y/width/height/depth` — this is the correct API for per-cell P&L-driven fill/opacity/labels, more suited to this phase's needs than the simpler `<Cell>` children pattern used for flat per-index coloring. `LineChart`/`AreaChart` composition inside `ResponsiveContainer` is the standard pattern for both new line charts; `<Area>` alone (stroke + fill in one element) is the simplest way to get the UI-SPEC's "line plus 10%-opacity wash" without stacking two elements.

**Primary recommendation:** Mirror `SimulatorDataSource`'s exact task-lifecycle shape for the snapshot recorder; use Recharts' `content` render-prop (not `<Cell>`) for the treemap so P&L-derived opacity/color/labels can be computed per node; lift "selected ticker" to a plain `useState` in `app/page.tsx` (not a new context) since `WatchlistPanel` and the new `DetailChart` are both direct children of `page.tsx` and CONTEXT.md's prop-drilling precedent (`removeControl`) already establishes passing render/callback props down through `WatchlistPanel` → `WatchlistRow`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 30s + post-trade snapshot recording | API / Backend | Database / Storage | Timer lives in the FastAPI process (`lifespan`); the row it writes is the actual durability mechanism (SQLite, not memory) |
| `GET /api/portfolio/history` | API / Backend | Database / Storage | Thin read endpoint over `portfolio_snapshots`, same shape as the existing `GET /api/portfolio` |
| Treemap rendering | Browser / Client | — | Pure client-side render of already-fetched `PortfolioProvider` context state; no new fetch |
| P&L line chart | Browser / Client | API / Backend | Client renders; backend supplies the one new read endpoint it depends on |
| Detail chart + ticker selection | Browser / Client | — | Selection state and SSE-accumulated history are both entirely client-side; no backend involvement (per CONTEXT.md, no new history endpoint for this) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| recharts | `3.10.1` [VERIFIED: npm registry — `npm view recharts version`, `npm view recharts time.modified` = 2026-07-25] | Treemap, LineChart/Area for P&L chart and detail chart | D3-based squarified `Treemap` primitive + declarative line-chart composition from one dependency; 54.8M weekly downloads, official `recharts/recharts` GitHub repo [VERIFIED: npm registry — `npm view recharts repository.url`] |

### Supporting
No new supporting libraries this phase — no date-formatting library needed (a small local formatter over `recorded_at`/`executed_at` ISO strings, matching the existing `formatCurrency`/`formatPercent`/`formatQuantity` pattern in `PositionsTable.tsx`, is sufficient and consistent with the codebase's zero-extra-dependency style).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Recharts | Lightweight Charts (TradingView) | No treemap primitive at all — would force a second charting library just for PORT-08, which CONTEXT.md explicitly rejects ("one charting dependency for the whole app, not two") |
| Recharts' `content` render-prop | `<Cell fill=.../>` per-entry children | `<Cell>` only sets a flat `fill`; it cannot easily express opacity-scaled-by-magnitude + a neutral-vs-signed fill rule + a conditional white-vs-default label color in one place the way a custom `content` renderer can |

**Installation:**
```bash
npm install recharts
```

**Version verification:** `npm view recharts version` → `3.10.1`; `npm view recharts peerDependencies` confirms `react`/`react-dom`/`react-is` all accept `^19.0.0`, matching this project's installed React 19.2.4 [VERIFIED: npm registry — commands run this session; `frontend/package.json:14-15` shows `"react": "19.2.4"`, `"react-dom": "19.2.4"`].

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| recharts | npm | 9 days (published 2026-07-25) [VERIFIED: npm registry — `npm view recharts time.modified`] | 54,869,498/week [VERIFIED: npm registry — `npm view recharts` weeklyDownloads via `package-legitimacy check` seam, cross-checked against `api.npmjs.org/downloads/point/last-week/recharts`] | `github.com/recharts/recharts` [VERIFIED: npm registry — `npm view recharts repository.url`] | SUS (reason: "too-new") | Approved — false positive, same pattern Phase 1 already resolved. No postinstall script [VERIFIED: npm registry — `npm view recharts scripts.postinstall` returned empty]. |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `recharts` — flagged purely on publish recency (a routine patch release, not a new/unknown package: multi-million weekly downloads and an 8+ year old official GitHub org predate this session by years). The planner should still add a lightweight `checkpoint:human-verify` before `npm install recharts` per the legitimacy-gate protocol, but the verification is expected to pass immediately — this is process compliance, not a real risk signal.

## Architecture Patterns

### System Architecture Diagram

```
                     ┌────────────────────────────────────────────┐
                     │  FastAPI process (backend/app/main.py)      │
                     │                                              │
  lifespan startup ─►│  asyncio.create_task(snapshot_loop)          │
                     │       │                                     │
                     │       ▼ every 30s                            │
                     │  get_portfolio_state() ──► value_portfolio() │
                     │       │                                     │
                     │       ▼                                     │
                     │  INSERT INTO portfolio_snapshots  ───────┐   │
                     │                                          │  │
  POST /api/portfolio/trade                                    │  │
       │                                                        │  │
       ▼                                                        │  │
  execute_trade() succeeds                                      │  │
       │                                                        │  │
       ▼                                                        │  │
  get_portfolio_state() ──► value_portfolio() ──► INSERT ───────┘  │
                     │                                              │
  GET /api/portfolio/history                                       │
       │                                                            │
       ▼                                                            │
  SELECT * FROM portfolio_snapshots ORDER BY recorded_at            │
                     └────────────────────────────────────────────┘
                                        │ JSON
                                        ▼
┌───────────────────────────────────────────────────────────────────┐
│  Browser (Next.js static export)                                   │
│                                                                       │
│  PnLChart ──fetch on mount/trade/poll──► /api/portfolio/history      │
│      │                                                                │
│      ▼ renders                                                       │
│  <ResponsiveContainer><LineChart|AreaChart>...</LineChart></...>      │
│                                                                       │
│  Treemap ──reads──► PortfolioProvider context (positions, live price) │
│      │                                                                │
│      ▼ renders                                                       │
│  <ResponsiveContainer><Treemap content={CustomizedContent} /></...>   │
│                                                                       │
│  WatchlistRow (onClick) ──setSelectedTicker──► app/page.tsx useState  │
│      │                                              │                │
│      ▼                                              ▼                │
│  (existing sparkline unaffected)          DetailChart reads          │
│                                            usePriceStream().history[selectedTicker] │
└───────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/app/
├── db/
│   ├── portfolio.py       # existing — get_portfolio_state, value_portfolio, execute_trade
│   └── snapshots.py        # NEW (recommended) — record_portfolio_snapshot(), list_snapshots()
├── routes/
│   └── portfolio.py        # existing router extended with GET /history, OR new snapshots router
└── main.py                 # lifespan extended with a second asyncio.create_task

frontend/
├── components/
│   ├── Treemap.tsx          # NEW — reads PortfolioProvider, recharts <Treemap>
│   ├── PnLChart.tsx         # NEW — fetches /api/portfolio/history, recharts <LineChart>/<AreaChart>
│   └── DetailChart.tsx      # NEW — reads usePriceStreamContext().history[selectedTicker]
├── lib/
│   └── api.ts               # extended with fetchPortfolioHistory()
└── app/
    └── page.tsx              # owns `selectedTicker` state, passes down to WatchlistPanel + DetailChart
```

### Pattern 1: Lifespan-managed periodic background task
**What:** A task created once in `lifespan`'s startup phase, running an infinite `while True` loop with an internal exception guard, cancelled and awaited (swallowing `asyncio.CancelledError`) in the teardown phase.
**When to use:** Any process-lifetime periodic job that must start exactly once per app instance and stop cleanly on shutdown — exactly PORT-06's 30-second snapshot recorder.
**Example — the exact existing pattern to mirror** [VERIFIED: backend/app/market/simulator.py:207-270, quoted verbatim]:
```python
class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache, update_interval: float = 0.5, event_probability: float = 0.001) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._sim = GBMSimulator(tickers=tickers, event_probability=self._event_prob)
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")
        logger.info("Simulator started with %d tickers", len(tickers))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Simulator stopped")

    async def _run_loop(self) -> None:
        while True:
            try:
                if self._sim:
                    prices = self._sim.step()
                    for ticker, price in prices.items():
                        self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
```
And the lifespan wiring that starts/stops it [VERIFIED: backend/app/main.py:33-47, quoted verbatim]:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    source = create_market_data_source(cache)
    watchlist = await list_watchlist()
    tickers = [row["ticker"] for row in watchlist] or list(SEED_PRICES.keys())
    await source.start(tickers)

    app.state.price_cache = cache
    app.state.market_source = source

    yield

    await source.stop()
```
The snapshot task follows this identically: a small object (or a bare `asyncio.create_task`/`asyncio.Task` pair stored on `app.state`) with a `_run_loop` that calls `record_portfolio_snapshot()` then `await asyncio.sleep(30)`, started after `yield`'s preceding lines and stopped with the same cancel-and-await-CancelledError shape after `await source.stop()`.

### Pattern 2: Recharts `Treemap` with a custom `content` render-prop for data-driven per-cell styling
**What:** Instead of `<Cell fill=.../>` children (flat, index-based coloring), pass a `content` prop — a component receiving `{root, depth, x, y, width, height, index, name, ...(all original data fields, spread)}` — that returns raw SVG.
**When to use:** Whenever cell fill/opacity/label depends on computed per-node business data (here: sign and magnitude of `unrealized_pnl`), not just a static palette index.
**Example** [CITED: github.com/recharts/recharts/blob/main/www/src/docs/exampleComponents/TreeMap/CustomContentTreemap.tsx, via Context7 `/recharts/recharts`]:
```typescript
import { Treemap, TreemapNode } from 'recharts';

const CustomizedContent = (props: TreemapNode) => {
  const { x, y, width, height, depth, index, name } = props;
  // `props` also carries every original data field via spread (computeNode
  // preserves custom fields), e.g. props.unrealizedPnl / props.pnlPercent.
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} style={{ fill: /* computed from pnl sign/magnitude */ '#22c55e', stroke: '#1a1a2e', strokeWidth: 2 }} />
      <text x={x + width / 2} y={y + height / 2} textAnchor="middle" fill="#fff" fontSize={12}>{name}</text>
    </g>
  );
};

<Treemap data={data} dataKey="marketValue" stroke="#1a1a2e" content={<CustomizedContent />} />
```
Note: `computeNode` (Recharts source) spreads the source node object into what `content` receives [CITED: github.com/recharts/recharts/blob/main/src/chart/Treemap.tsx, via Context7] — so building each data entry as `{ name: ticker, marketValue, unrealizedPnl, pnlPercent }` makes all four fields directly available inside `CustomizedContent`.

### Pattern 3: Selected-ticker state — lift to `app/page.tsx`, not a new context
**What:** A `useState<string | null>` in `app/page.tsx`, passed down to `WatchlistPanel` (as an `onSelectTicker` callback + `selectedTicker` for the sticky-highlight styling) and to the new `DetailChart` (as the ticker whose `history`/`baselines` to read from `usePriceStreamContext()`).
**When to use:** This case specifically — two sibling subtrees under one shared parent (`page.tsx`), needing exactly one piece of shared, non-deeply-nested state. `WatchlistPanel` already threads a callback-shaped prop one level deeper today (`removeControl` passed into `WatchlistRow` — [VERIFIED: frontend/components/WatchlistPanel.tsx:105, quoted] `removeControl={<RemoveTickerButton ticker={item.ticker} onRemoved={removeItem} />}`), so adding an `onSelect={() => onSelectTicker(item.ticker)}` prop into `WatchlistRow` and a click handler on its root `<div>` ([VERIFIED: frontend/components/WatchlistRow.tsx:66-67, quoted] `<div className="group flex h-9 items-center border-b border-edge px-2 hover:border-l-2 hover:border-l-accent hover:bg-panel">`) is a direct extension of the existing pattern, not a new one.
**Why not a new React Context:** `PriceStreamProvider`/`PortfolioProvider` exist in `layout.tsx` because their consumers (`AppHeader`, which lives in `layout.tsx` outside `{children}`, plus every page-level component) span both `layout.tsx` and `page.tsx`. Selected-ticker's only two consumers (`WatchlistPanel`, `DetailChart`) are both inside `page.tsx`'s own JSX per the UI-SPEC's layout contract — no cross-layout-boundary need exists, so a plain lifted `useState` avoids an unnecessary context for a value with exactly one producer and two same-level consumers.
**Example:**
```tsx
// app/page.tsx
"use client";
import { useState } from "react";
// ...
export default function Home() {
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null); // or first watchlist ticker once loaded, per UI-SPEC
  return (
    <main /* two-column grid per UI-SPEC layout contract */>
      <div>{/* left column: TradeBar, PositionsTable, WatchlistPanel */}
        <WatchlistPanel selectedTicker={selectedTicker} onSelectTicker={setSelectedTicker} />
      </div>
      <div>{/* right column */}
        <DetailChart ticker={selectedTicker} />
        <Treemap />
        <PnLChart />
      </div>
    </main>
  );
}
```

### Anti-Patterns to Avoid
- **Re-fetching portfolio state inside the treemap component:** UI-SPEC and CONTEXT.md both require the treemap to read from the existing `PortfolioProvider` context — a component-local `fetchPortfolio()` call would duplicate `PositionsTable`'s and `PortfolioProvider`'s existing fetch, doubling load and risking a treemap that disagrees with the positions table for one poll interval.
- **Building the snapshot recorder as a second concern inside `execute_trade()`:** CONTEXT.md is explicit that `execute_trade()` stays the sole cash/positions/trades mutator; the post-trade snapshot call belongs in the route handler (`backend/app/routes/portfolio.py`'s `trade()` handler), called after `execute_trade()` returns successfully, not folded into the trade engine's transaction.
- **Introducing a second charting library for the treemap:** already rejected by CONTEXT.md; Recharts' `Treemap` covers it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Squarified treemap layout algorithm | A custom rectangle-packing algorithm | Recharts' `Treemap` (built-in squarify) | Squarified treemap layout is a non-trivial recursive algorithm (aspect-ratio-minimizing partition) that Recharts already implements and tests; re-deriving it is exactly what CONTEXT.md's rationale for picking Recharts already rejects |
| Responsive chart sizing/resize observing | A manual `ResizeObserver` + width/height state | Recharts' `<ResponsiveContainer>` | Handles container resize, debouncing, and re-render scheduling; documented to accept `Treemap`/`LineChart`/`AreaChart` as children |

**Key insight:** This phase's "don't hand-roll" surface is small precisely because CONTEXT.md already made the one consequential build-vs-buy call (adopt Recharts) before research started. The remaining custom code (P&L-color/opacity mapping, snapshot timer, selected-ticker state) is genuinely app-specific business logic with no off-the-shelf equivalent, not a case of reinventing a solved problem.

## Common Pitfalls

### Pitfall 1: Recharts rendered from a Server Component crashes
**What goes wrong:** Importing any Recharts component into a file without `"use client"` throws at build/render time — Recharts requires browser APIs (DOM measurement for `ResponsiveContainer`, SVG refs).
**Why it happens:** Next.js App Router defaults every component to a Server Component; Recharts has no SSR-safe path.
**How to avoid:** Mark every new chart component (`Treemap.tsx`, `PnLChart.tsx`, `DetailChart.tsx`) `"use client"` at the top, exactly like every existing chart-adjacent component in this codebase (`Sparkline.tsx`, `WatchlistRow.tsx`, `PortfolioProvider.tsx` are all already `"use client"`) [CITED: community reports synthesized via WebSearch, LOW confidence — general Recharts/Next.js App Router behavior, not FinAlly-specific].
**Warning signs:** A build-time or first-render error mentioning class-component lifecycle methods, `useLayoutEffect` on the server, or "Cannot read properties of undefined (reading 'getBoundingClientRect')".

### Pitfall 2: Snapshot task silently dies after one failed write
**What goes wrong:** If the periodic loop's body isn't wrapped in `try/except Exception`, a single transient failure (e.g. a locked-database `sqlite3.OperationalError` under WAL contention) propagates out of the loop, the `asyncio.Task` completes with an exception, and no further snapshots are ever recorded — silently, since nothing awaits the task's result.
**Why it happens:** `asyncio.create_task()` fire-and-forget tasks that raise are only surfaced if something calls `.result()`/awaits them or a "Task exception was never retrieved" warning is logged at GC time — easy to miss in normal operation.
**How to avoid:** Mirror `SimulatorDataSource._run_loop`'s exact shape: `try: ... except Exception: logger.exception(...)` inside the `while True`, so one bad iteration logs and the loop continues to the next `asyncio.sleep(30)`.
**Warning signs:** `portfolio_snapshots` row count stops growing after the app has been running a while; `GET /api/portfolio/history` returns a truncated/stale-looking series.

### Pitfall 3: Treemap `dataKey` of zero, negative, or `None` breaks the layout
**What goes wrong:** Recharts' `Treemap` sizing algorithm expects a positive numeric `dataKey` per node; a position whose live price is temporarily unavailable (mirroring `value_portfolio()`'s existing `current_price: None` case [VERIFIED: backend/app/db/portfolio.py:347-359, quoted] `if price is None: total += qty_dec * avg_dec ... positions_out.append({... "current_price": None, "unrealized_pnl": None ...})`) would need a market-value fallback, or the treemap can render a degenerate/zero-size or crashing cell.
**Why it happens:** The treemap's data-shaping step (converting `PortfolioProvider`'s `positions` into `{name, marketValue, unrealizedPnl}` entries) is new code this phase writes; it's easy to pass `current_price * quantity` directly without the same `?? avg_cost` fallback `PositionsTable.tsx` already uses.
**How to avoid:** Reuse the exact fallback chain already established in `PositionsTable.tsx` [VERIFIED: frontend/components/PositionsTable.tsx:85, quoted] `const livePrice = prices[p.ticker]?.price ?? p.current_price ?? null;` — and for the treemap's sizing value specifically, further fall back to `avg_cost` (never `null`/`0`) so every held position always contributes a strictly-positive market value.
**Warning signs:** A treemap cell with zero width/height, a console warning about a non-finite size, or Recharts throwing on a `NaN`/negative `dataKey` value.

### Pitfall 4: Opacity-scaling division has the same zero-range hazard `Sparkline` already guards against
**What goes wrong:** UI-SPEC's "normalize against the largest `|P&L%|` currently held, clamped 45%–100%" rule divides by that largest magnitude; if every held position has exactly 0% P&L (e.g. right after several simultaneous fresh buys), the divisor is 0.
**Why it happens:** New code, not yet guarded — but the exact same shape of bug already has a fixed precedent in this codebase.
**How to avoid:** Mirror `Sparkline.tsx`'s existing guard [VERIFIED: frontend/components/Sparkline.tsx:37, quoted] `const range = max - min || 1;` — i.e. `const maxAbsPnlPercent = Math.max(...pnlPercents.map(Math.abs)) || 1;` before dividing.
**Warning signs:** `NaN` opacity values, cells rendering fully transparent or fully opaque regardless of actual P&L.

### Pitfall 5: Detail chart is bounded to the same ~30-second window as the sparkline
**What goes wrong:** CONTEXT.md mandates reusing `usePriceStream`'s existing `historyRef` accumulator unchanged rather than building a new pipeline. That accumulator truncates every ticker's history to `MAX_SPARKLINE_POINTS = 60` points [VERIFIED: frontend/lib/useSseStream.ts:10-11, quoted] `"Per-ticker sparkline history is capped at this many points so a long-running page tab does not grow memory without bound (T-01-10)." export const MAX_SPARKLINE_POINTS = 60;` — at the ~500ms SSE tick cadence [VERIFIED: backend/app/market/simulator.py:210, quoted] `update_interval: float = 0.5`, that's only ~30 seconds of visible history in the larger detail chart, not the longer trend a "detail" panel implies.
**Why it happens:** The constant was tuned for a small 60x20px inline sparkline, not a full-panel chart; reusing the accumulator verbatim (as CONTEXT.md requires) inherits that tuning.
**How to avoid:** This is a real product tradeoff, not a code bug — flagged in Open Questions below rather than resolved unilaterally, since raising `MAX_SPARKLINE_POINTS` affects the existing sparkline's memory footprint too (a shared constant, not a per-consumer one).
**Warning signs:** User clicks a ticker and sees a chart that appears to reset/flatten every ~30 seconds of session time as old points scroll off, with no way to see anything before the current page load's last 30 seconds regardless of how long the tab has been open.

## Code Examples

### Snapshot recorder function (new, following `execute_trade`'s module conventions)
```python
# Source: pattern synthesized from backend/app/db/portfolio.py's existing
# get_portfolio_state()/value_portfolio() signatures [VERIFIED: read this session]
async def record_portfolio_snapshot(user_id: str = DEFAULT_USER_ID) -> None:
    """Read current state, value it, and insert one portfolio_snapshots row."""
    state = await get_portfolio_state(user_id=user_id)
    # value_portfolio() needs the live price_cache — pass it in from the caller
    # (lifespan task / route handler), since this module has no cache reference
    # of its own (mirrors execute_trade()'s existing price_cache parameter).
```
(Exact signature — whether `price_cache` is a parameter here or the caller pre-computes `value_portfolio()` and only this function does the INSERT — is a planner-level decision; both are consistent with `run_db()`'s existing one-transaction-per-call convention [VERIFIED: backend/app/db/connection.py:59-76].)

### Recharts Treemap + custom content (P&L-driven fill)
```typescript
// Source: Context7 /recharts/recharts — CustomContentTreemap.tsx pattern, adapted
"use client";
import { ResponsiveContainer, Treemap } from "recharts";

function CustomizedContent(props: any) {
  const { x, y, width, height, name, pnlPercent } = props;
  const isNeutral = pnlPercent === 0;
  const magnitude = Math.min(1, Math.abs(pnlPercent) / (props.maxAbsPnlPercent || 1));
  const opacity = 0.45 + magnitude * 0.55; // clamp 45%-100% per UI-SPEC
  const fill = isNeutral ? "var(--color-edge)" : pnlPercent > 0 ? "#22c55e" : "#ef4444";
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={fill} fillOpacity={isNeutral ? 1 : opacity} />
      <text x={x + 4} y={y + 16} fill={isNeutral ? "#e6edf3" : "#ffffff"} fontSize={12} fontWeight={600}>
        {name}
      </text>
    </g>
  );
}

export function Treemap({ entries }: { entries: Array<{ name: string; marketValue: number; pnlPercent: number }> }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <Treemap data={entries} dataKey="marketValue" stroke="#1a1a2e" content={<CustomizedContent />} />
    </ResponsiveContainer>
  );
}
```

### Recharts line chart with area wash (P&L chart / detail chart)
```typescript
// Source: Context7 /recharts/recharts — GettingStarted.mdx + AreaChartExample.tsx patterns, adapted
"use client";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function PnLChart({ data }: { data: Array<{ recorded_at: string; total_value: number }> }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke="#30363d" strokeDasharray="0" vertical={false} />
        <XAxis dataKey="recorded_at" stroke="#8b949e" fontSize={12} />
        <YAxis stroke="#8b949e" fontSize={12} />
        <Tooltip contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #30363d" }} />
        <Area type="monotone" dataKey="total_value" stroke="#209dd7" fill="#209dd7" fillOpacity={0.1} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Recharts `accessibilityLayer` prop required explicitly | `accessibilityLayer` is `true` by default | Recharts 3.0 [CITED: github.com/recharts/recharts storybook Accessibility.mdx, via Context7] | No action needed — installed `3.10.1` already defaults it on |
| Recharts 2.x had incomplete/community-patched React 19 support | Recharts >= 2.15 (and all 3.x) declare React 19 in `peerDependencies` natively | Recharts 2.15 [CITED: community WebSearch synthesis, LOW confidence] | Installed `3.10.1` needs no override/shim for React 19 |

**Deprecated/outdated:** none specific to this phase's surface.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Recharts + React 19 rendering has occasional community-reported blank-chart issues traced to `react-is` version mismatches or a `ResponsiveContainer` production-build `isChart` check | Common Pitfalls (implicit, State of the Art) | If this project hits it, the treemap/line charts could render blank in production builds with no console error — mitigation is straightforward (pin/dedupe `react-is`) but should be verified once components are built, not assumed absent |
| A2 | Lifting selected-ticker state to `app/page.tsx` via plain `useState` (rather than a new React Context) is the better fit for this specific two-consumer case | Architecture Patterns, Pattern 3 | If a third consumer of "selected ticker" emerges later (e.g. Phase 4's chat referencing "the selected ticker"), a context would have been the more future-proof choice — low risk since CONTEXT.md explicitly leaves this decision open and Phase 4 is chat-focused, not detail-chart-focused |
| A3 | A market-value fallback to `avg_cost` (mirroring `value_portfolio()`'s existing None-price handling) is the correct treemap-sizing fallback when a position's live price is temporarily missing | Common Pitfalls, Pitfall 3 | If wrong, a missing-price position could render as a zero-size or crashing treemap cell instead of a degraded-but-visible one |

**If this table is empty:** N/A — see rows above for the claims needing confirmation before being treated as locked.

## Open Questions

1. **Should `MAX_SPARKLINE_POINTS` (currently 60, shared by the sparkline and the new detail chart) be raised for this phase?**
   - What we know: CONTEXT.md requires reusing the existing accumulator without a new pipeline; the constant is currently tuned for a 60x20px inline sparkline and yields only ~30 seconds of history at the ~500ms tick rate.
   - What's unclear: Whether a full-panel "detail chart" reading only 30 seconds of history meets the spirit of UI-02 / PLAN.md's "larger detailed chart" language, or whether raising the shared constant (affecting the sparkline's memory footprint too, still bounded and cheap at this app's ~10-20 ticker scale) is expected within this phase's scope.
   - Recommendation: Flag to the planner as a scope question rather than silently deciding; if raised, the change is a one-line constant edit with no new data-pipeline, so it's low-cost to include in this phase's plan if the planner judges it in-scope for UI-02.

2. **Exact wire shape of `GET /api/portfolio/history`.**
   - What we know: PLAN.md's endpoint table lists it with no query params; `portfolio_snapshots` has `id`, `user_id`, `total_value`, `recorded_at`.
   - What's unclear: Whether the response should be a bare array (`[{total_value, recorded_at}, ...]`, mirroring `GET /api/watchlist`'s `{tickers: [...]}` wrapper-object convention vs. a bare list) — no existing GET-list route in this codebase returns a bare top-level array; `GET /api/watchlist` wraps in `{"tickers": [...]}`.
   - Recommendation: Follow the existing wrapper convention (e.g. `{"snapshots": [...]}`) for consistency with `WatchlistResponse`-style shapes already established, unless the planner has a reason to diverge.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | frontend build/dev (`npm install recharts`, `next dev`/`next build`) | ✓ | v24.18.0 [VERIFIED: `node --version`, run this session] | — |
| npm | package install | ✓ | 11.16.0 [VERIFIED: `npm --version`, run this session] | — |
| Python (via uv) | backend | ✓ | 3.13.3 [VERIFIED: `uv run python --version`, run this session] | — |
| SQLite (CLI, dev convenience only) | manual DB inspection during development | ✓ | 3.51.0 [VERIFIED: `sqlite3 --version`, run this session] | Not required at runtime — the app uses Python's stdlib `sqlite3` module, not the CLI |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none — all required tooling is present.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 (backend, existing) [VERIFIED: `backend/tests/__pycache__/*.pyc` filename tags `cpython-313-pytest-9.0.2`]; no frontend test framework installed yet [VERIFIED: `frontend/package.json` has no test script/dependency] |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`, `asyncio_mode = "auto"`) [VERIFIED: backend/pyproject.toml, read this session, quoted section names] |
| Quick run command | `cd backend && uv run --extra dev pytest tests/db/test_portfolio.py tests/routes/test_portfolio.py -x` |
| Full suite command | `cd backend && uv run --extra dev pytest -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PORT-06 | `record_portfolio_snapshot()` inserts a row with correct `total_value`/`recorded_at` | unit | `uv run --extra dev pytest tests/db/test_portfolio.py -k snapshot -x` | ❌ Wave 0 — new test file/cases needed |
| PORT-06 | Snapshot task fires every 30s and survives a failed iteration (mirrors `SimulatorDataSource` test pattern) | unit | `uv run --extra dev pytest tests/market/test_simulator_source.py -k lifecycle -x` (as a pattern reference) — new equivalent test needed for the snapshot task | ❌ Wave 0 |
| PORT-06 | Trade route triggers an immediate post-trade snapshot | integration | `uv run --extra dev pytest tests/routes/test_portfolio.py -k snapshot -x` | ❌ Wave 0 |
| PORT-06 | Snapshots survive a "restart" (reopen a fresh `connect()`) | integration | New test: insert via one `run_db()` call, assert visible via a second, independent `connect()` | ❌ Wave 0 |
| PORT-07 | `GET /api/portfolio/history` returns snapshots ordered by `recorded_at` | integration | `uv run --extra dev pytest tests/routes/test_portfolio.py -k history -x` | ❌ Wave 0 |
| PORT-08 | Treemap sizing/coloring math (weight calc, opacity clamp, neutral-fill threshold) | unit (frontend) | No frontend test framework installed yet — manual/browser verification only unless one is added | ❌ Wave 0 — frontend test framework gap predates this phase (TEST-03 is scoped to Phase 5 per REQUIREMENTS.md traceability) |
| UI-02 | Clicking a watchlist row updates `selectedTicker` and `DetailChart`'s rendered ticker | frontend/E2E | No frontend test framework installed yet; Playwright E2E is Phase 5's TEST-04 | ❌ Deferred to Phase 5 per existing project-wide test-strategy split (see REQUIREMENTS.md TEST-03/TEST-04 phase mapping) |

### Sampling Rate
- **Per task commit:** `cd backend && uv run --extra dev pytest tests/db/test_portfolio.py tests/routes/test_portfolio.py -x`
- **Per wave merge:** `cd backend && uv run --extra dev pytest -v`
- **Phase gate:** Full backend suite green before `/gsd-verify-work`; frontend visual/interaction checks remain `human_needed` per this project's established Phase 1/2 pattern (STATE.md documents both prior phases deferred live-browser verification the same way) — expect Phase 3 to do the same for the treemap/chart visuals and click-selection UX.

### Wave 0 Gaps
- [ ] `backend/tests/db/test_snapshots.py` (or extend `tests/db/test_portfolio.py`) — covers PORT-06's `record_portfolio_snapshot()`
- [ ] `backend/tests/routes/test_portfolio.py` extension — covers PORT-06's post-trade trigger and PORT-07's `GET /api/portfolio/history`
- [ ] No frontend test framework exists yet for PORT-08/UI-02 component-level assertions — this gap is pre-existing (not introduced by this phase) and tracked project-wide under TEST-03 (Phase 5)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Single-user, hardcoded `user_id="default"` — unchanged, out of scope per project-wide decision |
| V3 Session Management | No | No sessions — unchanged |
| V4 Access Control | No | No access-control surface added — the new endpoint reads the same single-user's data as every other endpoint |
| V5 Input Validation | Marginal | `GET /api/portfolio/history` takes no request body/query params in PLAN.md's spec — if the planner adds any (e.g. a `limit`/`since` query param), it must go through a Pydantic-validated model exactly like `TradeRequest`, not a raw `request.query_params` read |
| V6 Cryptography | No | No new cryptographic surface |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unbounded `portfolio_snapshots` growth (a 30s timer running indefinitely) | Denial of Service (resource exhaustion) | Not a near-term concern at this app's single-user/demo scale (2,880 rows/day), but the planner may note it as a known non-issue rather than leave it unconsidered; no action required this phase |
| Snapshot task writing stale/incorrect data if `value_portfolio()`'s price-cache dependency is momentarily empty (e.g. immediately at process startup, before the market source seeds prices) | Tampering (data integrity, not malicious) | `value_portfolio()` already handles a missing price via its `current_price: None` fallback path [VERIFIED: backend/app/db/portfolio.py:347-359] — the snapshot writer inherits this safety for free by calling the same function, no new guard needed |

## Sources

### Primary (HIGH confidence)
- `backend/app/main.py`, `backend/app/market/simulator.py`, `backend/app/market/interface.py` — read directly this session, asyncio lifespan/task pattern
- `backend/app/db/portfolio.py`, `backend/app/db/connection.py`, `backend/app/db/schema.sql` — read directly this session, existing valuation/DB-access functions and `portfolio_snapshots` schema
- `frontend/lib/useSseStream.ts`, `frontend/components/{PortfolioProvider,PriceStreamProvider,WatchlistRow,WatchlistPanel,PositionsTable,Sparkline}.tsx`, `frontend/app/{layout,page}.tsx` — read directly this session
- `npm view recharts version/time.modified/repository.url/scripts.postinstall/peerDependencies` — run this session
- `gsd_run query package-legitimacy check --ecosystem npm recharts` — run this session

### Secondary (MEDIUM confidence)
- Context7 `/recharts/recharts` — Treemap `content` render-prop, `computeNode` field-spread behavior, LineChart/AreaChart/ResponsiveContainer composition, `accessibilityLayer` default-true in Recharts 3.0

### Tertiary (LOW confidence)
- WebSearch: Recharts + React 19 compatibility reports (`recharts/recharts` issues #6857, #5173, #4558) — general community reports, not reproduced against this project's exact dependency graph
- WebSearch: Recharts + Next.js App Router "use client" requirement — general Recharts/Next.js guidance, not FinAlly-specific

## Metadata

**Confidence breakdown:**
- Standard stack (recharts version/legitimacy): HIGH — verified directly against the npm registry this session
- Architecture (backend task pattern): HIGH — read verbatim from this codebase's own existing, shipped `SimulatorDataSource` implementation
- Architecture (Recharts composition): MEDIUM — Context7-sourced from Recharts' own repo/docs, not independently executed against this project's exact `3.10.1` install this session
- Pitfalls: MEDIUM/LOW — the codebase-grounded pitfalls (zero-division, price-fallback, task-exception-swallowing) are HIGH since they mirror already-shipped code; the React-19/Recharts interaction risk is LOW, community-sourced only

**Research date:** 2026-08-03
**Valid until:** 2026-09-02 (30 days — recharts is a fast-moving-ish but stable-API library; re-verify the installed version/peerDeps if this phase's execution is delayed past that window)
