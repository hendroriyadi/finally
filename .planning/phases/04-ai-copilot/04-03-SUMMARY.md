---
phase: 04-ai-copilot
plan: 03
subsystem: api
tags: [fastapi, watchlist, refactor, llm]

requires:
  - phase: 04-ai-copilot
    provides: "ActionResult / _execute_trade_action shape and the mock's watchlist-change emission (Plan 04-01); the POST /api/chat handler and its persistence (Plan 04-02)"
  - phase: 01-live-market-terminal
    provides: "add_watchlist_ticker/remove_watchlist_ticker, normalize_ticker, TICKER_PATTERN, MAX_WATCHLIST_SIZE, and the market_source add/remove lifecycle"
provides:
  - "apply_watchlist_add()/apply_watchlist_remove() — the single copy of the persist-then-track-then-compensate sequence, called by both the HTTP handlers and the chat executor"
  - "DuplicateTickerError / TickerNotOnWatchlistError / MarketSourceSyncError — purpose-named errors replacing HTTPException at the helper boundary"
  - "_execute_watchlist_action() — AI-initiated watchlist add/remove with per-action error containment"
affects: [04-04-ai-copilot, 05-one-command-ship]

actuals:
  tokens: 12000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "A route module may export async helpers that own a multi-step side-effect sequence (DB mutation + external-system sync + compensating rollback), with the HTTP handler reduced to a normalize-call-translate shell — so a second in-process caller runs identical logic instead of a hand-copied approximation"

key-files:
  created: []
  modified: [backend/app/routes/watchlist.py, backend/app/routes/chat.py, backend/tests/routes/test_watchlist.py, backend/tests/routes/test_chat.py]

key-decisions:
  - "Helpers raise purpose-named exceptions rather than HTTPException, so the chat caller never unwraps a web-framework type to build a transcript sentence"
  - "WatchlistCapReachedError is re-exported through app.routes.watchlist so all four helper-raisable errors are importable from one module (see Deviations)"

patterns-established:
  - "Mutation spot-check as proof-of-test-value: temporarily breaking the behavior under test and observing the specific failure, then restoring — the same technique Phase 2 used to prove its concurrency race test was real"

requirements-completed: [CHAT-04]

coverage:
  - id: D1
    description: "The assistant can add and remove watchlist tickers, and each change updates both the persisted list and the live market source"
    requirement: CHAT-04
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_mock_triggered_watchlist_add_starts_the_price_feed"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_mock_triggered_watchlist_remove_deletes_row_and_stops_the_feed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Chat-initiated and form-initiated watchlist changes run the same code, including the compensating rollback"
    requirement: CHAT-04
    verification:
      - kind: unit
        ref: "backend/tests/routes/test_watchlist.py#test_apply_add_compensates_when_starting_the_feed_fails (+ 6 sibling helper tests)"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_watchlist.py — all 11 pre-existing route tests pass with no test function edited"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every watchlist rejection returns HTTP 200 with a sentence identical to the one the manual UI shows, and never blocks a trade in the same reply"
    requirement: CHAT-04
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_adding_an_already_listed_ticker_returns_200_with_the_forms_error_copy"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_a_watchlist_failure_does_not_prevent_a_trade_in_the_same_reply"
        status: pass
    human_judgment: false

duration: ~20min
completed: 2026-08-04
status: complete
---

# Phase 4, Plan 03: Shared Watchlist Helpers + AI Curation Summary

**The insert-then-start-feed sequence (and its compensating rollback) now exists once and has two callers — the form and the assistant — so a ticker the AI adds actually streams a price instead of sitting in the database with an empty price cell.**

## Performance

- **Tasks:** 2 completed
- **Files modified:** 4
- **Tests:** 209 backend tests passing (was 200 after Task 1, 193 entering this plan)
- **Note:** executed directly by the orchestrator rather than a subagent — two consecutive executor dispatches for this wave failed on a session usage limit, and the established recovery pattern after repeated subagent failure on the same task is to do it inline.

## Accomplishments
- `apply_watchlist_add()` / `apply_watchlist_remove()` extracted into `backend/app/routes/watchlist.py`, owning the atomic capped insert (or delete), the market-source sync, and the compensating rollback if that sync fails
- Three purpose-named exceptions (`DuplicateTickerError`, `TickerNotOnWatchlistError`, `MarketSourceSyncError`) under a shared `WatchlistActionError` base, replacing `HTTPException` at the helper boundary
- Both HTTP write handlers reduced to normalize → call helper → map exception to status, with every status code and detail string preserved character for character
- `_execute_watchlist_action()` in the chat route, mirroring `_execute_trade_action()`'s shape, with per-action containment and a catch-all so no failure mode escapes as a 5xx
- The POST handler's two loops now feed one ordered action list, so a reply doing both a trade and a watchlist change reports both
- 16 new tests (7 helper-level, 9 chat-integration)

## Task Commits

1. **Task 1: Extract the persist-then-track helpers** - `0fa38be` (refactor)
2. **Task 2: The assistant curates the watchlist** - `a1e5a3f` (feat)

## Files Created/Modified
- `backend/app/routes/watchlist.py` - helpers, three exception types, handlers reduced to translators
- `backend/app/routes/chat.py` - `_execute_watchlist_action`, `_watchlist_error`, second loop in the POST handler
- `backend/tests/routes/test_watchlist.py` - 7 appended helper tests (no existing test edited)
- `backend/tests/routes/test_chat.py` - 9 appended chat-integration tests

## Decisions Made
- Ran a **mutation spot-check** on the plan's central claim rather than trusting the test's name: stubbed out `market_source.add_ticker` inside `apply_watchlist_add` and confirmed `test_mock_triggered_watchlist_add_starts_the_price_feed` fails with `assert None is not None` on the price lookup — exactly Pitfall 2's symptom — then restored the implementation and re-verified. Without this the test could have been passing vacuously (it does not: PYPL is absent from `SEED_PRICES`, so its price can only exist if the market source was actually told to track it).

## Deviations from Plan

### Auto-fixed Issues

**1. [Unsatisfiable acceptance criterion] `grep app.db.watchlist imports in chat.py returns 0`**
- **Found during:** Task 2, running the plan's own automated verify block
- **Issue:** The criterion was already false before this task began. Plan 04-02 (already committed) imports `list_watchlist` from `app.db.watchlist` in `chat.py` to build the CHAT-02 prompt context — a read, not a mutation. The plan's Task 2 action text also directly contradicts the criterion, instructing "import the cap error from where it is defined" (which is `app.db.watchlist`). Verified the pre-existing state with `git show 717962a:backend/app/routes/chat.py | grep 'app.db.watchlist'` → one hit, from 04-02.
- **Fix:** Satisfied the criterion's *stated intent* — "The chat route reaches the watchlist only through the shared helpers" — rather than its literal grep. `WatchlistCapReachedError` is now imported from `app.routes.watchlist` (which already imports it), so all four helper-raisable errors come from one module; `chat.py` imports **no** watchlist mutation function; and the surviving `list_watchlist` import carries an inline comment explaining why a read is not the thing the criterion guards against. Verified with a corrected gate: `grep -cE 'app\.db\.watchlist import.*(add_watchlist_ticker|remove_watchlist_ticker)' → 0`, and the existing `no SQL in chat.py` gate still returns 0.
- **Files modified:** `backend/app/routes/chat.py`
- **Verification:** 209/209 tests pass; `ruff check` clean; both intent-level gates green.
- **Committed in:** `a1e5a3f` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (an unsatisfiable acceptance criterion, resolved to its documented intent)
**Impact on plan:** No functional change. Every threat-model mitigation (T-04-15 through T-04-20) holds, including T-04-20's "no rule one path enforces and the other misses" — which is enforced by the mutation-function gate, not by the read-import gate.

## Issues Encountered
- Two consecutive `gsd-executor` dispatches for this wave (04-03 and its 04-04 sibling) failed on a session usage limit. The 04-03 attempt had written only a docstring paragraph before failing; that partial edit was kept and built on. Both plans were then executed inline by the orchestrator.

## Next Phase Readiness
- Plan 04-04 (the chat panel UI) can proceed: `POST /api/chat` now returns watchlist action results alongside trade results in one `actions` array, and `GET /api/chat/history` replays both — the frontend renders one card component for both kinds, branching on `kind`.

---
*Phase: 04-ai-copilot*
*Completed: 2026-08-04*
