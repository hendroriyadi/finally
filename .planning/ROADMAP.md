# Roadmap: FinAlly — AI Trading Workstation

## Overview

FinAlly is built bottom-up on top of an already-complete, frozen market data layer (GBM simulator, Massive/Polygon client, thread-safe `PriceCache`). The journey starts where correctness is hardest to retrofit: a concurrency-safe SQLite store and one atomic, Decimal-precise trade-execution function that every trading path — manual and AI — must call. That engine is then exposed as the backend HTTP surface (portfolio, trades, watchlist, snapshots) plus the live SSE price stream, giving the frontend real contracts to build against instead of guesses. The AI copilot lands next, reusing those validated contracts rather than inventing its own. Only then does the Next.js terminal get built — first the live trading shell (watchlist, flash, sparklines, chart, trade bar, header), then the portfolio visuals and the chat panel with inline action transparency. Finally the whole thing is packaged into the single-container, single-port design and proven end to end with Playwright against a mocked LLM.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Persistence & Trade Engine** - Concurrency-safe SQLite store, lazy init + seed, and the one atomic trade-execution path
- [ ] **Phase 2: Backend API & Live Price Stream** - Portfolio, trade, watchlist, and history endpoints plus SSE wired to the existing price cache
- [ ] **Phase 3: AI Chat Assistant** - Portfolio-aware LLM copilot that executes trades and watchlist changes through the same validated path
- [ ] **Phase 4: Trading Terminal Frontend** - Dark Next.js terminal with live watchlist, flash + sparklines, detail chart, trade bar, and header
- [ ] **Phase 5: Portfolio Visualization & AI Copilot Panel** - Heatmap, P&L chart, docked chat panel with inline action confirmations
- [ ] **Phase 6: Containerized Delivery & E2E Verification** - Single container on port 8000, persistent volume, start/stop scripts, Playwright suite

## Phase Details

### Phase 1: Persistence & Trade Engine
**Goal**: The app has a durable, concurrency-safe SQLite store and exactly one validated trade-execution path that every trading flow must go through
**Depends on**: Nothing (first phase) — builds on the existing, frozen market data layer
**Requirements**: DB-01, DB-02, DB-03, PORT-04, TEST-01
**Success Criteria** (what must be TRUE):
  1. Starting the backend with no database file yields a ready database seeded with a $10,000 cash balance and the 10 default tickers — no manual migration step, no setup command.
  2. Executing a buy debits cash, creates or updates the position with a correct weighted-average cost, and appends a trade record — all in one transaction, or not at all.
  3. A buy exceeding available cash or a sell exceeding held shares is rejected, leaving cash, positions, and trade history exactly as they were.
  4. Two writers hitting the database concurrently (trade + background writer) both complete instead of failing with "database is locked".
  5. `uv run pytest` passes trade-math tests covering fractional shares, exact-balance buys, full-position sells, and insufficient cash/shares.
**Plans**: 4 plans

Plans:
- [ ] 01-01-PLAN.md — Untrack the stale committed database, then drive one end-to-end buy tracer from schema through `execute_trade()` (wave 1)
- [ ] 01-02-PLAN.md — Expand the engine: sell path, rejection paths with zero state change, fractional/exact-balance/drift edge cases (wave 2)
- [ ] 01-03-PLAN.md — Repository access for all six tables, portfolio valuation math, and the database-layer test suite (wave 2)
- [ ] 01-04-PLAN.md — Concurrency proofs for atomicity and WAL contention, plus the phase gate (wave 3)

### Phase 2: Backend API & Live Price Stream
**Goal**: Every trading capability is usable over HTTP, and live prices stream continuously to any connected client
**Depends on**: Phase 1
**Requirements**: STREAM-01, PORT-01, PORT-02, PORT-03, PORT-05, PORT-06, WATCH-01, WATCH-02, WATCH-03
**Success Criteria** (what must be TRUE):
  1. `GET /api/portfolio` returns cash balance, total portfolio value, and every position with quantity, average cost, current price, unrealized P&L, and % change — values that move as cached prices move.
  2. `POST /api/portfolio/trade` fills a market buy or sell instantly at the current cached price with no fees and no confirmation step, and the result is immediately reflected in the next `GET /api/portfolio`.
  3. The watchlist can be read, added to, and removed from — starting from the 10 seeded defaults — and the market data source begins or stops tracking tickers to match.
  4. Connecting to `GET /api/stream/prices` with an `EventSource`-style client yields a continuous stream of price events (ticker, price, previous price, timestamp, direction) at roughly a 500ms cadence.
  5. `GET /api/portfolio/history` returns snapshots that accumulate every 30 seconds and gain an extra point immediately after each trade executes.
**Plans**: TBD

### Phase 3: AI Chat Assistant
**Goal**: A portfolio-aware LLM copilot answers questions and acts on the account through the exact same validated trade path used by manual trading
**Depends on**: Phase 2
**Requirements**: CHAT-01, CHAT-02, CHAT-03, CHAT-04, CHAT-06, CHAT-07, TEST-02
**Success Criteria** (what must be TRUE):
  1. Posting a message to `/api/chat` returns one complete JSON response containing the assistant's conversational message plus any actions it executed.
  2. The assistant's answers reflect the real current cash, positions with P&L, watchlist with live prices, total value, and recent conversation history — not stale or invented figures.
  3. Asking the assistant to buy or sell, or to add or remove a ticker, changes the real portfolio and watchlist, with identical validation to a manual trade.
  4. An AI-initiated trade that cannot be filled (insufficient cash or shares) returns an explanatory chat response rather than a failed request, and leaves no partial state change behind.
  5. With `LLM_MOCK=true` the chat endpoint returns deterministic responses without any OpenRouter call, and malformed or schema-invalid LLM output is rejected without executing anything.
**Plans**: TBD

### Phase 4: Trading Terminal Frontend
**Goal**: Opening the app shows a live dark trading terminal where the user can watch prices stream and place trades
**Depends on**: Phase 2
**Requirements**: UI-01, UI-02, UI-03, UI-05, WATCH-04, WATCH-05, STREAM-02
**Success Criteria** (what must be TRUE):
  1. Loading the app with no login or signup shows a dark, data-dense terminal layout with the watchlist grid, main detail chart, positions table, and trade bar all visible.
  2. Watchlist rows update live from the SSE stream — price flashes green on an uptick and red on a downtick and fades over ~500ms, daily change % updates, and a sparkline fills in progressively from page load.
  3. Clicking a ticker in the watchlist loads that ticker into the larger main detail chart.
  4. The header shows total portfolio value and cash balance updating live, plus a status dot that turns yellow/red when the stream drops and green again once `EventSource` reconnects on its own.
  5. Entering a ticker and quantity in the trade bar and pressing buy or sell fills instantly with no confirmation dialog, and portfolio figures update without a page reload.
**Plans**: TBD
**UI hint**: yes

### Phase 5: Portfolio Visualization & AI Copilot Panel
**Goal**: The user can see their portfolio as live visuals and converse with the AI copilot inside the terminal, with every AI action visible after the fact
**Depends on**: Phase 3, Phase 4
**Requirements**: PORT-07, PORT-08, UI-04, CHAT-05, TEST-03
**Success Criteria** (what must be TRUE):
  1. A heatmap/treemap shows each position as a rectangle sized by portfolio weight and colored green for profit and red for loss, shifting as prices move.
  2. A line chart plots total portfolio value over time from recorded snapshots, gaining new points as time passes and as trades execute.
  3. The AI chat panel docks and collapses, accepts a message, shows a loading indicator while waiting, and appends the reply to a scrolling conversation history.
  4. Trades and watchlist changes performed by the AI appear inline in the transcript as readable confirmation entries, so the user can always see what was done on their behalf.
  5. The frontend component test suite passes for price-flash behavior, watchlist add/remove, portfolio display calculations, and chat message rendering.
**Plans**: TBD
**UI hint**: yes

### Phase 6: Containerized Delivery & E2E Verification
**Goal**: Anyone can run the entire app with one command and the core user journeys are proven end to end
**Depends on**: Phase 5
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03, TEST-04
**Success Criteria** (what must be TRUE):
  1. A single container built from the multi-stage Dockerfile serves both the API and the built static frontend on port 8000.
  2. Stopping the container and starting it again preserves cash, positions, trade history, and chat history from the volume-mounted `db/` directory.
  3. The macOS/Linux and Windows PowerShell start/stop scripts build and run the container, print the URL, and are safe to run repeatedly.
  4. The Playwright suite passes against the running container with `LLM_MOCK=true`, covering fresh start, watchlist add/remove, buy and sell flows, portfolio visualizations, AI chat with trade execution, and SSE reconnection.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Persistence & Trade Engine | 0/4 | Planned | - |
| 2. Backend API & Live Price Stream | 0/TBD | Not started | - |
| 3. AI Chat Assistant | 0/TBD | Not started | - |
| 4. Trading Terminal Frontend | 0/TBD | Not started | - |
| 5. Portfolio Visualization & AI Copilot Panel | 0/TBD | Not started | - |
| 6. Containerized Delivery & E2E Verification | 0/TBD | Not started | - |

---
*Roadmap created: 2026-08-02*
