---
phase: 01-live-market-terminal
plan: 01
subsystem: database, api
tags: [fastapi, sqlite, sse, wal, watchlist, lifespan]

requires: []
provides:
  - "backend/app/db/ package: WAL+busy_timeout connection factory (run_db seam), idempotent schema init + seed, watchlist CRUD data access"
  - "backend/app/main.py: create_app() FastAPI factory with lifespan wiring, dev CORS allowlist"
  - "backend/app/routes/watchlist.py: GET/POST /api/watchlist, DELETE /api/watchlist/{ticker}"
  - "GET /api/stream/prices mounted on the assembled app (frozen create_stream_router)"
  - "GET /api/health"
  - "Clean repo: no tracked db file, httpx dev dependency, TestClient importable"
affects: [phase-02-manual-trading, phase-03-portfolio-visualization, phase-04-ai-copilot, phase-05-one-command-ship]

actuals:
  tokens: 7029
  tasks: 3
  commits: 3

tech-stack:
  added: [httpx (dev-only, for fastapi.testclient.TestClient)]
  patterns:
    - "create_app() factory closing over one PriceCache instance — no module-level singleton"
    - "run_db(fn) async seam: short-lived sqlite3 connection per call via asyncio.to_thread, WAL + busy_timeout reissued on every open"
    - "Idempotent lazy init: schema.sql is pure CREATE TABLE IF NOT EXISTS DDL; seed guarded by a users_profile row-count check"
    - "Seed/ticker source of truth: app.market.seed_prices.SEED_PRICES imported by app/db/init.py — never duplicated as a literal list"
    - "Persist-then-track write ordering: DB write commits before the market_source.add_ticker()/remove_ticker() call-through"
    - "Ticker normalization (strip/upper/regex shape check) applied identically to POST body and DELETE path parameter, before any SQL or market-source call"

key-files:
  created:
    - backend/app/db/__init__.py
    - backend/app/db/connection.py
    - backend/app/db/schema.sql
    - backend/app/db/init.py
    - backend/app/db/watchlist.py
    - backend/app/routes/__init__.py
    - backend/app/routes/watchlist.py
    - backend/app/main.py
    - backend/tests/db/test_connection.py
    - backend/tests/db/test_init.py
    - backend/tests/routes/test_watchlist.py
    - backend/tests/routes/test_stream_mount.py
    - db/.gitkeep
  modified:
    - .gitignore
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/tests/conftest.py

key-decisions:
  - "Untracked and deleted the stale, polluted db/finally.db committed to git; added db/.gitkeep and four .gitignore patterns so lazy-init never silently skips seeding on a fresh clone again"
  - "schema.sql lives at backend/app/db/schema.sql (package-internal), not backend/db/ or the repo-root db/ runtime mount — resolves the planner's noted open question in favor of relative-path loading from within the importable package"
  - "SSE mount test drives the ASGI app directly (raw scope/receive/send) instead of httpx TestClient.stream(), because httpx's ASGITransport buffers the entire app call to completion and cannot signal a mid-stream client disconnect — which would hang forever against stream.py's intentionally infinite generator"

patterns-established:
  - "Every SQL statement uses `?` placeholders exclusively; verify gate greps for f-string-interpolated execute() calls in app/db and app/routes on every task"
  - "Watchlist mutation ordering: normalize -> validate (cap/duplicate) -> persist to SQLite -> call through to market_source -> return response"

requirements-completed: [DB-01, DB-02, DB-03, STREAM-01, WATCH-01, WATCH-02, WATCH-03]

coverage:
  - id: D1
    description: "Lazy-init SQLite database creates all six tables and seeds exactly the ten SEED_PRICES tickers on first start, idempotently on subsequent starts"
    requirement: DB-01
    verification:
      - kind: unit
        ref: "backend/tests/db/test_init.py::test_all_tables_created"
        status: pass
      - kind: unit
        ref: "backend/tests/db/test_init.py::test_seeds_ten_default_tickers"
        status: pass
      - kind: unit
        ref: "backend/tests/db/test_init.py::test_init_is_idempotent"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every SQLite connection reports journal_mode=wal and busy_timeout=5000"
    requirement: DB-03
    verification:
      - kind: unit
        ref: "backend/tests/db/test_connection.py::test_wal_and_busy_timeout"
        status: pass
    human_judgment: false
  - id: D3
    description: "GET /api/stream/prices is mounted on the assembled FastAPI app and responds text/event-stream"
    requirement: STREAM-01
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_stream_mount.py::test_stream_endpoint_mounted"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /api/watchlist returns the seeded ten tickers over HTTP"
    requirement: WATCH-01
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_watchlist.py::test_get_watchlist_returns_seeded_tickers"
        status: pass
    human_judgment: false
  - id: D5
    description: "POST /api/watchlist persists a new ticker and calls market_source.add_ticker(); rejects duplicates (409), malformed tickers (400), and over-cap adds (400)"
    requirement: WATCH-02
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_watchlist.py::test_add_ticker_persists_and_calls_source"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_watchlist.py::test_add_duplicate_ticker_returns_409_and_does_not_duplicate"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_watchlist.py::test_add_malformed_ticker_returns_400_and_never_calls_source"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_watchlist.py::test_add_ticker_at_cap_returns_400_and_writes_nothing"
        status: pass
    human_judgment: false
  - id: D6
    description: "DELETE /api/watchlist/{ticker} removes the row and calls market_source.remove_ticker(); 404 on unknown ticker, 400 on malformed path param"
    requirement: WATCH-03
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_watchlist.py::test_remove_ticker_persists_and_calls_source"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_watchlist.py::test_remove_unknown_ticker_returns_404"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_watchlist.py::test_remove_malformed_ticker_returns_400_before_any_query"
        status: pass
    human_judgment: false
  - id: D7
    description: "Repository tracks no SQLite database file; a fresh clone gets an empty db/ that lazy-init populates correctly; httpx/TestClient is importable"
    verification:
      - kind: other
        ref: "test \"$(git ls-files db/)\" = \"db/.gitkeep\""
        status: pass
      - kind: unit
        ref: "uv run --extra dev python -c \"import httpx; from fastapi.testclient import TestClient\""
        status: pass
    human_judgment: false
  - id: D8
    description: "Manual end-to-end: delete db/finally.db, start uvicorn against an empty db/, curl the seeded watchlist, POST a ticker, see it in the next SSE frame, restart the process, confirm it persisted, DELETE it"
    verification:
      - kind: manual_procedural
        ref: "Documented local full-stack run in 01-SKELETON.md, executed this session: GET returned 10 seeded tickers, POST PYPL returned 201, PYPL appeared in the SSE frame, restart preserved PYPL, DELETE PYPL returned 204"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-08-02
status: complete
---

# Phase 1 Plan 01: Backend Walking Skeleton Summary

**Lazy-init WAL-mode SQLite (all six tables), a `create_app()` FastAPI factory with lifespan-driven market-source startup, and a fully CRUD-able `/api/watchlist` that persists to SQLite and tracks live through the mounted SSE stream — no restart required.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-08-02T18:47Z (approx, first commit)
- **Completed:** 2026-08-02T19:01Z
- **Tasks:** 3
- **Files modified:** 17 (excl. `backend/uv.lock`)

## Accomplishments
- Untracked and deleted the stale, polluted `db/finally.db` from git; the repo now tracks only `db/.gitkeep`, and `.gitignore` correctly excludes the runtime database and its WAL/SHM/journal sidecars
- Built `backend/app/db/`: a WAL + `busy_timeout=5000` connection factory (`run_db()` async seam over `asyncio.to_thread`), idempotent schema creation from pure DDL, and seeding driven entirely by `app.market.seed_prices.SEED_PRICES` (zero duplicated ticker literals)
- Built the first-ever FastAPI app object (`backend/app/main.py`, `create_app()`), whose `lifespan` lazily initializes the database, starts the market data source from the *persisted* watchlist (falling back to `SEED_PRICES` only when empty), and mounts both the frozen `create_stream_router` and the new watchlist router
- Implemented the full watchlist HTTP contract: `GET`/`POST /api/watchlist`, `DELETE /api/watchlist/{ticker}` — every write validates ticker shape server-side, enforces the 50-ticker cap, persists to SQLite, and only then calls through to `market_source.add_ticker()`/`remove_ticker()`
- Verified end-to-end by hand: seeded 10 tickers over HTTP, added `PYPL`, saw it in the next SSE frame without a restart, restarted the backend process, confirmed `PYPL` survived, then removed it (204)
- 86/86 backend tests pass (including the pre-existing `tests/market/` suite), 96% coverage on `app/`, `ruff check` clean, and the SQL-injection grep gate (`execute(f"...")`) finds nothing in `app/db` or `app/routes`

## Task Commits

1. **Task 1: Repo hygiene — untrack stale db, fix .gitignore, add httpx dev dep** - `4cb9f29` (chore)
2. **Task 2: TRACER — seeded watchlist from SQLite to HTTP, with the SSE stream mounted** - `0b6c7cb` (feat)
3. **Task 3: Watchlist writes — add and remove a ticker, persisted and tracked by the live stream** - `14013ba` (feat)

_No TDD tasks in this plan; each task is a single atomic commit._

## Files Created/Modified
- `backend/app/db/connection.py` - WAL + busy_timeout connection factory, `get_db_path()`, `run_db()` seam
- `backend/app/db/schema.sql` - Pure DDL for all six tables + five indexes, byte-for-byte from the plan
- `backend/app/db/init.py` - Idempotent `init_db()`: executescript + row-count-guarded seed from `SEED_PRICES`
- `backend/app/db/watchlist.py` - `list_watchlist`/`count_watchlist`/`add_watchlist_ticker`/`remove_watchlist_ticker`, all parameterized
- `backend/app/routes/watchlist.py` - `TICKER_PATTERN`, `normalize_ticker`, `create_watchlist_router()` with GET/POST/DELETE
- `backend/app/main.py` - `create_app()` factory, lifespan, dev CORS allowlist, `/api/health`
- `backend/tests/conftest.py` - `temp_db` and `client` fixtures (lifespan-running `TestClient`)
- `backend/tests/db/test_connection.py`, `test_init.py` - WAL/busy_timeout, schema/seed/idempotency tests
- `backend/tests/routes/test_watchlist.py`, `test_stream_mount.py` - route contract + SSE mount tests
- `.gitignore`, `backend/pyproject.toml`, `backend/uv.lock` - db patterns, `httpx>=0.28.1` dev dependency
- `db/.gitkeep` - runtime volume-mount placeholder (replaces the deleted tracked `db/finally.db`)

## Decisions Made
- **schema.sql location:** placed at `backend/app/db/schema.sql` (package-internal) rather than the top-level `backend/db/` the codebase map originally suggested, per the plan's explicit call and the research's stated rationale (relative-path loading from within the importable package, and non-collision with the repo-root `db/` runtime mount).
- **SSE mount test strategy:** `httpx`'s `ASGITransport` (which backs `fastapi.testclient.TestClient`) runs the entire ASGI app call to completion before returning a response — it has no mechanism to signal a mid-stream client disconnect. Since `stream.py`'s generator is intentionally infinite (stops only on `request.is_disconnected()`), driving it through `TestClient.stream()` hangs forever. Discovered this by direct execution during Task 2 and switched `test_stream_mount.py` to call the app's ASGI callable directly with a `receive()` that reports `http.disconnect` after the first poll — the exact signal the frozen generator watches for.

## Deviations from Plan

None beyond the SSE test-strategy adjustment above, which was a testing-implementation detail, not a change to shipped behavior — the plan's specified behavior (`GET /api/stream/prices` responds 200 `text/event-stream`) is verified exactly as required, just via a different test harness mechanism than a naive `TestClient.stream()` call would have used.

## Issues Encountered

`backend/tests/routes/test_stream_mount.py::test_stream_endpoint_mounted` hung indefinitely on first attempt using `client.stream("GET", "/api/stream/prices")`. Root-caused (via a manual ASGI reproduction script) to `httpx.ASGITransport.handle_async_request` awaiting `self.app(scope, receive, send)` to full completion before constructing a `Response` — it cannot express a mid-stream disconnect signal back into the running app. Fixed by driving the app's ASGI callable directly with a custom `receive()` returning `http.disconnect` on its second invocation, which `Request.is_disconnected()` picks up on the generator's next poll. Test now completes in well under a second.

## User Setup Required

None - no external service configuration required. (`httpx` is a dev-only dependency, installed via `uv sync --extra dev`.)

## Next Phase Readiness

- `run_db()`, `connect()`, and the WAL-mode database file are ready for Phase 2's `execute_trade()` and the `positions`/`trades` tables (schema already includes them, currently empty).
- `create_app()`'s `lifespan` and `app.state.market_source`/`app.state.price_cache` are the mounting points every later phase's router will reuse.
- `app/routes/watchlist.py`'s `normalize_ticker`/validation pattern is the template for Phase 2's trade-ticket validation.
- No blockers. Frontend half of this phase (Next.js scaffold, watchlist grid, SSE client) is plan `01-02`, not covered here.

## Self-Check: PASSED

All 11 created files verified present on disk; all 3 task commits (`4cb9f29`, `0b6c7cb`, `14013ba`) verified present in `git log --oneline --all`.

---
*Phase: 01-live-market-terminal*
*Completed: 2026-08-02*
