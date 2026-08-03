# Roadmap: FinAlly — AI Trading Workstation

## Overview

FinAlly starts from an already-built, frozen market data layer (GBM simulator, optional Massive REST client, thread-safe `PriceCache`) and builds the rest of the workstation outward in vertical slices. Each phase ends with something a person can open in a browser and use: first a live-streaming watchlist terminal, then real buying and selling with a live portfolio, then the visualizations that make the portfolio legible, then the AI copilot that analyzes and trades on the user's behalf, and finally the single-command Docker container with the full automated test suite behind it. The build order respects the hard technical dependencies research identified — SQLite (WAL) before anything persists, and the shared `execute_trade()` service before either the trade bar or the LLM can call it — but each slice bundles database, service, route, and UI together so nothing is a dead technical layer waiting on a later phase to become visible.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Live Market Terminal** - Dark terminal UI with a persistent, editable watchlist streaming live prices over SSE
- [ ] **Phase 2: Manual Trading** - Buy and sell at live prices with instant, atomically-validated fills and a live positions table
- [ ] **Phase 3: Portfolio Visualization** - Heatmap, P&L-over-time chart, and per-ticker detail chart over the working portfolio
- [ ] **Phase 4: AI Copilot** - Portfolio-aware chat assistant that executes trades and watchlist changes through the same validated path
- [ ] **Phase 5: One-Command Ship** - Single Docker container on port 8000, persistent volume, start/stop scripts, and the full test suite

## Phase Details

### Phase 1: Live Market Terminal

**Goal**: A user opens one URL with no login and watches a live, editable watchlist stream real prices in a dark trading-terminal UI
**Mode:** mvp
**Depends on**: Nothing (builds on the existing, frozen market data layer — `PriceCache`, simulator, Massive client)
**Requirements**: DB-01, DB-02, DB-03, STREAM-01, STREAM-02, WATCH-01, WATCH-02, WATCH-03, WATCH-04, WATCH-05, UI-01
**Success Criteria** (what must be TRUE):

  1. User opens the app at a single URL with no login or signup and sees a dark, data-dense terminal layout listing the 10 default tickers (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX)
  2. Prices in the grid update live from the SSE stream, flashing green on an uptick and red on a downtick, fading out within about 500ms
  3. Each watchlist row shows daily change % and a sparkline that fills in progressively from prices received since page load
  4. User can add and remove tickers; the change survives a page refresh and a backend restart, and a newly added ticker starts streaming prices
  5. If the price stream drops, prices resume on their own without a manual refresh

**Plans**: 4/4 plans executed

Plans:

- [x] 01-01-PLAN.md — Backend skeleton: repo hygiene, WAL SQLite lazy-init, FastAPI app, watchlist REST + SSE mounted (wave 1)
- [x] 01-02-PLAN.md — Next.js static-export scaffold, Tailwind v4 dark shell, watchlist grid from the API (wave 2)
- [x] 01-03-PLAN.md — Live SSE stream: price flash, session change %, sparklines, connection-status dot (wave 3)
- [x] 01-04-PLAN.md — Editable watchlist: add-ticker form and per-row remove control with full state coverage (wave 4)

**UI hint**: yes
**Walking skeleton**: `01-SKELETON.md`

### Phase 2: Manual Trading

**Goal**: A user can buy and sell shares at live prices and watch cash, positions, and total portfolio value update instantly
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: PORT-01, PORT-02, PORT-03, PORT-04, PORT-05, UI-03, UI-05, TEST-01
**Success Criteria** (what must be TRUE):

  1. User types a ticker and quantity into the trade bar and clicks Buy — the order fills instantly at the current price with no confirmation dialog and no fees, and cash decreases by exactly quantity × price
  2. User clicks Sell — the position shrinks or disappears and cash increases by exactly the proceeds, including for fractional share quantities
  3. The positions table shows ticker, quantity, avg cost, current price, unrealized P&L, and % change, with current price and P&L updating live as the stream ticks
  4. The header shows total portfolio value and cash balance updating live, alongside a connection-status dot (green connected / yellow reconnecting / red disconnected)
  5. Buying beyond available cash or selling more shares than owned is rejected with a clear message and leaves cash and positions exactly unchanged, even under concurrent requests

**Plans**: 4/4 plans executed

Plans:

- [x] 02-01-PLAN.md — Trade engine and portfolio API: atomic buy/sell, position upsert, trade log, valued read (wave 1)
- [x] 02-02-PLAN.md — TEST-01 proof suite: money math, state integrity, and concurrent-trade race safety (wave 2)
- [x] 02-03-PLAN.md — Shared portfolio state and the trade bar: buy and sell from the browser (wave 2)
- [x] 02-04-PLAN.md — Positions table and live header: portfolio value and cash ticking with the stream (wave 3)

**UI hint**: yes

### Phase 3: Portfolio Visualization

**Goal**: A user can read their portfolio's shape and performance at a glance through a position heatmap, a value-over-time chart, and a per-ticker detail chart
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: PORT-06, PORT-07, PORT-08, UI-02
**Success Criteria** (what must be TRUE):

  1. User sees a treemap where each held position is a rectangle sized by its portfolio weight and colored green or red by its unrealized P&L
  2. User sees a line chart of total portfolio value over time that gains a new point automatically every 30 seconds and immediately after every trade
  3. Clicking a ticker in the watchlist loads it into the larger main detail chart, which keeps updating from the live stream
  4. The P&L chart still shows points recorded before the backend was restarted — portfolio history is durable, not in-memory

**Plans**: TBD
**UI hint**: yes

### Phase 4: AI Copilot

**Goal**: A user can converse with a portfolio-aware AI assistant that analyzes their holdings and executes trades and watchlist changes on their behalf
**Mode:** mvp
**Depends on**: Phase 2 (requires the shared `execute_trade()` service and watchlist service); Phase 3 recommended first so the full dashboard reacts visibly to AI actions
**Requirements**: CHAT-01, CHAT-02, CHAT-03, CHAT-04, CHAT-05, CHAT-06, CHAT-07, UI-04, TEST-02
**Success Criteria** (what must be TRUE):

  1. User opens a docked, collapsible chat panel, sends a message, sees a loading indicator while waiting, and receives a reply; the conversation scrolls and survives a page refresh
  2. Asking about the portfolio produces a reply grounded in the user's actual cash, positions, P&L, and watchlist prices, and follow-up questions retain the earlier conversation
  3. Telling the assistant to buy or sell executes the trade through the exact same validated function the trade bar uses — cash, positions, header value, and charts all update — and the chat shows an inline confirmation of what was executed
  4. Asking the assistant to add or remove a watchlist ticker updates the watchlist grid and shows that change inline in the chat transcript
  5. An impossible or malformed AI action (insufficient cash, unparseable model output) produces a graceful explanation in the chat instead of a crash or an unvalidated trade, and running with `LLM_MOCK=true` returns deterministic replies without calling OpenRouter

**Plans**: TBD
**UI hint**: yes

### Phase 5: One-Command Ship

**Goal**: Anyone can run the entire workstation with a single command, keep their data across restarts, and trust it through an automated test suite
**Mode:** mvp
**Depends on**: Phases 1-4
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):

  1. One start script builds and runs a single Docker container; browsing to `http://localhost:8000` serves the complete app — static frontend and API — from that one port
  2. Stopping the container and starting it again preserves cash, positions, trade history, watchlist, and chat history through the volume-mounted `db/` directory
  3. Start and stop scripts exist for macOS/Linux and Windows PowerShell and are safe to run repeatedly without manual cleanup
  4. Frontend component tests pass, covering price flash animation, watchlist CRUD, portfolio display calculations, and chat message rendering
  5. The Playwright E2E suite passes against the running container with `LLM_MOCK=true`, covering fresh start, watchlist add/remove, buy/sell, portfolio visualizations, AI chat trade execution, and SSE reconnection

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Live Market Terminal | 4/4 | In Progress|  |
| 2. Manual Trading | 4/4 | In Progress|  |
| 3. Portfolio Visualization | 0/TBD | Not started | - |
| 4. AI Copilot | 0/TBD | Not started | - |
| 5. One-Command Ship | 0/TBD | Not started | - |

## Notes

**Frozen dependency:** the market data subsystem (`backend/app/market/`) is already built and tested. All phases read from `PriceCache` rather than re-implementing price fetching. See `.planning/codebase/ARCHITECTURE.md`.

**Research flags carried into planning** (from `.planning/research/SUMMARY.md`):

- Phase 1 — define exact SSE reconnect semantics (gap indication, backfill or not) during planning; establish SQLite WAL + `busy_timeout` from the first commit, not retroactively
- Phase 2 — highest-risk phase: money math precision (Decimal vs float, and exactly where conversion happens at the DB boundary) and atomic check-then-deduct via a single conditional `UPDATE`
- Phase 3 — prototype the Recharts Treemap with 10-15 realistic positions before committing to the heatmap layout
- Phase 4 — validate the LiteLLM + OpenRouter + `openrouter/openai/gpt-oss-120b` + Cerebras structured-output combination end-to-end (per the project's `cerebras` skill) before building on it; decide chat context window size
- Phase 5 — decide FastAPI native SPA serving vs. `StaticFiles` + catch-all, and whether to bump FastAPI from the pinned 0.128.7
