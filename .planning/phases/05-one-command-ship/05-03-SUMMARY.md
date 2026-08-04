---
phase: 05-one-command-ship
plan: 03
subsystem: testing
tags: [vitest, react-testing-library, jsdom, frontend-tests]

requires:
  - phase: 04-ai-copilot
    provides: "ChatPanel and its CR-01 critical bug, which this plan's highest-value test regresses against"
  - phase: 01-live-market-terminal
    provides: "WatchlistRow's 500ms flash effect and WatchlistPanel's CRUD callbacks"
provides:
  - "The project's first frontend test framework (Vitest + React Testing Library + jsdom)"
  - "27 component tests covering all four TEST-03 areas"
  - "frontend/vitest.config.ts, frontend/vitest.setup.ts, and `test`/`test:watch` scripts"
affects: []

actuals:
  tokens: 15000
  tasks: 3
  commits: 2

tech-stack:
  added:
    - "vitest@4.1.10, @testing-library/react@16.3.2, @testing-library/dom@10.4.1, jsdom@30.0.1, @vitejs/plugin-react@6.0.5, vite-tsconfig-paths@6.1.1, @testing-library/jest-dom@7.0.0, @testing-library/user-event@14.6.3, @vitest/coverage-v8@4.1.10"
  patterns:
    - "vi.mock with importOriginal spreading the original module, never vi.spyOn — ES module namespace objects are sealed, and spreading keeps the real ApiError available for components' instanceof branches"

key-files:
  created:
    - frontend/vitest.config.ts
    - frontend/vitest.setup.ts
    - frontend/components/WatchlistRow.test.tsx
    - frontend/components/WatchlistPanel.test.tsx
    - frontend/components/PositionsTable.test.tsx
    - frontend/components/ChatPanel.test.tsx
  modified: [frontend/package.json, frontend/package-lock.json, frontend/tsconfig.json]

key-decisions:
  - "An explicit resolve.alias in vitest.config.ts alongside the tsconfigPaths plugin — not redundant, see Deviations"
  - "An explicit afterEach(cleanup) in vitest.setup.ts, because RTL only auto-registers cleanup when Vitest globals are enabled and this config runs without them"

patterns-established:
  - "Mutation spot-check must reproduce the ORIGINAL bug, not just revert one mechanism — see Issues Encountered"

requirements-completed: [TEST-03]

coverage:
  - id: D1
    description: "Price flash animation flashes the right colour and fades after ~500ms"
    requirement: TEST-03
    verification:
      - kind: unit
        ref: "frontend/components/WatchlistRow.test.tsx — 7 tests"
        status: pass
    human_judgment: false
  - id: D2
    description: "Watchlist CRUD — add and remove update the grid; empty and error states are distinguished"
    requirement: TEST-03
    verification:
      - kind: unit
        ref: "frontend/components/WatchlistPanel.test.tsx — 6 tests"
        status: pass
    human_judgment: false
  - id: D3
    description: "Portfolio display calculations derive from the live stream price, not the server's snapshot P&L"
    requirement: TEST-03
    verification:
      - kind: unit
        ref: "frontend/components/PositionsTable.test.tsx — 7 tests"
        status: pass
    human_judgment: false
  - id: D4
    description: "Chat message rendering, including the CR-01 regression"
    requirement: TEST-03
    verification:
      - kind: unit
        ref: "frontend/components/ChatPanel.test.tsx — 7 tests, incl. the CR-01 regression"
        status: pass
    human_judgment: false

duration: ~35min
completed: 2026-08-04
status: complete
---

# Phase 5, Plan 03: Frontend Component Tests Summary

**The project's first frontend test framework and 27 tests across TEST-03's four named areas — including a regression for the critical `ChatPanel` bug Phase 4's review found in a component that had zero coverage.**

## Performance

- **Tasks:** 3 completed
- **Files:** 6 created, 3 modified
- **Tests:** 27 passing across 4 files
- **Note:** executed directly by the orchestrator, per this session's established pattern after repeated executor session-limit failures.

## Accomplishments
- All nine dev dependencies re-verified against the **live registry** before install (version resolves, repository is the official project repo, no install-time script) and pinned exactly; `npm audit` shows only the pre-existing `next`/`postcss`/`sharp` advisories
- Vitest + RTL + jsdom configured from this repo's **own bundled** Next.js 16.2.12 testing guide rather than remembered patterns, per `frontend/AGENTS.md`
- `WatchlistRow` (7): no flash on first price, uptick, downtick, fade completes at 500ms, repeated price is not a tick, undefined price placeholder, and the fade **restarts** on a rapid second tick
- `WatchlistPanel` (6): rows render, error copy, empty-vs-broken distinction, add, remove, and a failed remove leaving the grid unchanged (non-optimistic)
- `PositionsTable` (7): P&L and % change derived from the **live** price rather than the server's snapshot, negative P&L, server-price fallback, em-dash on no price, one row per position
- `ChatPanel` (7): empty/loaded/error states, send lifecycle, inline action cards (success and failure), no cards when nothing executed, and the **CR-01 regression**
- `npm run lint` and `npm run build` both still pass — the Docker image's frontend stage is unaffected

## Task Commits

1. **Tasks 1: framework + price flash** — `test(05-03): Vitest/RTL framework + price flash tests`
2. **Tasks 2–3: the two grids + chat** — `test(05-03): watchlist CRUD, positions math, chat rendering`

## Deviations from Plan

**1. [Genuine conflict] `tsconfig.json` `exclude` broke alias resolution in the test files**
- **Issue:** Step 6 adds the test globs to `exclude` so `next build` does not type-check them. But `vite-tsconfig-paths` honours that same `exclude`, so it refused to map `@/` inside exactly the files that needed it — every test failed at import with `Failed to resolve import "@/components/..."`.
- **Fix:** Kept both the `exclude` (needed for the build) and the `tsconfigPaths` plugin (the plan's gate requires it), and added an explicit `resolve.alias` for `@`. Documented inline as non-redundant so a later reader does not delete it as duplication.

**2. [Missing setup] RTL cleanup is not automatic without Vitest globals**
- **Issue:** The plan specifies not enabling implicit globals. RTL only auto-registers its `afterEach(cleanup)` when globals are on, so DOM accumulated across tests and queries began failing with "found multiple elements" for reasons unrelated to the component under test.
- **Fix:** Explicit `afterEach(cleanup)` in `vitest.setup.ts`.

**3. [Test fixture] An ambiguous assertion of my own making**
- **Issue:** `PositionsTable`'s live-price test used quantity 10 with avg cost 100, so the P&L figure rendered "100.00" — identical to the avg-cost cell, and `getByText` matched two elements.
- **Fix:** Quantity 3, making every cell's figure distinct.

## Issues Encountered

**The mutation spot-check that taught me something.** The `ChatPanel` CR-01 regression is the highest-value test in this phase, so I mutation-checked it. The first attempt reverted the render-branch priority — what I would have described as *the* CR-01 fix — and **the test still passed**.

That looked like a vacuous test. It wasn't. The Phase 4 fix has **two independent mechanisms**: the render-branch priority *and* clearing the stale flag on a successful send. Either alone protects. Only removing both — reconstructing the original bug exactly — failed the test, and then it failed on precisely the right assertion.

The lesson, recorded because it generalises: a mutation check is only meaningful if the mutation actually reproduces the original defect. Stopping at the first revert would have led me to "fix" a test that was already correct.

## Next Phase Readiness
Plan 05-04 (Playwright E2E) followed. This plan's framework is independent of it — component tests run with `npx vitest run` and need no container.

---
*Phase: 05-one-command-ship*
*Completed: 2026-08-04*
