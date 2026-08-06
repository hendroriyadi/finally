---
phase: 01-live-market-terminal
plan: 04
subsystem: ui
tags: [react, nextjs, forms]

requires:
  - phase: 01-live-market-terminal (plan 01)
    provides: "POST /api/watchlist, DELETE /api/watchlist/{ticker} REST contract"
  - phase: 01-live-market-terminal (plan 02)
    provides: "addWatchlistTicker/removeWatchlistTicker typed fetch wrappers, WatchlistPanel/WatchlistRow"
  - phase: 01-live-market-terminal (plan 03)
    provides: "live-priced WatchlistRow consuming the shared SSE stream"
provides:
  - "AddTickerForm: input + submit with real empty/in-flight/error/long-text states, wired to POST /api/watchlist"
  - "RemoveTickerButton: per-row remove control, non-optimistic (row removed only after DELETE succeeds), 44px tablet hit target, no confirmation dialog"
  - "WatchlistPanel/WatchlistRow updated to own add/remove state and render the remove control in a fixed-width cell"
affects: [phase-02-manual-trading, phase-03-portfolio-visualization]

actuals:
  tokens: 6500
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Non-optimistic mutation pattern: onRemoved()/item-added callback fires only after the awaited fetch resolves, never before — so client state can't diverge from the server on failure"
    - "In-flight disable + auto-clearing inline error (~4s timer, cleaned up on unmount) for both add and remove controls"

key-files:
  created:
    - frontend/components/AddTickerForm.tsx
    - frontend/components/RemoveTickerButton.tsx
  modified:
    - frontend/components/WatchlistPanel.tsx
    - frontend/components/WatchlistRow.tsx

key-decisions:
  - "Remove control renders in a fixed-width fifth cell on WatchlistRow so its presence never reflows the ticker/price/change/sparkline columns"
  - "Emptying the watchlist relies on the panel's existing items.length===0 branch (from Plan 02) rather than a second empty-state code path — verified this falls through correctly rather than adding new code"

patterns-established:
  - "Every state-mutating control (add, remove) follows the same shape: disable while in-flight, catch ApiError specifically, show scoped inline error copy, auto-clear after ~4s"

requirements-completed: [WATCH-02, WATCH-03, UI-01]

coverage:
  - id: D1
    description: "User adds a ticker from the browser; it joins the grid, persists across refresh/restart, and starts streaming without a restart"
    requirement: "WATCH-02"
    verification:
      - kind: unit
        ref: "cd frontend && npx tsc --noEmit && npm run build && npx eslint app components lib"
        status: pass
    human_judgment: true
    rationale: "Full round-trip persistence-across-restart and live-streaming-without-restart behavior requires a running backend + browser session; automated checks confirm the code paths exist and compile/lint clean, but the plan's <human-check> browser walkthrough was not performed this session (no reliable browser automation available)."
  - id: D2
    description: "User removes a ticker with no confirmation dialog; removal is non-optimistic and persists across refresh/restart; emptying the list lands on the empty state"
    requirement: "WATCH-03"
    verification:
      - kind: unit
        ref: "cd frontend && npx tsc --noEmit && npm run build && npx eslint app components lib; grep -ic 'confirm(' frontend/components/RemoveTickerButton.tsx == 0 (verified directly, see Issues Encountered re: the plan's -r flag)"
        status: pass
      - kind: integration
        ref: "cd backend && uv run --extra dev pytest -q"
        status: pass
    human_judgment: true
    rationale: "Same as D1 — code-level acceptance criteria all verified directly; the interactive browser walkthrough (tablet-width hit-target check, visual empty-state confirmation) was not performed this session."

duration: ~35min (includes a stall/resume, see Issues Encountered)
completed: 2026-08-02
status: complete
---

# Phase 1 Plan 04: Add/Remove Ticker UI Summary

**Watchlist is now fully editable from the browser: an add-ticker form and a per-row remove control, both non-optimistic and wired to the Plan 01 REST endpoints, with every empty/in-flight/error/long-text state real.**

## Performance

- **Duration:** ~35 min elapsed (includes a stall, see below)
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments
- `AddTickerForm`: text input (uppercased, capped at 10 chars client-side) + submit button, disabled while empty/whitespace or in-flight, posts to `addWatchlistTicker()`, shows the UI-SPEC's add-ticker error copy inline on failure while retaining the typed value
- `RemoveTickerButton`: per-row control (`Trash2`/`Loader2` from `lucide-react`), `aria-label="Remove {ticker}"`, inverted `min-w/min-h` breakpoint giving a 44px square hit target at tablet width while staying compact on desktop, no confirmation dialog anywhere
- Both controls are strictly non-optimistic: the UI only reflects a mutation after the server confirms it, so a failed request can never leave client state ahead of the database
- `WatchlistRow` gained a fixed-width fifth cell for the remove control so its presence never reflows the other four columns
- Confirmed (rather than assumed) that removing the last ticker falls through to the existing empty-state branch with zero new code

## Task Commits

1. **Task 1: Add-ticker form** — `7f8c546`
2. **Task 2: Remove-ticker control** — `245153d`

## Files Created/Modified
- `frontend/components/AddTickerForm.tsx` — add-ticker input/submit with full state coverage
- `frontend/components/RemoveTickerButton.tsx` — per-row remove control
- `frontend/components/WatchlistRow.tsx` — fixed-width remove-control cell
- `frontend/components/WatchlistPanel.tsx` — wires both controls, owns `removeItem`/add-item state mutators

## Decisions Made
None beyond what's in `key-decisions` above — plan executed as written.

## Deviations from Plan

None in substance. One verify-command environment quirk encountered (see Issues Encountered) — not a code defect.

## Issues Encountered

**Executor stall, not a plan defect.** The first execution attempt on this plan stalled (no progress for 600s) while running Task 2's verification step. Task 1 (`7f8c546`) was already committed; Task 2's code (`RemoveTickerButton.tsx`, plus the `WatchlistRow.tsx`/`WatchlistPanel.tsx` wiring) was already written and uncommitted on disk. The orchestrator (this session) reviewed the uncommitted code directly against Task 2's acceptance criteria, confirmed it correctly implements the spec, committed it (`245153d`), and is completing this SUMMARY.md in place of the stalled executor's final step.

**Root cause of the likely stall trigger, resolved:** Task 2's automated verify command includes `grep -ric 'confirm(' components/RemoveTickerButton.tsx`. On this environment's BSD/macOS `grep`, the `-r` (recursive) flag causes even a single explicit file argument to be printed in `path:count` format (e.g. `components/RemoveTickerButton.tsx:0`) rather than a bare count — so a literal `test "$(...)" = "0"` comparison against that command's raw output would read `"...tsx:0"`, not `"0"`, and fail even though the real answer (zero `confirm(` calls) is correct. Re-run without `-r` (`grep -ic`) returns the expected bare `0`. This is a pre-existing quirk in the plan's verify-command syntax on BSD grep, not a functional defect in `RemoveTickerButton.tsx` — the component genuinely contains no confirmation dialog. Recorded here for awareness; no code change needed.

**Not performed:** the plan's `<human-check>` interactive browser walkthrough (click-to-remove, refresh/restart persistence, tablet-width hit-target check, full empty-the-watchlist walkthrough) was not run in this unattended session — no reliable browser automation completed successfully. Recorded honestly as `human_judgment: true` in the `coverage:` block above rather than silently claimed as verified.

**Verified directly by the orchestrator (not the stalled executor):**
- `cd frontend && npx tsc --noEmit` — pass
- `cd frontend && npm run build` — pass (static export)
- `cd frontend && npx eslint app components lib` — pass
- All plan-specified grep gates (copy string, `removeWatchlistTicker` call, `aria-label`, `Trash2` icon, wiring into `WatchlistPanel`) — pass
- Zero `confirm(` calls in `RemoveTickerButton.tsx` — pass (see grep-quirk note above)
- `cd backend && uv run --extra dev pytest -q` — 86/86 pass, backend suite still green after the phase's full round-trip

## Next Phase Readiness

**Phase 1 (Live Market Terminal) is now feature-complete across all 4 plans.** All 11 phase requirements (DB-01/02/03, STREAM-01/02, WATCH-01..05, UI-01) have backend and/or frontend implementations committed. Recommend running code review, a UI review pass, and phase-level goal-backward verification next — and, since no browser-based human-check ran during Plans 02-04, a manual or automated visual pass before considering the phase's UI truly proven end-to-end in a live browser.

---
*Phase: 01-live-market-terminal*
*Completed: 2026-08-02*
