---
phase: 01-live-market-terminal
fixed: 2026-08-02T19:00:00Z
review_ref: 01-REVIEW.md
findings_addressed: 9
findings_fixed: 9
findings_skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed:** 2026-08-02
**Source review:** [01-REVIEW.md](./01-REVIEW.md) (6 Warning, 3 Info, 0 Blocker)
**Status:** all 9 findings fixed

## Summary

All 6 Warnings and all 3 Info findings from the Phase 1 code review are fixed, verified, and committed. Backend fixes landed in `3b015c6` (8 new/updated tests, suite now 94/94 passing, up from 86; `ruff check` clean). Frontend fixes landed in `53bd94e` (`tsc --noEmit`, `eslint`, and `npm run build` all clean).

## Fixes Applied

### WR-01: Watchlist size cap check-then-act race — FIXED

**Commit:** `3b015c6`
`add_watchlist_ticker()` gained an optional `max_size` parameter that enforces the cap inside the same atomic statement as the insert (`INSERT ... SELECT ... WHERE (SELECT COUNT(*) ...) < max_size`), replacing the router's separate `count_watchlist()` read-then-insert. A blocked insert raises `WatchlistCapReachedError`, mapped to the same `400` the router previously returned directly. New test `test_concurrent_adds_never_exceed_cap` (`backend/tests/db/test_watchlist.py`) proves N concurrent callers racing against a cap of `baseline + 1` never let more than one succeed.

### WR-02: No compensation when market-source call fails after DB commit — FIXED

**Commit:** `3b015c6`
Both `add_ticker` and `remove_ticker` in `backend/app/routes/watchlist.py` now wrap the `market_source` call in `try/except`. On failure, `add_ticker` compensates by deleting the just-inserted row (`remove_watchlist_ticker`); `remove_ticker` compensates by re-adding the just-deleted row (uncapped, since it's restoring not net-adding). Both then return `502` rather than letting a raw exception surface, and both log via `logger.exception` for diagnosis.

### WR-03: Overly broad `except sqlite3.IntegrityError` — FIXED

**Commit:** `3b015c6`
`add_watchlist_ticker` now matches the specific UNIQUE-constraint message text before treating an `IntegrityError` as "duplicate ticker." Any other integrity violation is logged at `error` level with the original exception before still returning `None` (preserving the existing 409 behavior for genuine duplicates, but no longer silently misreporting an unrelated failure).

### WR-04: `init_db()` seed race — FIXED

**Commit:** `3b015c6`
The seed step now issues a single `INSERT OR IGNORE INTO users_profile (...)` instead of a separate `SELECT COUNT(*)` followed by an `INSERT`, checking `cursor.rowcount` to decide whether this call "won" the seed race before seeding the watchlist (also switched to `INSERT OR IGNORE`, for the same reason). Two concurrent `init_db()` calls can no longer both observe "unseeded" and both attempt the primary-key insert. New test in `backend/tests/db/test_init.py` exercises concurrent `init_db()` calls against the same file and asserts exactly one seed occurs with no unhandled exception.

### WR-05: SSE status can't distinguish "retrying" from "permanently closed" — FIXED

**Commit:** `53bd94e`
`usePriceStream`'s `onerror` handler now inspects `source.readyState`: `"disconnected"` when `readyState === EventSource.CLOSED` (the browser has given up and will never reconnect on its own), `"reconnecting"` otherwise. Previously every error unconditionally reported `"reconnecting"`, which could mislead the user into thinking recovery was imminent when only a page reload would help.

### WR-06: Unhandled non-`ApiError` promise rejections — FIXED

**Commit:** `53bd94e`
`AddTickerForm` and `RemoveTickerButton` both now show their existing user-facing error copy for *any* thrown error, not only `ApiError` — a bare network error (offline, DNS failure, CORS rejection) previously fell into an `else { throw err; }` branch that became an unhandled promise rejection with the button silently stopping its spinner and no error shown. The original error is still logged via `console.error` for diagnostics; user-facing behavior is now consistent regardless of failure type.

### IN-01: Unused `direction` prop — FIXED (removed)

**Commit:** `53bd94e`
Removed the dead `direction` prop from `WatchlistRow`'s interface and from `WatchlistPanel`'s pass-through — it was computed (`prices[item.ticker]?.direction`) and passed but never read inside `WatchlistRow` (the flash color is correctly derived locally from `previousPriceRef` comparison, as documented in the component's existing comment). Chose removal over wiring it in, since the local re-derivation is already the intended/correct behavior per the component's own doc comment.

### IN-02: Loose `TICKER_PATTERN` — FIXED

**Commit:** `3b015c6`
`TICKER_PATTERN` tightened from `^[A-Z0-9.\-]{1,10}$` to `^[A-Z][A-Z0-9.\-]{0,9}$`, requiring a leading alphanumeric character so bare punctuation (`"-"`, `"."`, `"--"`) can no longer pass as a "valid" ticker shape, while still permitting real tickers with embedded punctuation (e.g. `"BRK.B"`).

### IN-03: DELETE path parameter missing length bound — FIXED

**Commit:** `3b015c6`
The `DELETE /api/watchlist/{ticker}` route's `ticker` path parameter now declares `Path(min_length=1, max_length=10)`, matching the POST body's `Field(min_length=1, max_length=10)` for symmetric Pydantic-level validation before `normalize_ticker` runs.

## Verification

- **Backend:** `cd backend && uv run --extra dev pytest -q` → 94/94 passed (was 86; 8 new tests added for WR-01/WR-02/WR-04 coverage). `uv run --extra dev ruff check app/ tests/` → clean.
- **Frontend:** `cd frontend && npx tsc --noEmit` → clean. `npx eslint app components lib` → clean. `npm run build` → static export succeeds.

## Notes

The code-fixer agent that applied the backend fixes (WR-01..04, IN-02, IN-03) stalled mid-session after the fixes were already written and verified but before it committed or wrote this report — the orchestrator reviewed the uncommitted diff directly, confirmed correctness and clean test/lint results, and committed it (`3b015c6`). The frontend fixes (WR-05, WR-06, IN-01) were applied directly by the orchestrator after that stall, given their small, well-scoped nature.

---
*Phase: 01-live-market-terminal*
*Fixed: 2026-08-02*
