---
phase: 02-manual-trading
plan: 01
subsystem: api
tags: [fastapi, pydantic, sqlite, decimal, atomic-transactions]

requires:
  - phase: 01-live-market-terminal
    provides: PriceCache (app.state.price_cache), watchlist's normalize_ticker/TICKER_PATTERN, run_db() atomic-guard-plus-rowcount idiom, schema.sql's positions/trades/users_profile tables
provides:
  - execute_trade() — the single entry point for every mutation of cash, positions, and trade history
  - get_portfolio_state() / value_portfolio() — the read side both this phase's UI and Phase 4's copilot context will consume
  - GET /api/portfolio and POST /api/portfolio/trade HTTP surfaces
affects: [02-02, 02-03, 02-04, 03-portfolio-analytics, 04-ai-copilot]

actuals:
  tokens: 6877
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Atomic sufficiency guard: UPDATE ... WHERE <guard> checked via cursor.rowcount, never a separate SELECT-then-UPDATE (buy's cash guard and sell's share guard both follow this, mirroring add_watchlist_ticker's max_size pattern from Phase 1)"
    - "Decimal(str(value)) at every arithmetic entry point, float(...) only at the SQLite REAL write boundary and the dict/response-model construction boundary"
    - "Single-entry-point mutation: execute_trade() is the only function in the codebase permitted to touch users_profile.cash_balance, positions, or trades"
    - "Full-position sell deletes the positions row (exact Decimal-zero comparison, no tolerance window) rather than leaving a phantom quantity=0 row"

key-files:
  created:
    - backend/app/db/portfolio.py
    - backend/app/routes/portfolio.py
    - backend/tests/routes/test_portfolio.py
  modified:
    - backend/app/main.py

key-decisions:
  - "Combined multi-line SQL string literals into single-line statements in _apply_buy and _apply_sell so the plan's grep-based verify gates (which match a single continuous substring) pass; ruff's 100-char line-length limit was not exceeded, so no readability tradeoff was needed."
  - "Wrote the test file's Task 1 and Task 2 coverage as one incrementally-built file (Task 1 tests committed first with only the buy path testable, Task 2 tests appended once the sell path existed), matching the plan's file_modified list of exactly one test file for the whole plan."

patterns-established:
  - "Pattern 1: description — atomic-guard-plus-rowcount pattern is now used identically in two places (watchlist cap, portfolio cash/shares) and should be the default answer whenever a future check-then-act race is spotted in this codebase"
  - "Pattern 2: description — fresh-connection state assertions (not the HTTP response body) are the required proof style for every rejection-leaves-state-untouched test in this codebase"

requirements-completed: [PORT-01, PORT-02, PORT-03, PORT-04, PORT-05]

coverage:
  - id: D1
    description: "A buy fills instantly at the live cached price, debits cash by exactly quantity*price, and creates/updates a position via weighted-average cost"
    requirement: PORT-02
    verification:
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_buy_returns_200_and_debits_cash_exactly"
        status: pass
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_second_buy_of_same_ticker_produces_weighted_average_cost"
        status: pass
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_fractional_buy_debits_exactly_half"
        status: pass
    human_judgment: false
  - id: D2
    description: "A sell fills instantly, credits proceeds, and either reduces quantity in place (leaving avg_cost unchanged) or deletes the position row on a full sell"
    requirement: PORT-03
    verification:
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_partial_sell_reduces_quantity_and_leaves_avg_cost_unchanged"
        status: pass
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_full_sell_removes_position_row_and_returns_null_position"
        status: pass
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_fractional_sell_credits_exactly_the_proceeds"
        status: pass
    human_judgment: false
  - id: D3
    description: "Trade execution atomically rejects insufficient cash, insufficient shares, and missing-price trades, leaving cash/positions/trade history byte-identical (verified from a fresh connection)"
    requirement: PORT-04
    verification:
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_oversized_sell_returns_409_and_leaves_state_byte_identical"
        status: pass
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_sell_of_unheld_ticker_returns_409_and_writes_nothing"
        status: pass
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_buy_exceeding_cash_returns_409_and_appends_no_trade_row"
        status: pass
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_trade_with_no_cached_price_returns_400_and_writes_nothing"
        status: pass
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_malformed_trade_body_returns_422_before_the_engine_runs"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /api/portfolio reports cash, total value, and per-position quantity/avg_cost/current_price/unrealized_pnl/change_percent, tolerating a ticker with no cached price"
    requirement: PORT-01
    verification:
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_get_portfolio_after_buy_reports_valued_position"
        status: pass
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_position_with_no_cached_price_reports_nulls_and_still_contributes_cost_basis"
        status: pass
    human_judgment: false
  - id: D5
    description: "Every money value crosses the wire as a JSON number, never a string, even though all engine arithmetic is Decimal"
    requirement: PORT-05
    verification:
      - kind: unit
        ref: "backend/tests/routes/test_portfolio.py::test_money_values_are_json_numbers_not_strings"
        status: pass
    human_judgment: false

duration: 27min
completed: 2026-08-03
status: complete
---

# Phase 2 Plan 1: Trade Engine and Portfolio Read Side Summary

**Single-entry-point `execute_trade()` (buy + sell, Decimal-precise, atomically-guarded) plus `GET /api/portfolio` and `POST /api/portfolio/trade` with float-only wire types**

## Performance

- **Duration:** 27 min (resumed session; Task 1's production code was already written by a prior run cut off by a transient API error, and was verified/completed here rather than rewritten)
- **Started:** 2026-08-03T12:49:35+07:00 (prior commit baseline)
- **Completed:** 2026-08-03T13:16:34+07:00
- **Tasks:** 2 completed
- **Files modified:** 4 (3 new, 1 modified)

## Accomplishments

- `execute_trade()` is now the sole mutation path for `users_profile.cash_balance`, `positions`, and `trades` — buy and sell both implemented, both guarded by a single atomic `UPDATE ... WHERE <sufficiency guard>` statement checked via `cursor.rowcount`, with zero separate SELECT-then-UPDATE checks anywhere in the module.
- `GET /api/portfolio` values every open position against the live `PriceCache`, tolerating a ticker with no cached price by falling back to cost basis for total-value purposes and reporting null P&L fields instead of crashing.
- Every wire-facing numeric field is `float`-typed and converted from `Decimal` at construction; a dedicated test parses the raw JSON body and asserts `isinstance(..., float)` rather than trusting the Pydantic model's Python-side type.
- Full-position sells delete the `positions` row (exact-Decimal-zero comparison); partial sells leave `avg_cost` untouched.
- Every rejection path (insufficient cash, insufficient shares, no cached price) is proven to leave cash, the position row, and the `trades` count byte-identical via a fresh `sqlite3.connect()`-based read, not the HTTP response.

## Task Commits

1. **Task 1: One buy, end to end — HTTP request through the atomic cash guard and back out as a valued position** - `a8573a5` (feat)
2. **Task 2: Sell, reject, and hold the wire boundary — the paths that must leave no trace when they fail** - `2b72924` (feat)

_Note: This plan resumed a prior run that was cut off mid-Task-1 by a transient API connection error. Task 1's production code (`backend/app/db/portfolio.py`, `backend/app/routes/portfolio.py`, the `main.py` router mount) was already written and uncommitted on disk when this session began; it was read, verified against the plan's acceptance criteria, and found correct except for a grep-format issue (see Deviations). The missing test file was then written and Task 1 was committed as a single atomic commit, exactly as if it had been executed in one pass._

## Files Created/Modified

- `backend/app/db/portfolio.py` - `execute_trade()` (buy + sell), `_apply_buy`/`_apply_sell` atomic guards, `_upsert_position_on_buy` weighted-avg-cost, `get_portfolio_state()`, `value_portfolio()`, and the four `TradeRejectedError` subclasses
- `backend/app/routes/portfolio.py` - `GET /api/portfolio`, `POST /api/portfolio/trade`, float-typed Pydantic models, full exception-to-status-code mapping (400/409)
- `backend/app/main.py` - mounts `create_portfolio_router()`
- `backend/tests/routes/test_portfolio.py` - 16 tests covering buy, weighted-avg-cost, fractional trades, sell (partial/full/fractional), all four rejection paths (fresh-connection state-untouched proof), 422 validation, and the JSON-number wire boundary

## Decisions Made

- Combined the buy and sell atomic-guard SQL statements from two adjacent string-literal lines into a single line each, so the plan's grep-based verify gates (which require the exact SQL text as one continuous substring) pass. This is a pure formatting change with no behavioral difference; ruff's 100-character line-length limit was not exceeded either way.
- Task 1's test file was written to cover exactly Task 1's scope (buy path, `GET /api/portfolio`, JSON-number boundary) and committed alone; Task 2's sell/rejection tests were appended to the same file afterward — matching the plan's `files_modified` list, which names one test file for the whole plan rather than two.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Buy and sell atomic-guard SQL statements failed the plan's grep verify gates due to line-splitting**
- **Found during:** Task 1 verification (and again during Task 2 verification for the sell guard)
- **Issue:** The prior run's uncommitted code wrote the cash-guard and share-guard `UPDATE` statements as two adjacent Python string literals across two source lines (e.g. `"UPDATE users_profile SET cash_balance = cash_balance - ? " "WHERE id = ? AND cash_balance >= ?"`). The plan's `<verify>` block greps for the exact SQL text as one continuous substring on a single line; grep matches per-line by default, so the split literal never matched even though the resulting SQL string was byte-identical at runtime.
- **Fix:** Joined each pair of string literals onto one line in `_apply_buy` and `_apply_sell`. No logic change — `ruff check` confirms the resulting lines stay within the project's 100-character limit.
- **Files modified:** `backend/app/db/portfolio.py`
- **Verification:** `grep -q 'cash_balance = cash_balance - ? WHERE id = ? AND cash_balance >= ?' app/db/portfolio.py` and the equivalent sell-guard grep both pass; `ruff check` and the full test suite (110 passed) confirm no behavioral regression.
- **Committed in:** `a8573a5` (buy guard), `2b72924` (sell guard)

---

**Total deviations:** 1 auto-fixed (1 bug — verify-gate-only formatting issue, no runtime behavior change)
**Impact on plan:** Zero functional impact. No scope creep.

## Issues Encountered

None beyond the deviation above. The prior run's production code for Task 1 (`execute_trade()` buy path, `get_portfolio_state()`, `value_portfolio()`, the route handlers, and the `main.py` mount) was read in full and found to already satisfy every one of Task 1's acceptance criteria — no rewrite was needed, only the missing test file and the grep-format fix.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `execute_trade()`, `get_portfolio_state()`, and `value_portfolio()` are stable, tested, and ready to be called unchanged by Phase 4's AI copilot (CHAT-03) and by Plans 02-02/02-03/02-04's frontend trade bar and positions table.
- `GET /api/portfolio`'s response shape (`cash_balance`, `total_value`, `positions[]` with `current_price`/`unrealized_pnl`/`change_percent`) is the exact contract Phase 3's heatmap and P&L chart will read.
- No blockers. Full backend test suite is green (110 passed) after this plan.

---
*Phase: 02-manual-trading*
*Completed: 2026-08-03*
