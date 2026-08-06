# Project Research Summary

**Project:** FinAlly — AI Trading Workstation
**Domain:** Single-container FastAPI + SQLite + Next.js static export, with AI-powered trade execution
**Researched:** 2026-08-01
**Confidence:** MEDIUM

## Executive Summary

FinAlly is a single-container trading simulator with an AI copilot that can analyze portfolios and execute trades in natural language. The architecture is lean by design: a frozen market-data layer (GBM simulator + optional Massive API) feeds a new persistence/API/LLM middleware stack, all served by FastAPI on port 8000. The project leverages well-established patterns (SQLite + FastAPI, static Next.js export, LiteLLM structured outputs) but concentrates risk in three areas: money-math correctness (float vs. Decimal), SQLite concurrency (WAL mode is mandatory), and LLM validation (the backend must never trust LLM arithmetic or proposed trades without re-validating them server-side).

The recommended approach is to build bottom-up: solidify the database and trade-execution logic first (where precision and atomicity are load-bearing), then wire up the REST API and frontend against that stable foundation, then layer the LLM on top. This order ensures the hardest-to-debug issues (race conditions, arithmetic drift) are caught early, and means frontend work can start against a real, working API rather than guessing at contracts.

Key risk: the project's distinctive feature — AI auto-executing trades with zero confirmation dialog — is deliberately allowed by PLAN.md but only defensible if paired with strong post-hoc visibility (inline action-confirmation cards in the chat transcript) and airtight server-side validation. This research identifies that risk explicitly and maps it to specific phases.

## Key Findings

### Recommended Stack

FastAPI ≥0.136.0 (upgrade recommended from the currently installed 0.128.7) provides native SSE support via `fastapi.sse.EventSourceResponse`, eliminating the need for `sse-starlette`. The frontend is a Next.js static export (`output: 'export'`), built once and served by FastAPI as static files — single container, single port. Database is SQLite with `aiosqlite` for async access, running in WAL mode with a 5-second busy timeout (mandatory to avoid "database is locked" errors from the concurrent portfolio-snapshot background task). LLM uses LiteLLM ≥1.90.0 (1.82.8 was a confirmed PyPI supply-chain compromise — do not use) routed to OpenRouter/Cerebras with Pydantic structured outputs for trade/watchlist action validation, following the project's own `cerebras-inference` skill pattern verbatim.

Frontend charting splits: Lightweight Charts (canvas-based, TradingView) for the high-frequency-updating detail chart; Recharts for the heatmap/treemap, P&L chart, and sparklines (its built-in `<Treemap>` and axis-less `<LineChart>` cover all three, no separate sparkline library needed).

**Core technologies:**
- **FastAPI ≥0.136.0**: Native SSE, REST API, static file serving — bump from current 0.128.7 pin
- **Next.js (static export)**: Single-origin SPA, no runtime Node needed in production
- **SQLite + aiosqlite**: WAL mode + busy_timeout for concurrent safety with multiple writers
- **LiteLLM ≥1.90.0**: Structured-output LLM calls with Pydantic validation — avoid the yanked 1.82.8
- **Lightweight Charts + Recharts**: Split charting for different update-frequency needs
- **Tailwind CSS**: Dark theme with PLAN.md's brand colors

### Expected Features

Table stakes and differentiators from PLAN.md are confirmed as industry-standard for this product category, not invented from scratch — high confidence to proceed as specified.

**Must have (table stakes):**
- Watchlist grid with live prices, flash animation, sparkline
- Detail chart, positions table, buy/sell entry, cash/portfolio display, connection indicator

**Should have (competitive):**
- AI chat with portfolio-aware analysis and trade auto-execution
- AI proactively manages watchlist
- Portfolio heatmap/treemap (recognized best-practice visualization, Finviz-style)
- P&L-over-time line chart
- Bloomberg-terminal dark aesthetic

**Defer (v2+, explicitly out of scope per PLAN.md):**
- Limit orders, stop-loss/options, multi-user auth, real brokerage integration, price alerts

### Architecture Approach

Layered: frozen market-data layer → price cache → new persistence layer (SQLite repository) → service layer (trade validation, P&L math) → REST adapters + LLM handler. The critical seam is a **shared trade-execution service** — both the manual REST trade route and the LLM chat handler must call one function (`execute_trade()`), never duplicate validation logic. Singletons are created in FastAPI's `lifespan` hook and injected via `Depends()`. The frontend is mounted as a static fallback after all API routes.

**Major components:**
1. `app/db/` — connection, schema init, repository functions
2. `app/portfolio/service.py` and `app/watchlist/service.py` — trade validation, P&L math (the shared seam)
3. `app/routes/` — thin HTTP adapters over the service layer
4. `app/llm/chat.py` — context assembly, LLM call, action execution via the same service layer
5. `PriceCache` (existing, frozen) — read-only dependency for all of the above
6. Next.js static export — served by FastAPI as static files

### Critical Pitfalls

1. **Float arithmetic drifts** — Use Python `Decimal` for all money/quantity math, converting only at the DB boundary; test with exact assertions, not approximate ones.
2. **Check-then-deduct race** — Make the balance check + update atomic in a single `UPDATE ... WHERE cash_balance >= :cost` statement, checking rowcount rather than a separate SELECT-then-UPDATE.
3. **SQLite "database is locked"** — Enable WAL mode + `PRAGMA busy_timeout=5000` at connection startup, from day one (multiple concurrent writers: trade endpoint, chat endpoint, 30s snapshot task).
4. **LLM trades bypassing validation** — Route every LLM-proposed trade through the identical `execute_trade()` function used for manual trades; never trust LLM arithmetic or a separate less-validated path.
5. **Structured-output parsing fragility** — Validate LLM output against the Pydantic model; wrap in try/except that returns a graceful chat error and never executes from a malformed response.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Database & Schema
**Rationale:** Everything downstream depends on a concurrent-safe SQLite layer
**Delivers:** Schema, lazy init via FastAPI `lifespan`, repository functions, WAL mode + busy_timeout
**Avoids:** SQLite locking pitfall, lazy-init race pitfall

### Phase 2: Portfolio & Watchlist Service
**Rationale:** Core domain logic, called from both REST and LLM paths — the load-bearing shared seam
**Delivers:** `execute_trade()` (atomic, Decimal-based), weighted-avg-cost calculation, portfolio valuation
**Avoids:** Float-drift pitfall, check-then-deduct race pitfall
**Research flag:** Needs a detailed math spec and thorough unit tests (fractional shares, insufficient-funds edge cases)

### Phase 3: REST API
**Rationale:** Thin adapters over Phase 2, makes the core manual-trading loop functional end-to-end
**Delivers:** `/api/portfolio`, `/api/portfolio/trade`, `/api/watchlist/*`, portfolio snapshots, `/api/health`
**Uses:** FastAPI, the Phase 2 service layer

### Phase 4: SSE & Watchlist UI
**Rationale:** First fully visible user-facing feature, unblocks frontend iteration
**Delivers:** `/api/stream/prices` wired to the existing `PriceCache`, watchlist grid, flash animation, connection-status indicator
**Avoids:** SSE reconnection pitfall

### Phase 5: Charts & Portfolio Visualization
**Rationale:** Visualize the now-working portfolio
**Delivers:** Positions table, heatmap/treemap, P&L chart, detail chart, dashboard layout
**Research flag:** Worth a quick Recharts Treemap prototype with dynamic data before committing to layout

### Phase 6: LLM Integration & Chat
**Rationale:** Layer the distinctive feature on top of now-stable APIs
**Delivers:** Chat endpoint, context assembly, structured-output call via `cerebras-inference` skill, trade/watchlist auto-execution, inline action-confirmation cards, `LLM_MOCK=true` mode
**Avoids:** LLM-bypass-validation pitfall, structured-output parsing pitfall
**Research flag:** Validate the exact LiteLLM + OpenRouter + `openrouter/openai/gpt-oss-120b` + Cerebras combination works as expected — general OpenRouter structured-output findings were used as a proxy, not verified against this exact model/provider pairing

### Phase 7: Frontend SPA Completion
**Rationale:** All APIs working — assemble the full Next.js SPA
**Delivers:** Trade bar, chat panel, responsive layout, dark theme polish, error handling

### Phase 8: Docker & Deployment
**Rationale:** Containerize the single-container design as the final step
**Delivers:** Multi-stage Dockerfile, start/stop scripts, volume mount, restart-with-existing-volume verification
**Research flag:** Decide between FastAPI's newer native `app.frontend()` (requires the version bump) vs. traditional `StaticFiles` + catch-all for serving the SPA

### Phase Ordering Rationale

- Phases 1–3 are strict prerequisites (DB → service layer → REST) since each can be independently pytested before the next depends on it.
- Phases 4–5 can be worked in parallel once Phase 3 lands (both are largely read-only consumers of the portfolio/watchlist API).
- Phase 6 (LLM) deliberately comes after 3–5 are stable, since it reuses their validated contracts rather than inventing its own.
- Phase 7 depends on a working backend across all prior phases.
- Phase 8 is last by nature — it packages what already works.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Portfolio/trade math — precision, atomicity, and edge cases are the highest-risk area in this project
- **Phase 6:** LLM integration — exact LiteLLM/OpenRouter/Cerebras compatibility for this specific model needs a spike, not just documentation review
- **Phase 8:** Docker/frontend-serving — FastAPI version bump decision (native `app.frontend()` vs. `StaticFiles` fallback) needs a deliberate call

Phases with standard, well-documented patterns (skip research-phase):
- **Phase 1:** SQLite + FastAPI lazy-init is a well-established pattern
- **Phase 3:** Standard REST CRUD over an existing service layer
- **Phase 4:** SSE + EventSource is standard, MDN-documented behavior
- **Phase 7:** Standard Next.js SPA assembly, no novel integration risk

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Core tech mature and cross-checked against official docs; LiteLLM + OpenRouter structured-output compatibility for this exact model/provider pairing needs validation during Phase 6 |
| Features | MEDIUM | Grounded in PLAN.md (locked, authoritative scope) plus competitor cross-checks; AI auto-execute UX risk is well-researched and has a clear mitigation (inline transparency) |
| Architecture | MEDIUM-HIGH | Standard FastAPI patterns verified against official docs; shared-service-layer pattern is directionally consistent across sources though not independently novel |
| Pitfalls | MEDIUM-HIGH | Thoroughly cross-referenced (official docs, community sources, one academic source); high confidence on the risks themselves, medium on exact prevention specifics for this project |

**Overall confidence:** MEDIUM — not a novel architecture, but execution discipline (money-math precision, validation boundaries, concurrency handling) is what will make or break quality.

### Gaps to Address

- **Decimal conversion strategy**: exactly when/where float↔Decimal conversion happens (DB boundary vs. API boundary) — spec this out during Phase 2 planning.
- **LiteLLM + OpenRouter + Cerebras version validation**: confirm the `cerebras-inference` skill pattern works end-to-end with the specified model before relying on it in Phase 6.
- **Recharts Treemap behavior**: verify readability with realistic position counts (10-15) before committing to final heatmap layout in Phase 5.
- **SSE reconnection semantics**: define exact frontend behavior on reconnect (gap indication, backfill or not) in Phase 4 requirements.
- **Chat context window**: how many prior messages to include per LLM call — define in Phase 6 requirements.
- **A sibling reference implementation** may exist at `github.com/ed-donner/fin` (surfaced during features research as apparently the instructor's own prior build of a similar spec) — worth a look during phase planning as a de-risking reference, not a source of truth to copy blindly.

## Sources

### Primary (HIGH confidence)
- Official FastAPI docs (fastapi.tiangolo.com) — SSE support, lifespan, Depends, static file serving
- Official SQLite docs and forum — WAL mode, busy_timeout, lazy-init race conditions
- Python official docs — Decimal vs. float for money math
- MDN — EventSource/SSE reconnection mechanics
- Project's own `cerebras-inference` skill and `planning/PLAN.md` — LLM integration pattern, full product spec

### Secondary (MEDIUM confidence)
- OpenRouter official docs and GitHub issues — structured-output defects and compatibility notes
- Context7 aggregated docs — FastAPI/Next.js cross-checks
- arXiv papers on agentic financial security — LLM auto-execution trust boundary research
- Competitor/practitioner sources (Finviz, paper-trading platform reviews) — feature landscape and treemap conventions

### Tertiary (LOW confidence)
- General web search / blog posts — float-as-money anti-pattern framing, general FastAPI+SPA+SQLite build-order conventions

---
*Research completed: 2026-08-01*
*Ready for roadmap: yes*
