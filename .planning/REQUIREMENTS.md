# Requirements: FinAlly — AI Trading Workstation

**Defined:** 2026-08-01
**Core Value:** A user opens one URL and, with zero setup, sees live-streaming prices, can place trades, and can chat with an AI copilot that actually analyzes their portfolio and executes trades for them.

## v1 Requirements

Requirements for initial release. Scope is `planning/PLAN.md` in full — the market data layer (Validated in PROJECT.md) is excluded here since it's already built; everything below is new work for this milestone.

### Database

- [ ] **DB-01**: System persists user cash balance, watchlist, positions, trades, portfolio snapshots, and chat history in SQLite
- [ ] **DB-02**: Database schema and seed data are lazily initialized on startup if missing (no manual migration step)
- [ ] **DB-03**: SQLite runs in WAL mode with `busy_timeout` set to support safe concurrent writers (trade endpoint, chat endpoint, snapshot background task)

### Streaming

- [ ] **STREAM-01**: User's browser receives live price updates via SSE at `/api/stream/prices`, sourced from the existing price cache
- [ ] **STREAM-02**: Frontend auto-reconnects on SSE disconnect using `EventSource`'s native retry behavior

### Portfolio

- [ ] **PORT-01**: User can view current positions with ticker, quantity, avg cost, current price, unrealized P&L, and % change
- [ ] **PORT-02**: User can execute a market buy order (instant fill at current price, no fees, no confirmation dialog)
- [ ] **PORT-03**: User can execute a market sell order (instant fill, no fees, no confirmation dialog)
- [ ] **PORT-04**: Trade execution validates sufficient cash (buy) or sufficient shares (sell) atomically before committing, preventing check-then-deduct races
- [ ] **PORT-05**: User can view total portfolio value and cash balance, updating live
- [ ] **PORT-06**: System records a portfolio value snapshot every 30 seconds and immediately after each trade
- [ ] **PORT-07**: User can view portfolio value over time as a P&L line chart
- [ ] **PORT-08**: User can view a heatmap/treemap of positions sized by portfolio weight and colored by P&L

### Watchlist

- [ ] **WATCH-01**: User sees a default watchlist of 10 tickers (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX) on first launch
- [ ] **WATCH-02**: User can add a ticker to the watchlist
- [ ] **WATCH-03**: User can remove a ticker from the watchlist
- [ ] **WATCH-04**: Watchlist grid shows live price, daily change %, and a sparkline mini-chart accumulated from the SSE stream since page load
- [ ] **WATCH-05**: Price changes trigger a brief green/red flash animation that fades over ~500ms

### Chat / AI Assistant

- [ ] **CHAT-01**: User can send a chat message and receive a complete structured JSON response (message + executed actions)
- [ ] **CHAT-02**: AI assistant receives current portfolio context (cash, positions w/ P&L, watchlist w/ live prices, total value) and recent conversation history on each turn
- [ ] **CHAT-03**: AI assistant can execute trades on the user's behalf, routed through the exact same validated trade-execution function used by manual trades — never a separate, less-validated path
- [ ] **CHAT-04**: AI assistant can add/remove watchlist tickers on the user's behalf
- [ ] **CHAT-05**: Trade and watchlist actions taken by the AI are shown inline in the chat as confirmations (the transparency mitigation for zero-confirmation auto-execution)
- [ ] **CHAT-06**: Failed AI-initiated trades (e.g. insufficient cash) surface an error the AI can explain to the user in its response, rather than crashing the request
- [ ] **CHAT-07**: Chat supports a deterministic mock mode (`LLM_MOCK=true`) for testing without calling OpenRouter

### Frontend

- [ ] **UI-01**: User sees a dark, data-dense trading-terminal layout on first launch with no login/signup required
- [ ] **UI-02**: Clicking a ticker in the watchlist selects it for the main detail chart
- [ ] **UI-03**: Header shows live portfolio total value, cash balance, and a connection-status indicator (green/yellow/red dot)
- [ ] **UI-04**: AI chat panel is docked/collapsible with message input, scrolling history, and a loading indicator while waiting for a response
- [ ] **UI-05**: Trade bar allows entering ticker, quantity, and buy/sell with instant market-order execution

### Deployment

- [ ] **DEPLOY-01**: Application runs as a single Docker container on port 8000, serving both the API and the static frontend
- [ ] **DEPLOY-02**: SQLite database persists across container restarts via a volume-mounted `db/` directory, verified against a restart-with-existing-volume scenario
- [ ] **DEPLOY-03**: Start/stop scripts exist for macOS/Linux and Windows to build and run the container idempotently

### Testing

- [ ] **TEST-01**: Backend unit tests cover portfolio trade execution logic, P&L calculations, and edge cases (insufficient cash/shares, fractional shares)
- [ ] **TEST-02**: Backend unit tests cover LLM structured-output parsing, including malformed/invalid responses
- [ ] **TEST-03**: Frontend component tests cover price flash animation, watchlist CRUD, portfolio display calculations, and chat message rendering
- [ ] **TEST-04**: Playwright E2E suite (run with `LLM_MOCK=true`) covers: fresh start, watchlist add/remove, buy/sell flow, portfolio visualization, AI chat with trade execution, and SSE reconnection

## v2 Requirements

None — per explicit project decision, all of PLAN.md's scope is in v1 for this milestone. Anything beyond PLAN.md's spec is Out of Scope below, not deferred.

## Out of Scope

Explicitly excluded per PLAN.md's own design rationale. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Limit orders, stop-loss, options chains | Market orders only — avoids order-book/partial-fill/pending-order state machine complexity |
| Trade confirmation dialogs (manual or AI-initiated) | Deliberate: zero stakes (simulated money); frictionless "describe a strategy, watch it happen" is the core demo experience. Mitigated by inline action-transparency (CHAT-05), not by gating. |
| Multi-user accounts / login | No auth = no multi-user; `user_id="default"` hardcoded but schema is future-proofed |
| Postgres or any external DB server | SQLite is sufficient for single-user, zero-config, self-contained |
| WebSockets | SSE is sufficient for one-way price push; simpler and universally supported |
| Server-persisted price/sparkline history endpoint | Client-accumulated sparklines from the SSE stream are intentional; avoids extra backend surface area |
| Real brokerage integration / real-money execution | Total scope and regulatory explosion; also destroys the zero-stakes rationale that makes no-confirmation execution defensible |
| Push/toast notifications, price alerts | Orthogonal to the core agentic-AI demo value; not in PLAN.md |
| Terraform/App Runner cloud deployment config | Stretch goal only per PLAN.md §11, not core build |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DB-01 | TBD | Pending |
| DB-02 | TBD | Pending |
| DB-03 | TBD | Pending |
| STREAM-01 | TBD | Pending |
| STREAM-02 | TBD | Pending |
| PORT-01 | TBD | Pending |
| PORT-02 | TBD | Pending |
| PORT-03 | TBD | Pending |
| PORT-04 | TBD | Pending |
| PORT-05 | TBD | Pending |
| PORT-06 | TBD | Pending |
| PORT-07 | TBD | Pending |
| PORT-08 | TBD | Pending |
| WATCH-01 | TBD | Pending |
| WATCH-02 | TBD | Pending |
| WATCH-03 | TBD | Pending |
| WATCH-04 | TBD | Pending |
| WATCH-05 | TBD | Pending |
| CHAT-01 | TBD | Pending |
| CHAT-02 | TBD | Pending |
| CHAT-03 | TBD | Pending |
| CHAT-04 | TBD | Pending |
| CHAT-05 | TBD | Pending |
| CHAT-06 | TBD | Pending |
| CHAT-07 | TBD | Pending |
| UI-01 | TBD | Pending |
| UI-02 | TBD | Pending |
| UI-03 | TBD | Pending |
| UI-04 | TBD | Pending |
| UI-05 | TBD | Pending |
| DEPLOY-01 | TBD | Pending |
| DEPLOY-02 | TBD | Pending |
| DEPLOY-03 | TBD | Pending |
| TEST-01 | TBD | Pending |
| TEST-02 | TBD | Pending |
| TEST-03 | TBD | Pending |
| TEST-04 | TBD | Pending |

**Coverage:**
- v1 requirements: 36 total
- Mapped to phases: 0 (filled by roadmap creation)
- Unmapped: 36 ⚠️ (expected — roadmap not yet created)

---
*Requirements defined: 2026-08-01*
*Last updated: 2026-08-01 after initial definition*
