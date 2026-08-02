# Phase 1: Live Market Terminal - Context

**Gathered:** 2026-08-02
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run — grey areas resolved directly from PLAN.md/REQUIREMENTS.md/codebase maps rather than interactive discussion, per explicit user direction to build the full project without interactive check-ins)

<domain>
## Phase Boundary

This phase delivers the first vertical slice: a user opens the app at a single URL and sees a live, editable watchlist streaming real prices in a dark trading-terminal UI. It spans the full stack — SQLite persistence layer (all six tables, even though only `watchlist`/`users_profile` are exercised by this phase's UI, because DB-01/02/03 are foundational and nothing else can persist without them), the `/api/stream/prices` SSE route wired to the existing `PriceCache`, watchlist CRUD persisted to DB, and the first-ever Next.js frontend (project doesn't exist yet — `frontend/` is empty).

Out of scope: trading (Phase 2 — no `execute_trade()`/trade-execution engine in this phase), portfolio visuals (Phase 3), AI chat (Phase 4), Docker packaging (Phase 5). No `positions`/`trades`/`portfolio_snapshots`/`chat_messages` writers exist yet — those tables exist in the schema (DB-01 requires the full schema) but stay empty until later phases.

</domain>

<decisions>
## Implementation Decisions

### Schema (locked by PLAN.md §7 — not a grey area, restated for the planner)
- Six tables, all with `user_id TEXT DEFAULT 'default'`: `users_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages`. All six must exist after lazy init (DB-01) even though this phase only reads/writes `users_profile` (seed only) and `watchlist`.
- IDs: TEXT PRIMARY KEY, UUIDs (except `users_profile.id = "default"`). Timestamps: TEXT ISO 8601.
- Seed: `users_profile` row with `cash_balance=10000.0`; ten `watchlist` rows — AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX (must match `backend/app/market/seed_prices.py`'s ticker list exactly — reuse that list, don't re-declare it).
- WAL mode (`PRAGMA journal_mode=WAL`) + `PRAGMA busy_timeout=5000` on every connection (DB-03) — this phase is the first writer, so it must set this up correctly even though heavy concurrent writes don't start until Phase 2's trade endpoint.
- Lazy init: on backend startup (FastAPI `lifespan`, fastapi>=0.115 already pinned), check for tables; create `backend/db/schema.sql` + `backend/db/seed.sql` if missing. Idempotent — safe to call on every restart, never re-seeds an already-initialized DB. `backend/db/` does not currently exist on disk (must be created); do not trust any codebase-map claim that schema.sql/seed.sql are pre-existing placeholders — verify with `ls` first.
- DB connection pattern: stdlib `sqlite3` (no new dependency, no `aiosqlite`/ORM), wrapped in `asyncio.to_thread()` per call — matches the existing `backend/app/market/massive_client.py` blocking-I/O pattern.

### Known environment issue — MUST be an early task
- `db/finally.db` is currently **committed to git** with stale, polluted seed data (extra watchlist rows, phantom positions/trades) from an earlier scaffolding step, and `.gitignore` only matches the Django-leftover pattern `db.sqlite3` — it does NOT match `finally.db`. Since lazy-init only seeds when tables are missing, this stale committed file would be silently treated as "already initialized" and never get the correct seed data. The plan MUST: untrack `db/finally.db` from git, delete it (and any `-shm`/`-wal` sidecars) from the working tree, add `db/.gitkeep`, and fix `.gitignore` to match `finally.db`/`finally.db-shm`/`finally.db-wal`/`finally.db-journal`.

### SSE Route (STREAM-01, STREAM-02)
- `GET /api/stream/prices` — thin FastAPI route wiring; the actual SSE generator already exists and is fully implemented/tested at `backend/app/market/stream.py:create_stream_router()`. This phase's job is to mount that router in the (new, to-be-created) FastAPI app entrypoint, initialize the market data source (`create_market_data_source(cache)` from `backend/app/market/factory.py`) at startup with the seeded watchlist tickers, and ensure watchlist add/remove calls `MarketDataSource.add_ticker()`/`remove_ticker()` so the stream tracks watchlist changes live.
- Frontend: native `EventSource` for the SSE connection (STREAM-02 — reconnection is `EventSource`'s built-in behavior, no custom retry logic needed).

### Frontend (first-ever Next.js code in this repo)
- `frontend/` is currently empty. This phase scaffolds the whole Next.js TypeScript project: `output: 'export'` static export config (per PLAN.md §3/§11 — single-origin, no CORS, servable as static files by FastAPI later in Phase 5), Tailwind CSS with the locked dark theme (backgrounds `#0d1117`/`#1a1a2e`, no pure black; accent yellow `#ecad0a`, blue primary `#209dd7`, purple secondary `#753991` for submit buttons).
- Watchlist grid: ticker, live price (green/red flash on change fading ~500ms via CSS transition), daily change %, sparkline mini-chart accumulated client-side from the SSE stream since page load (not server-computed history — the frontend builds it up in memory as events arrive).
- Header: connection-status dot (green=connected, yellow=reconnecting, red=disconnected), driven by `EventSource.onopen`/`onerror` state.
- Add/remove ticker UI: simple input + button, calls `POST /api/watchlist` / `DELETE /api/watchlist/{ticker}`.
- No portfolio/trade/chat UI in this phase — those are stubbed absent, not placeholder-rendered (don't build empty panels for future phases).

### Claude's Discretion
- Exact Next.js file/component structure (`frontend/components/`, `frontend/lib/`) — follow standard Next.js App Router conventions since this is a fresh scaffold; no existing frontend convention to match yet.
- Charting approach for the sparkline specifically (inline SVG/canvas vs. a lightweight library) — PLAN.md recommends Lightweight Charts or Recharts for the *main* detail chart (that's Phase 3), but a watchlist-row sparkline is small enough that a hand-rolled inline SVG polyline may be simpler than pulling in a charting dependency this early; planner's call.
- Backend app entrypoint structure (`backend/app/main.py` vs similar) — first phase to create the actual `FastAPI()` app object; follow `backend/app/market/` conventions (factory functions, dependency injection, no global state).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets (fully implemented, frozen — do not modify)
- `backend/app/market/cache.py` — `PriceCache`, thread-safe, `get_price(ticker) -> float | None`, `get_all()`, `version` property.
- `backend/app/market/stream.py` — `create_stream_router(cache) -> APIRouter` already implements the full `/api/stream/prices` SSE generator (500ms cadence, version-based change detection, retry directive). This phase mounts it, does not rewrite it.
- `backend/app/market/factory.py` — `create_market_data_source(cache)` selects Simulator vs Massive based on `MASSIVE_API_KEY`.
- `backend/app/market/interface.py` — `MarketDataSource.add_ticker()`/`remove_ticker()`/`start()`/`stop()`.
- `backend/app/market/seed_prices.py` — canonical 10-ticker list; reuse for both market-data seeding and DB watchlist seeding.

### Established Patterns
- `from __future__ import annotations`, full type hints, `snake_case`/`PascalCase`, module-level `logger = logging.getLogger(__name__)`, prose docstrings, specific exception handling, blocking I/O via `asyncio.to_thread()`. Factory-function DI pattern (`create_X(cache)`) — follow the same shape for a new DB connection/session factory.

### Integration Points
- New FastAPI app object (doesn't exist yet) must: initialize `PriceCache` + market data source at startup, lazy-init the DB, mount the market router (`create_stream_router`) plus new watchlist routes, and serve as the single app entrypoint future phases add routers to.
- `backend/tests/` mirrors `backend/app/` — new tests go in `backend/tests/db/`, `backend/tests/routes/` (or similar) mirroring new `backend/app/db/`, `backend/app/routes/` packages.

</code_context>

<specifics>
## Specific Ideas

- Watchlist seed tickers must be identical between `app/market/seed_prices.py` and the DB `watchlist` seed rows — single source of truth, no duplicated literal list.
- Success criterion 4 ("survives a page refresh and a backend restart") means watchlist add/remove must persist to SQLite immediately, not just update the in-memory `PriceCache`/`MarketDataSource` state — both must be updated together on every add/remove.
- Success criterion 5 ("stream drops, prices resume on their own") is satisfied by `EventSource`'s native auto-reconnect — no custom reconnect logic needed on the frontend, just don't fight it with manual connection teardown/rebuild.

</specifics>

<deferred>
## Deferred Ideas

- Trade execution, positions, trades, portfolio_snapshots writers — Phase 2.
- Portfolio heatmap, P&L chart, ticker detail chart — Phase 3.
- AI chat panel — Phase 4.
- Docker packaging, start/stop scripts — Phase 5.

</deferred>
