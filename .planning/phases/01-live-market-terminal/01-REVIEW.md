---
phase: 01-live-market-terminal
reviewed: 2026-08-02T18:20:54Z
depth: standard
files_reviewed: 34
files_reviewed_list:
  - .gitignore
  - backend/app/db/__init__.py
  - backend/app/db/connection.py
  - backend/app/db/init.py
  - backend/app/db/schema.sql
  - backend/app/db/watchlist.py
  - backend/app/main.py
  - backend/app/routes/__init__.py
  - backend/app/routes/watchlist.py
  - backend/pyproject.toml
  - backend/tests/conftest.py
  - backend/tests/db/__init__.py
  - backend/tests/db/test_connection.py
  - backend/tests/db/test_init.py
  - backend/tests/routes/__init__.py
  - backend/tests/routes/test_stream_mount.py
  - backend/tests/routes/test_watchlist.py
  - db/.gitkeep
  - frontend/.env.local.example
  - frontend/.gitignore
  - frontend/app/globals.css
  - frontend/app/layout.tsx
  - frontend/app/page.tsx
  - frontend/components/AddTickerForm.tsx
  - frontend/components/AppHeader.tsx
  - frontend/components/ConnectionStatusDot.tsx
  - frontend/components/PriceStreamProvider.tsx
  - frontend/components/RemoveTickerButton.tsx
  - frontend/components/Sparkline.tsx
  - frontend/components/WatchlistPanel.tsx
  - frontend/components/WatchlistRow.tsx
  - frontend/lib/api.ts
  - frontend/lib/types.ts
  - frontend/lib/useSseStream.ts
  - frontend/next.config.ts
  - frontend/package.json
  - frontend/postcss.config.mjs
findings:
  critical: 0
  warning: 6
  info: 3
  total: 9
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-08-02T18:20:54Z
**Depth:** standard
**Files Reviewed:** 34
**Status:** issues_found

## Summary

Reviewed the Phase 1 "Live Market Terminal" diff (`f357189..HEAD`): SQLite lazy-init/seed, the WAL-mode connection factory, the watchlist REST router, CORS config, and the Next.js watchlist grid (SSE consumption, sparkline/flash UI, add/remove-ticker forms).

The core security asks hold up well: every SQL statement is parameterized (no string-built SQL anywhere), the ticker shape regex is applied identically on both write paths before any DB or market-source call, CORS is an exact-origin allowlist with `allow_credentials=False` (correctly scoped as dev-only per the code comment), and ticker strings reach the DOM only through JSX text interpolation — no `dangerouslySetInnerHTML`, no `eval`, no innerHTML anywhere in the reviewed files, so there's no XSS path from a ticker string.

What I found instead is a cluster of real-but-survivable logic/race bugs: a TOCTOU race on the watchlist size cap, two places where a downstream failure after a DB mutation leaves persistent state and live-stream state out of sync with no rollback, an overly-broad exception catch that can mis-attribute unrelated DB errors as "duplicate ticker," a seed-race in `init_db()` that contradicts its own documented idempotency guarantee, a connection-status state machine on the frontend that can get stuck showing "Reconnecting" forever after an unrecoverable SSE failure, and two places where a non-`ApiError` failure (e.g., a bare network error) is silently swallowed as an unhandled promise rejection with zero user-facing feedback. None of these are exploitable as security vulnerabilities and none corrupt data, but several are logic bugs that will surface as confusing, silently-broken UI states under real network conditions — worth fixing before this phase is considered done.

## Warnings

### WR-01: Watchlist size cap has a check-then-act race

**File:** `backend/app/routes/watchlist.py:73-79`
**Issue:** `add_ticker` calls `count_watchlist()` and compares to `MAX_WATCHLIST_SIZE`, then — as a separate, unguarded step — calls `add_watchlist_ticker()`. Two concurrent POST requests can both observe `count == 49` and both proceed to insert, letting the watchlist grow past `MAX_WATCHLIST_SIZE`. Contrast this with `add_watchlist_ticker`'s own duplicate-ticker handling (`backend/app/db/watchlist.py:55-63`), which the code's own docstring correctly notes is "race-free without a separate read" because it lets the DB's UNIQUE constraint be the single source of truth — the size cap doesn't get the same treatment.
**Fix:** Enforce the cap inside the same statement/transaction as the insert, e.g. a single `INSERT ... SELECT ... WHERE (SELECT COUNT(*) ...) < MAX_WATCHLIST_SIZE` guarded by `rowcount`, or take an explicit lock around count+insert in `run_db`.

### WR-02: No compensation when the market-data source call fails after a DB mutation

**File:** `backend/app/routes/watchlist.py:79-86` (add), `92-96` (remove)
**Issue:** `add_ticker` persists the watchlist row first, then calls `request.app.state.market_source.add_ticker(ticker)` with no try/except. If that call raises (e.g. an upstream data-source error for a syntactically-valid-but-unknown symbol), the request 500s but the watchlist row is already committed — the ticker is now permanently in the DB with no live price feed until the process restarts and re-seeds from the watchlist. The mirror case in `remove_ticker` is the same shape: the DB delete commits before `market_source.remove_ticker()` runs, so a failure there leaves a ticker still streaming that the DB (and therefore every `GET /api/watchlist` response) says is gone.
**Fix:** Wrap the market-source call and, on failure, compensate (delete the just-inserted row / re-add the just-deleted row) before propagating the error, or make the two operations part of one explicit unit of work with rollback on either side failing.

### WR-03: Overly broad `except sqlite3.IntegrityError` conflates "duplicate" with "any integrity violation"

**File:** `backend/app/db/watchlist.py:55-63`
**Issue:** `add_watchlist_ticker` catches bare `sqlite3.IntegrityError` and unconditionally returns `None`, which the router turns into `409 "{ticker} is already on the watchlist"`. Any other integrity violation on that insert (e.g. a future NOT NULL/FK addition, or corruption) would be silently reported to the user as "already on the watchlist," which is misleading and would hide the real failure from logs.
**Fix:** Inspect the exception (e.g. match on the UNIQUE constraint via the error message, or use `sqlite3.IntegrityError` subclassing where available) or at minimum log the original exception before mapping to the 409, so a genuinely different integrity failure isn't silently misreported.

### WR-04: `init_db()` seed step is not safe under concurrent invocation, contradicting its own doc comment

**File:** `backend/app/db/init.py:27-49`
**Issue:** The module docstring states `init_db()` "is safe to call on every backend startup" and is idempotent via a `SELECT COUNT(*) FROM users_profile` guard. That guard is check-then-act across a fresh connection with no locking: if `init_db()` is ever invoked twice concurrently (e.g. two lifespans/workers sharing the same DB file, or a future multi-process deployment), both calls can read `existing == 0` before either inserts, and the second `INSERT INTO users_profile` will raise an **unhandled** `sqlite3.IntegrityError` (`users_profile.id` is a primary key) that isn't caught anywhere in `_init` — crashing that call's startup instead of silently no-op'ing like the docstring implies.
**Fix:** Either serialize `init_db()` calls (e.g. a startup-time lock/flag) or make the seed insert itself race-safe with `INSERT OR IGNORE` / a single transaction with `BEGIN IMMEDIATE`.

### WR-05: SSE connection-status state machine can't distinguish "still retrying" from "permanently closed"

**File:** `frontend/lib/useSseStream.ts:51-55`
**Issue:** `source.onerror` unconditionally sets `status` to `"reconnecting"`, regardless of `source.readyState`. A native `EventSource` only fires `onerror` without ever retrying when it enters `readyState === EventSource.CLOSED` (e.g. the initial response isn't a `text/event-stream`, or the server sends a non-2xx status) — in that case the browser will never reconnect on its own, yet `ConnectionStatusDot` will show "Reconnecting" (yellow, `animate-pulse`) forever instead of "Disconnected" (red), actively misinforming the user about a state that requires a page reload to recover from. This is exactly the "does the connection status tell the truth" property `PriceStreamProvider`'s comment claims to care about.
**Fix:** Check `source.readyState` in the `onerror` handler; only set `"reconnecting"` when `readyState === EventSource.CONNECTING`, and set `"disconnected"` when `readyState === EventSource.CLOSED`.

### WR-06: Non-`ApiError` failures are re-thrown from an async event handler with no catch anywhere, silently dropping user feedback

**File:** `frontend/components/AddTickerForm.tsx:42-47`, `frontend/components/RemoveTickerButton.tsx:38-51`
**Issue:** Both handlers only set a user-visible `errorMessage` when the caught error is an `ApiError` (i.e. the fetch completed with a non-ok HTTP status). Any other failure — most notably a bare `fetch` network error (`TypeError: Failed to fetch` when offline, DNS failure, or a CORS preflight rejection) — falls into the `else { throw err; }` branch. Since this is inside an `async` function invoked from a DOM event handler (`onSubmit`/`onClick`), the re-thrown error becomes an unhandled promise rejection: nothing up the call chain catches it, React doesn't render an error boundary for it, and the user is left with a button that simply stops spinning (the `finally` block still resets `submitting`/`removing`) with zero indication that anything went wrong.
**Fix:** Treat any thrown error (not just `ApiError`) as user-facing-error-worthy — e.g. set a generic "network error, try again" message in the `else` branch instead of re-throwing — while still logging the original error for diagnostics.

## Info

### IN-01: `direction` prop on `WatchlistRow` is accepted but never read

**File:** `frontend/components/WatchlistRow.tsx:10,21`, `frontend/components/WatchlistPanel.tsx:104`
**Issue:** `WatchlistPanel` plumbs `prices[item.ticker]?.direction` (the server-computed tick direction from the SSE `PriceUpdate`) into `WatchlistRow`'s `direction` prop, but `WatchlistRow`'s destructured parameter list (`{ ticker, price, changePercent, points, removeControl }`) never includes `direction`, so the value is computed, passed, and dropped on the floor. The flash color is instead derived independently by comparing the new price to the component's own `previousPriceRef`. Functionally equivalent for now, but it's dead data flow that should either be removed or intentionally wired in.
**Fix:** Either delete the unused prop/type field and the value being passed for it, or use it explicitly (e.g. document why the local re-derivation is preferred over the server-provided value).

### IN-02: `TICKER_PATTERN` accepts shapes that aren't valid ticker symbols

**File:** `backend/app/routes/watchlist.py:26`
**Issue:** `^[A-Z0-9.\-]{1,10}$` permits values like `"-"`, `"."`, or `"--"` as "valid" tickers — not a security issue (still fully parameterized, still shape-bounded), but a validation gap: these will be accepted, persisted, and handed to the market-data source, which will presumably reject or mishandle them downstream.
**Fix:** Tighten the pattern to require at least one leading alphanumeric character, e.g. `^[A-Z][A-Z0-9.\-]{0,9}$`.

### IN-03: `DELETE /api/watchlist/{ticker}` path parameter has no declared length bound, unlike the POST body field

**File:** `backend/app/routes/watchlist.py:31,89`
**Issue:** `AddTickerRequest.ticker` is declared with `Field(min_length=1, max_length=10)`, giving Pydantic-level validation before `normalize_ticker` even runs. The DELETE route's `ticker: str` path parameter has no equivalent declared bound — it only gets bounded indirectly by `TICKER_PATTERN`'s `{1,10}` at the end of `normalize_ticker`. Functionally the outcome is the same (400 either way), but it's an inconsistency: one write path validates length before normalization, the other only after processing the full (unbounded) string.
**Fix:** Add `min_length=1, max_length=10` (or a `Path(...)` constraint) to the `ticker` path parameter for symmetry with the POST body validation.

---

_Reviewed: 2026-08-02T18:20:54Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
