# Phase 1: Persistence & Trade Engine - Context

**Gathered:** 2026-08-02
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run — grey areas resolved directly from PLAN.md/REQUIREMENTS.md/codebase maps rather than interactive discussion, per explicit user direction to build the full project without interactive check-ins)

<domain>
## Phase Boundary

This phase delivers the SQLite persistence layer and the single, validated trade-execution path that every trading flow (manual trade in Phase 2, AI-initiated trade in Phase 3) must call through. It does NOT expose any HTTP routes (that's Phase 2) and does NOT touch the market data subsystem's internals (frozen/Validated) — it only reads current prices from the existing `PriceCache`.

In scope: `backend/db/schema.sql` + `seed.sql`, lazy init/seeding logic, a DB connection helper, repository/access functions for each table, the atomic `execute_trade()` function, and portfolio valuation math (current value, unrealized P&L) as pure functions callable by Phase 2's routes.

Out of scope: FastAPI route handlers (Phase 2), SSE (already built), LLM integration (Phase 3), any frontend.

</domain>

<decisions>
## Implementation Decisions

### Schema (locked by PLAN.md §7 — not a grey area, restated here for the planner)
- Six tables, all with `user_id TEXT DEFAULT 'default'`: `users_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages` (chat_messages table is created now for schema completeness even though Phase 3 is the first writer — avoids a schema migration later).
- IDs: TEXT PRIMARY KEY, UUIDs (except `users_profile.id` which is the literal string `"default"`).
- Timestamps: TEXT, ISO 8601 (`datetime.now(UTC).isoformat()`).
- Money/quantity columns (`cash_balance`, `quantity`, `avg_cost`, `price`, `total_value`): SQLite `REAL`. This is a PLAN.md constraint, not open for reconsideration (PROJECT.md: "Build exactly what PLAN.md specifies").
- UNIQUE `(user_id, ticker)` on `watchlist` and `positions`.
- Seed: one `users_profile` row (`cash_balance=10000.0`), ten `watchlist` rows (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX — same list already seeded in `app/market/seed_prices.py`, so watchlist and market-data seed tickers must match).

### Decimal/Float Boundary
- Use Python `Decimal` for all money and share-quantity arithmetic inside the trade-execution and valuation functions (weighted-average cost, cash debit/credit, P&L) to avoid float drift across repeated trades.
- Convert `Decimal → float` only at the two boundaries: writing to SQLite `REAL` columns, and serializing to JSON for the API layer (Phase 2's concern, but the functions this phase writes should return `Decimal` or `float` consistently — return `float` from public repository functions so Phase 2 doesn't need to know about `Decimal`, keeping `Decimal` usage internal to the engine module).
- No fixed rounding/quantization scheme is imposed (e.g. no forced 2-decimal cash rounding) — fractional shares and prices can carry full precision; this avoids inventing a rounding rule PLAN.md never specified.

### Concurrency (DB-03)
- On every connection: `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` (5 seconds). WAL is a one-time durable setting on the database file; `busy_timeout` is per-connection and must be set each time a connection opens.
- Follow the codebase's established pattern (documented in ARCHITECTURE.md, used by `massive_client.py`) for blocking I/O: use the stdlib `sqlite3` module (no new dependency), and wrap each blocking call in `asyncio.to_thread()` rather than introducing `aiosqlite` or an ORM. This keeps the persistence layer consistent with how the rest of the codebase already handles sync-blocking-call-in-async-context, and PLAN.md never calls for an ORM.
- Trade execution (the check-then-write for sufficient cash/shares) must run as a single SQLite transaction (`BEGIN IMMEDIATE` or equivalent) so the check and the write are atomic against concurrent writers — this is what makes PORT-04 ("atomic... preventing check-then-deduct races") true under WAL with multiple threads/tasks issuing trades.

### Lazy Init
- On backend startup (or first DB access — whichever the planner finds cleaner given FastAPI's lifespan hooks), check whether `db/finally.db` exists / has tables. If missing, execute `schema.sql` then `seed.sql`. No separate migration command; safe to call on every startup (idempotent — check for existing tables/rows before seeding, don't double-seed on restart).
- DB file path: `db/finally.db` relative to project root (per PLAN.md §4 directory structure — the top-level `db/` volume-mount directory, not `backend/db/` which holds only the SQL definition files).

### Module Layout (planner's discretion within these constraints)
- `backend/db/schema.sql`, `backend/db/seed.sql` already exist as empty placeholders per STRUCTURE.md — fill these in.
- Connection/init helper and repository/engine code goes under `backend/app/` in a new package (e.g. `backend/app/db/` for connection + lazy-init, `backend/app/portfolio/` for trade execution + valuation) — exact naming is the planner's call, following the existing `snake_case` module / `PascalCase` class conventions documented in CONVENTIONS.md. The one hard constraint: there must be exactly ONE trade-execution entry point (single function or single class method) that both Phase 2's manual-trade route and Phase 3's AI-trade path call — no parallel/duplicate validation logic.

### Claude's Discretion
- Exact internal module/file names within `backend/app/db/` and `backend/app/portfolio/` (or whatever the planner names them).
- Whether lazy-init runs via FastAPI `lifespan` context manager or a startup event — planner's call, prefer whichever is more idiomatic for the FastAPI version already pinned in `pyproject.toml` (`fastapi>=0.115.0`, which supports `lifespan`).
- Exact concurrency test design proving "two writers don't get 'database is locked'" (success criterion 4) — e.g. `asyncio.gather()` of multiple concurrent trade calls, or multi-threaded — planner/executor's call, using `pytest-asyncio` (already a dev dependency).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app.market.PriceCache` (`backend/app/market/cache.py`) — thread-safe, already implemented. Trade execution and portfolio valuation read current prices via `cache.get_price(ticker) -> float | None`. Must handle `None` gracefully (ticker not yet priced) per the documented "Assuming Cache Always Has Data" anti-pattern.
- `app/market/seed_prices.py` — existing list of the 10 default tickers; reuse this list (or a shared constant) for watchlist seeding rather than re-declaring it, so the two seed lists can't drift apart.

### Established Patterns
- `from __future__ import annotations` at the top of every module; full type hints (`dict[str, float]`, `X | None`); `snake_case` functions/`PascalCase` classes; module-level `logger = logging.getLogger(__name__)`; docstrings on all public classes/functions (prose style, not Google/NumPy).
- Blocking I/O wrapped in `asyncio.to_thread()` (see `massive_client.py:_poll_once()`) — apply the same for SQLite calls.
- Factory-function pattern for dependency injection (`create_market_data_source(cache)`, `create_stream_router(cache)`) — consider the same shape for a DB connection/session factory so Phase 2 can inject it via FastAPI `Depends`, consistent with existing style.
- Specific exception handling, never bare `except:`.

### Integration Points
- Trade execution needs read access to `PriceCache` (constructor/factory parameter, matching the existing DI pattern — not a global).
- `backend/tests/` mirrors `backend/app/` structure (e.g. `backend/tests/market/`); this phase's tests should live in a new `backend/tests/db/` and/or `backend/tests/portfolio/` mirroring the new `backend/app/db/` / `backend/app/portfolio/` packages, per STRUCTURE.md's "Where to Add New Code" guidance.
- `pytest-asyncio` is already a dev dependency (`asyncio_mode = "auto"` in `pyproject.toml`) — new async tests need no additional config.

</code_context>

<specifics>
## Specific Ideas

- Watchlist seed tickers must be identical to `app/market/seed_prices.py`'s ticker list — do not hardcode a second, possibly-divergent list in `seed.sql`.
- `TEST-01` (from ROADMAP Phase 1 requirements) means: fractional shares, exact-balance buys (spend exactly all cash), full-position sells (sell down to zero, position row should probably be deleted or zeroed — planner's call, but must not leave a phantom `quantity=0` position that then renders oddly in Phase 4/5's positions table and heatmap), and insufficient-cash/shares rejection are all covered by `uv run pytest`.

</specifics>

<deferred>
## Deferred Ideas

- REST route handlers, request/response validation models — Phase 2.
- Any UI representation of positions/trades — Phase 4/5.
- LLM-initiated trades — Phase 3 (but must reuse this phase's `execute_trade()` unchanged, per CHAT-03).

</deferred>
