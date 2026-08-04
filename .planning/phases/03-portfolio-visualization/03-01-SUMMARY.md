---
phase: 03-portfolio-visualization
plan: 01
subsystem: database
tags: [sqlite, fastapi, asyncio, background-task]

requires:
  - phase: 02-manual-trading
    provides: get_portfolio_state() and value_portfolio() from app/db/portfolio.py, reused unmodified as the sole valuation path
provides:
  - "record_portfolio_snapshot() / list_snapshots() (app/db/snapshots.py) — the first writer/reader of portfolio_snapshots"
  - "GET /api/portfolio/history — {snapshots: [...]} oldest-first, server-bounded at 500 rows, no client-controlled input"
  - "SnapshotRecorder (app/snapshot_task.py) — 30-second lifespan-managed periodic writer, mirroring SimulatorDataSource's start/stop/_run_loop shape"
  - "Post-trade snapshot recorded in POST /api/portfolio/trade, guarded so a snapshot failure never fails an already-filled trade"
affects: [03-02-portfolio-visualization, 04-ai-copilot]

actuals:
  tokens: 9000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "SnapshotRecorder.start() awaits its first tick synchronously before spawning the background loop task, rather than leaving the first write to the loop's first iteration — deliberate deviation from the plan's literal 'work first, then sleep inside the loop' phrasing, made to close a real race (see Deviations)"

key-files:
  created: [backend/app/db/snapshots.py, backend/app/snapshot_task.py, backend/tests/db/test_snapshots.py]
  modified: [backend/app/routes/portfolio.py, backend/app/main.py, backend/tests/routes/test_portfolio.py]

key-decisions:
  - "record_portfolio_snapshot()'s initial call is awaited inside SnapshotRecorder.start() (before the background task is created), not left as the loop's first iteration — see Deviations"
  - "app/db/snapshots.py writes exactly one table (portfolio_snapshots); execute_trade() gained no snapshot call, keeping it the sole mutator of cash/positions/trades for Phase 4's CHAT-03 contract"

patterns-established:
  - "Lifespan-managed background task pairs an awaited one-shot 'do it now' call in start() with a sleep-then-tick loop for subsequent iterations, when the caller needs the first side effect to be deterministic relative to request handling (e.g. under TestClient)"

requirements-completed: [PORT-06, PORT-07]

coverage:
  - id: D1
    description: "A portfolio_snapshots row is written every 30 seconds by a lifespan-managed task, and another immediately after every successful trade, from two independent triggers"
    requirement: PORT-06
    verification:
      - kind: unit
        ref: "backend/tests/db/test_snapshots.py#test_recorder_writes_more_than_one_row_over_time"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_portfolio.py#test_successful_buy_increases_snapshot_count_by_exactly_one"
        status: pass
    human_judgment: false
  - id: D2
    description: "The snapshot writer reuses get_portfolio_state()/value_portfolio() and introduces no second valuation path; execute_trade() remains the sole mutator of cash/positions/trades"
    requirement: PORT-06
    verification:
      - kind: unit
        ref: "grep -cE '\"(INSERT INTO|UPDATE|DELETE FROM) +(users_profile|positions|trades)\\b' backend/app/db/snapshots.py -> 0"
        status: pass
    human_judgment: false
  - id: D3
    description: "GET /api/portfolio/history returns {snapshots: [...]} oldest-first, bounded server-side at 500, with no client-controlled input"
    requirement: PORT-07
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_portfolio.py#test_history_after_two_trades_returns_both_oldest_first"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_portfolio.py#test_history_total_value_is_a_json_number_not_a_string"
        status: pass
    human_judgment: false
  - id: D4
    description: "A failing snapshot write neither kills the recorder nor fails the trade that triggered it"
    requirement: PORT-06
    verification:
      - kind: unit
        ref: "backend/tests/db/test_snapshots.py#test_a_failing_iteration_does_not_kill_the_loop"
        status: pass
    human_judgment: false
  - id: D5
    description: "History written before a restart is readable after it, proven from a connection independent of the writer"
    requirement: PORT-06
    verification:
      - kind: unit
        ref: "backend/tests/db/test_snapshots.py#test_snapshots_survive_a_fresh_independent_connection"
        status: pass
    human_judgment: false

duration: unknown (resumed mid-plan after a session-limit interruption; original Task 1 start time not recorded)
completed: 2026-08-04
status: complete
---

# Phase 3, Plan 01: Portfolio Snapshot Writer + History Endpoint Summary

**Durable `portfolio_snapshots` writer (30s timer + post-trade trigger) and `GET /api/portfolio/history`, giving the portfolio a persisted value-over-time record for Plan 03-02's P&L chart.**

## Performance

- **Tasks:** 2 completed
- **Files modified:** 6 (3 created, 3 modified)
- **Note:** execution spanned a session interruption (background executor hit a usage limit mid-Task-1, right before its commit). Task 1's uncommitted work was reviewed against this plan's acceptance criteria, verified, and committed as-is; Task 2 was then written and verified directly.

## Accomplishments
- `app/db/snapshots.py`: `record_portfolio_snapshot()` and `list_snapshots()`, the sole reader/writer of `portfolio_snapshots`, reusing Phase 2's `get_portfolio_state()`/`value_portfolio()` for valuation
- `GET /api/portfolio/history` returns `{"snapshots": [...]}` oldest-first, capped at `MAX_HISTORY_POINTS = 500`, no query parameters
- `POST /api/portfolio/trade` records a snapshot immediately after a successful fill, guarded so a snapshot failure can't turn a filled trade into an error response
- `SnapshotRecorder` (`app/snapshot_task.py`) records a snapshot every 30 seconds via `main.py`'s lifespan, independent of the trade-triggered path, and survives a failing iteration
- 30 new tests (21 pre-existing + 9 new in `test_portfolio.py`'s snapshot section, 9 new in `test_snapshots.py`) — full backend suite (142 tests) green across repeated runs

## Task Commits

1. **Task 1: One snapshot, end to end** - `83f2c4d` (feat) — recovered from a stalled background executor's uncommitted work, reviewed against acceptance criteria, verified, committed as-is with no changes needed
2. **Task 2: The 30-second recorder** - `1b1b0be` (feat) — written directly (not via subagent, after two consecutive executor session-limit stalls on this plan), includes a deviation fix (see below)

## Files Created/Modified
- `backend/app/db/snapshots.py` - `record_portfolio_snapshot()`, `list_snapshots()`, `MAX_HISTORY_POINTS`
- `backend/app/snapshot_task.py` - `SnapshotRecorder` (start/stop/_tick/_run_loop), `SNAPSHOT_INTERVAL_SECONDS`
- `backend/app/routes/portfolio.py` - `SnapshotOut`, `PortfolioHistoryResponse`, `GET /history`, post-trade snapshot call
- `backend/app/main.py` - lifespan starts/stops `SnapshotRecorder` alongside the market source
- `backend/tests/routes/test_portfolio.py` - snapshot-count delta tests, history endpoint tests
- `backend/tests/db/test_snapshots.py` - writer/reader tests, restart-durability test, recorder lifecycle tests

## Decisions Made
- Task 1's committed code was accepted as-is after independent verification (lint, targeted tests, all 6 grep-based acceptance criteria from the plan) rather than re-run through a fresh executor — matches this session's established recovery pattern for interrupted-but-already-correct work.
- `SnapshotRecorder.start()` awaits one `record_portfolio_snapshot()` call synchronously before creating the background loop task (see Deviations) — a targeted fix to a race the plan's literal instructions would have reproduced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Correctness] `SnapshotRecorder`'s startup snapshot raced with the first test request**
- **Found during:** Task 2, first full-suite run after wiring the recorder into `main.py`'s lifespan
- **Issue:** The plan's Task 2 action text specifies "work first, then sleep" *inside* `_run_loop`, with the first write left to the loop's first iteration as a fire-and-forget `asyncio.Task`. Under `TestClient`, that task's first iteration doesn't necessarily run during lifespan startup — it can run during whichever later `await` point the event loop next visits, which in practice was the *first client request* of each test. This intermittently added +1 to `portfolio_snapshots` mid-request, breaking Task 1's delta-based snapshot-count assertions (`test_successful_buy_increases_snapshot_count_by_exactly_one`, `test_rejected_trade_adds_no_snapshot_row`) roughly 1 in 3 runs.
- **Fix:** Split the single write into a `_tick()` helper (try/except + the actual write) called from two places: once, awaited directly inside `start()` before the background task is created (so the startup snapshot lands deterministically during lifespan startup, before any request is served), and then repeatedly from `_run_loop`, which now sleeps first and ticks second since the immediate point is already covered by `start()`. Behavior (one point recorded immediately at startup, then every `SNAPSHOT_INTERVAL_SECONDS` after) is unchanged; only the mechanism providing the *deterministic timing* of that first point changed.
- **Files modified:** `backend/app/snapshot_task.py`
- **Verification:** `tests/routes/test_portfolio.py` + `tests/db/test_snapshots.py` run 8 consecutive times with zero failures (previously failed roughly 1 in 3 runs); full suite (142 tests) run 3 consecutive times, all green.
- **Committed in:** `1b1b0be` (Task 2 commit — the fix was applied before the task was ever committed, so there is no separate fix commit)

---

**Total deviations:** 1 auto-fixed (correctness — a genuine race, not a plan ambiguity)
**Impact on plan:** All of the plan's acceptance criteria and threat-model mitigations (T-03-01 through T-03-08) remain satisfied; the fix changes only *when* the first tick fires relative to task creation, not the shape of `SnapshotRecorder`'s public interface or its `_run_loop`'s try/except/sleep structure that the plan's grep-based verification checks.

## Issues Encountered
- Two consecutive background-executor dispatches for this plan hit the session usage limit mid-task (one right before Task 1's commit, one before Task 2 started). Both were resolved by doing the work directly rather than re-dispatching a third time, consistent with this session's established pattern after 2-3 failed subagent attempts on the same task.

## Next Phase Readiness
- The `{"snapshots": [...]}` wire contract (`total_value: float`, `recorded_at: str`, oldest-first) is live and stable — Plan 03-02's `PnLChart` can fetch it immediately.
- No blockers for Plan 03-02. Its Task 1 blocking human-verify checkpoint (the new `recharts` frontend dependency) remains outstanding and is pre-approved per `03-CONTEXT.md`/`03-RESEARCH.md`'s package-legitimacy research (54.8M weekly downloads, official `recharts/recharts` repo, React 19 peer-dep support).

---
*Phase: 03-portfolio-visualization*
*Completed: 2026-08-04*
