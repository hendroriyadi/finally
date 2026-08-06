# FinAlly — AI Trading Workstation

## What This Is

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation: a single-container web app that streams live (simulated or real) market data, lets a user trade a simulated $10,000 portfolio, and includes an LLM chat assistant that can analyze the portfolio and execute trades on the user's behalf. It's a Bloomberg-terminal-style demo, built as the capstone project for an agentic AI coding course, and is built end-to-end by coding agents.

## Core Value

A user opens one URL and, with zero setup, sees live-streaming prices, can place trades, and can chat with an AI copilot that actually analyzes their portfolio and executes trades for them. The AI-driven trading experience is the centerpiece — everything else (charts, heatmap, terminal aesthetic) exists to make that experience feel real.

## Requirements

### Validated

- ✓ Market data abstraction (simulator + optional Massive/Polygon.io REST client behind one interface) — existing
- ✓ GBM-based price simulator with correlated moves and random events — existing
- ✓ Thread-safe in-memory price cache (latest/previous price, timestamp per ticker) — existing
- ✓ SSE-ready backend plumbing for live price streaming — existing (endpoint wiring still to be exposed via FastAPI routes)
- ✓ FastAPI backend scaffold on `uv`, Python 3.12 — existing
- ✓ Test suite for the market data layer (pytest, async support) — existing

### Active

Build the rest of FinAlly exactly as specified in `planning/PLAN.md` — no scope changes from that document. This covers:

- [ ] SQLite database: schema (users_profile, watchlist, positions, trades, portfolio_snapshots, chat_messages), lazy init + seed data
- [ ] `/api/stream/prices` SSE endpoint wired to the existing price cache
- [ ] Portfolio API: get portfolio, execute trade (market orders only), get value history
- [ ] Watchlist API: get/add/remove tickers
- [ ] Chat API: `/api/chat` — LLM-backed assistant via LiteLLM → OpenRouter (Cerebras inference, `openrouter/openai/gpt-oss-120b`), structured-output trade/watchlist auto-execution
- [ ] `LLM_MOCK=true` deterministic mock mode for tests/dev
- [ ] Next.js (TypeScript, static export) frontend: watchlist grid with price-flash + sparklines, main chart, portfolio heatmap, P&L chart, positions table, trade bar, AI chat panel, header with connection status
- [ ] Dark trading-terminal visual design per PLAN.md color scheme (`#0d1117`/`#1a1a2e` backgrounds, `#ecad0a` yellow, `#209dd7` blue, `#753991` purple)
- [ ] Multi-stage Dockerfile (Node → Python), single container, single port 8000, SQLite volume mount
- [ ] Start/stop scripts (macOS/Linux + Windows PowerShell)
- [ ] Backend unit tests (portfolio math, LLM structured-output parsing, API routes) + frontend component tests
- [ ] Playwright E2E suite in `test/` with `docker-compose.test.yml`, run against `LLM_MOCK=true`

### Out of Scope

- Limit orders, partial fills, order book — Market orders only, per PLAN.md's simplicity rationale
- Multi-user auth/login — Single hardcoded `user_id="default"`, per PLAN.md
- Postgres or any external DB server — SQLite is sufficient for single-user, zero-config
- WebSockets — SSE is sufficient for one-way price push, simpler and universal
- Trade confirmation dialogs — Deliberate: zero stakes (fake money), fluid demo experience
- Terraform/App Runner deployment config — Stretch goal only, not core build (per PLAN.md §11)

## Context

- This is a capstone project for an agentic-AI coding course — the whole app (beyond the already-built market data layer) is meant to be built by coding agents, demonstrating orchestrated agent workflows.
- The full, detailed spec already exists at `planning/PLAN.md` (vision, architecture, DB schema, API contracts, LLM integration behavior, frontend layout, Docker/deployment, testing strategy). This PROJECT.md summarizes it as the working reference; PLAN.md remains the source of truth for exact contracts (endpoint shapes, schema field names, structured-output JSON schema, etc.) — consult it during planning/execution rather than re-deriving these from scratch.
- Codebase state (`.planning/codebase/`, mapped 2026-08-01): backend is a `uv`-managed FastAPI project with the market data subsystem (simulator, Massive client, price cache) fully implemented and tested. Routes (portfolio/watchlist/chat), the database layer, LLM integration, and the entire `frontend/` (Next.js not yet initialized) are not yet built. See `.planning/codebase/ARCHITECTURE.md` and `STRUCTURE.md` for the current layout.
- `OPENROUTER_API_KEY` is already present in the project's `.env` (per user, 2026-08-01) — the chat/LLM phase is unblocked on that front.
- No deadline — build to the full PLAN.md spec at a sustainable pace.

## Constraints

- **Tech stack**: FastAPI (Python 3.12, `uv`) backend, Next.js (TypeScript, static export) frontend, SQLite, single Docker container on port 8000 — locked in by PLAN.md, not open for reconsideration.
- **LLM provider**: LiteLLM → OpenRouter, Cerebras inference, `openrouter/openai/gpt-oss-120b`, structured outputs — per PLAN.md §9 and the `cerebras-inference` skill.
- **Architecture**: Must reuse the existing market data interface/price cache as-is; new code (SSE route, portfolio valuation, etc.) reads from that cache rather than re-implementing data fetching.
- **Scope discipline**: Build exactly what PLAN.md specifies — user explicitly declined to change or simplify scope.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Follow PLAN.md as-is, no scope changes | User confirmed: "just build it as specified in PLAN.md, no deadline" | — Pending |
| Treat market data subsystem as Validated/frozen | Already implemented, tested, and summarized in `planning/MARKET_DATA_SUMMARY.md`; new work builds on top of it, not around it | ✓ Good |
| No deadline-driven phase compression | User confirmed no deadline exists | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-01 after initialization*
