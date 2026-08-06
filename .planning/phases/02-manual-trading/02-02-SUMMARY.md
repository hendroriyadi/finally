---
phase: 02-manual-trading
plan: 02
subsystem: testing
tags: [pytest, asyncio, sqlite, decimal, concurrency, race-proof]

requires:
  - phase: 02-manual-trading
    provides: "execute_trade() / get_portfolio_state() / value_portfolio() from Plan 02-01 — the atomic buy/sell engine this plan proves against fresh-connection state"
provides:
  - "backend/tests/db/test_portfolio.py — TEST-01 proof suite: exact-value money math, full rejection-leaves-state-untouched coverage, and a four-test concurrency race proof modelled on test_concurrent_adds_never_exceed_cap"
affects: [02-03, 02-04, 03-portfolio-analytics, 04-ai-copilot]

actuals:
  tokens: 2927
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Fresh-connection _read_state((cash, position, trade_count)) tuple comparison as the single assertion covering all three invariants a rejection must leave untouched"
    - "Direct UPDATE/INSERT through connect() to seed cash/position state precisely for concurrency tests, bypassing execute_trade() so the seed itself never consumes the balance under test"
    - "Per-call coroutine catches the specific TradeRejectedError subclass only, never a bare or broad except, so a crashed engine cannot be mistaken for a clean rejection"

key-files:
  created:
    - backend/tests/db/test_portfolio.py
  modified: []

key-decisions:
  - "Chose starting_qty=35.0 (not 30.0) for the partial-sell concurrency test so the position affording exactly 3 of 20 concurrent 10-share sells leaves a non-zero remainder (5.0) rather than triggering the full-position-sell row-deletion path, keeping that test's assertion about a live quantity distinct from the separate full-sell-deletes-the-row test."
  - "All exact-value assertions use fixture prices/quantities (200.0, 100.0, 130.0, 0.5, 0.25, 10, 5, 50) chosen so every expected result — including the weighted-average-cost case (10*100+5*130)/15=110.0 — is exactly representable in binary floating point; zero pytest.approx uses were needed anywhere in the file."
  - "Committed Task 1 and Task 2 as two atomic commits against the same file (test file written incrementally: Task 1's content first, verified and committed alone with the then-unused asyncio import removed; Task 2's concurrency section and the asyncio import re-added and committed second), matching the plan's single-file files_modified list."

patterns-established:
  - "Pattern: mutation spot-check as an explicit, uncommitted verification step — temporarily reverting the guard under test to its racy check-then-act form to confirm the proof actually fails (12/20 buys succeeded against the racy version vs. the required 1/20), then reverting before committing. Recommended default whenever a race-proof test is authored, to avoid a 'test that would pass either way.'"

requirements-completed: [TEST-01, PORT-02, PORT-03, PORT-04]

coverage:
  - id: D1
    description: "Fractional-share buys and sells debit/credit cash by exactly quantity*price with no float drift, verified against a fresh connection rather than the call's return value"
    requirement: TEST-01
    verification:
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_fractional_buy_debits_exact_cash_and_creates_position"
        status: pass
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_fractional_sell_credits_exact_cash_and_reduces_quantity"
        status: pass
    human_judgment: false
  - id: D2
    description: "The exact-balance boundary is pinned on both sides: a buy spending the entire balance succeeds and lands on exactly 0.0, and one cent more raises InsufficientCashError and leaves state untouched"
    requirement: PORT-04
    verification:
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_buy_spending_exact_balance_succeeds_and_lands_on_zero"
        status: pass
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_buy_one_cent_over_balance_raises_and_leaves_state_untouched"
        status: pass
    human_judgment: false
  - id: D3
    description: "A second buy of a held ticker produces the exact weighted-average cost in a single updated row, not a second lot row"
    requirement: PORT-02
    verification:
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_second_buy_produces_exact_weighted_average_cost"
        status: pass
    human_judgment: false
  - id: D4
    description: "A full-position sell deletes the positions row entirely (asserted as absence, not a zero quantity); a partial sell leaves avg_cost byte-identical"
    requirement: PORT-03
    verification:
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_full_position_sell_leaves_no_row"
        status: pass
    human_judgment: false
  - id: D5
    description: "Insufficient-shares (oversell, unheld ticker) and no-cached-price rejections each raise the correct exception and leave cash, position, and trade count byte-identical to a fresh read taken immediately before the attempt"
    requirement: PORT-04
    verification:
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_oversell_raises_and_leaves_state_untouched"
        status: pass
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_sell_of_unheld_ticker_raises_and_leaves_state_untouched"
        status: pass
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_trade_with_no_cached_price_raises_and_leaves_state_untouched"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every successful buy/sell appends exactly one trades row with the right side, quantity, and price, read from a fresh connection"
    requirement: TEST-01
    verification:
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_trade_log_records_one_row_per_successful_trade"
        status: pass
    human_judgment: false
  - id: D7
    description: "Twenty concurrent buys against a balance affording exactly one produce exactly 1 fill, a non-negative final balance equal to the seed minus one fill, and a matching trades count — the double-spend race proof, and it is proven real via an uncommitted mutation spot-check that fails the same test against a racy check-then-act implementation"
    requirement: PORT-04
    verification:
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_concurrent_buys_never_overdraw_balance"
        status: pass
    human_judgment: false
  - id: D8
    description: "Twenty concurrent full sells against one lot, and twenty concurrent partial sells against a position affording exactly three, each produce exactly the fills the state could afford with a non-negative remainder and a matching trades count"
    requirement: PORT-04
    verification:
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_concurrent_full_sells_never_oversell"
        status: pass
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_concurrent_partial_sells_fill_exactly_what_position_affords"
        status: pass
    human_judgment: false
  - id: D9
    description: "A mixed gather of 10 concurrent buys and 10 concurrent sells against cash/position each affording one leaves cash and quantity non-negative and the trades count equal to the success count, asserting interleaving-independent invariants rather than a flaky exact final balance"
    requirement: PORT-04
    verification:
      - kind: unit
        ref: "backend/tests/db/test_portfolio.py::test_concurrent_mixed_buys_and_sells_keep_state_non_negative"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-08-03
status: complete
---

# Phase 2 Plan 2: Money-Math and Race-Safety Proof Suite for execute_trade() Summary

**Fourteen-test proof suite for `execute_trade()` covering exact-value money math, full-tuple rejection-untouched assertions, and a four-test twenty-caller concurrency race proof — verified against a deliberately racy check-then-act mutation to confirm the proof is real, not merely passing**

## Performance

- **Duration:** 20 min
- **Started:** 2026-08-03T13:20:00+07:00 (approximate, following 02-01's completion)
- **Completed:** 2026-08-03T13:40:00+07:00 (approximate)
- **Tasks:** 2 completed
- **Files modified:** 1 (new)

## Accomplishments

- Ten exact-value tests prove fractional buy/sell cash math, both sides of the exact-balance boundary (spend-all lands on exactly `0.0`; one cent more raises `InsufficientCashError`), weighted-average-cost recompute (`(10*100 + 5*130)/15 == 110.0` exactly, asserted alongside a single-row guard), full-position-sell row deletion (asserted as absence, not a zero quantity), and every rejection path (oversell, sell-of-unheld-ticker, no-cached-price) proven to leave the complete `(cash, position, trade_count)` tuple byte-identical to a fresh read taken immediately beforehand.
- Zero `pytest.approx` uses were needed anywhere in the file — fixture values were chosen so every expected result, including the weighted-average case, is exactly representable in binary floating point.
- Four concurrency tests race twenty `asyncio.gather`-launched `execute_trade()` calls against a purposely finite balance/position: concurrent buys, concurrent full sells, concurrent partial sells (affording exactly 3 of 20), and a mixed buy/sell gather asserting only interleaving-independent invariants (non-negativity, matching trade count) rather than a flaky exact final value.
- The race proof was verified to be real, not just passing: the buy guard was temporarily reverted from its atomic `UPDATE ... WHERE ... >= ?` form to a separate `SELECT`-then-conditional-`UPDATE` (the exact check-then-act shape PORT-04 exists to prevent), which made `test_concurrent_buys_never_overdraw_balance` fail with 12 fills instead of 1 — then reverted before committing (`git diff --stat` confirmed `portfolio.py` was byte-identical to its pre-mutation state).
- Full backend suite (124 tests, including this plan's 14) passes; `tests/db/test_portfolio.py` was run three consecutive times with no flakiness.

## Task Commits

1. **Task 1: Money math and state integrity — the exact-value suite** - `111f329` (test)
2. **Task 2: The race proof — twenty callers, one finite balance** - `47ba96d` (test)

## Files Created/Modified

- `backend/tests/db/test_portfolio.py` - `_FixedPriceCache` (deterministic price double), `_read_state()` (fresh-connection state reader), `_set_cash_balance()`/`_seed_position()` (direct-write seed helpers for concurrency tests), 10 exact-value tests, and 4 concurrency race-proof tests

## Decisions Made

- Combined each rejection's "raises the right exception" and "leaves state untouched" behavior into a single test function (capturing `before = _read_state(...)` immediately prior to the attempt) rather than writing them as separate tests, since the plan's acceptance criteria require every rejection test to compare the complete tuple before and after — this avoids redundant duplicate-exception tests while still satisfying both the boundary-pair requirement and the untouched-state requirement.
- Chose `starting_qty = 35.0` for the partial-sell concurrency test (not `30.0`) so that after 3 successful 10-share sells, 5.0 shares remain — keeping this test's "non-negative remainder" assertion distinct from, and not accidentally overlapping with, the separate full-position-sell-deletes-the-row test.
- Wrote and verified Task 1 in isolation first (temporarily without the `asyncio` import, since it would otherwise be unused and fail `ruff check`), committed it alone, then re-added the concurrency section and the `asyncio` import for Task 2's commit — matching the plan's single-file `files_modified` list while keeping each task's commit atomic and independently verifiable.

## Deviations from Plan

None - plan executed exactly as written. No production code was touched (this plan adds tests only), and the one temporary edit to `backend/app/db/portfolio.py` (the mutation spot-check explicitly called for in the plan's `<verification>` section) was reverted before any commit, confirmed via `git diff --stat` showing no changes to that file.

## Issues Encountered

None. The mutation spot-check produced the expected failure signature (12/20 fills against the racy implementation vs. 1/20 required), confirming the race-proof tests are load-bearing rather than tests that would pass regardless of the guard's correctness.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `execute_trade()`'s atomic guard behavior is now proven under load, not just asserted by inspection — this is the regression gate for T-02-01/T-02-02 identified in the phase's threat model, and the same `_FixedPriceCache`/`_read_state`/seed-helper pattern is available for Plans 02-03/02-04 or any future test needing precise, engine-bypassing state seeding.
- No blockers. Full backend suite is green (124 passed) after this plan.

---
*Phase: 02-manual-trading*
*Completed: 2026-08-03*

## Self-Check: PASSED

- FOUND: backend/tests/db/test_portfolio.py
- FOUND: .planning/phases/02-manual-trading/02-02-SUMMARY.md
- FOUND: commit 111f329
- FOUND: commit 47ba96d
