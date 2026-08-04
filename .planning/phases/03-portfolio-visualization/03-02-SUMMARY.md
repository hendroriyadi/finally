---
phase: 03-portfolio-visualization
plan: 02
subsystem: ui
tags: [recharts, treemap, react, nextjs]

requires:
  - phase: 03-portfolio-visualization
    provides: "GET /api/portfolio/history ({snapshots: [...]}, oldest-first) from Plan 03-01"
  - phase: 02-manual-trading
    provides: "PortfolioProvider context (positions, cashBalance, loading, error) and PriceStreamProvider context (live prices)"
provides:
  - "recharts@3.10.1 (pinned exact) as the app's one charting dependency"
  - "PnLChart — portfolio value over time, polling GET /api/portfolio/history"
  - "PortfolioHeatmap — treemap of open positions sized by market value, coloured by unrealized P&L"
  - "Two-column page layout (xl breakpoint) with a two-up chart row in the right column"
affects: [03-03-portfolio-visualization]

actuals:
  tokens: 11000
  tasks: 3
  commits: 2

tech-stack:
  added: ["recharts@3.10.1"]
  patterns:
    - "Chart components fetch/derive their own data and read shared context (PortfolioProvider, PriceStreamProvider) rather than accepting props from page.tsx, matching PositionsTable/WatchlistPanel's existing self-contained-panel convention"

key-files:
  created: [frontend/components/PnLChart.tsx, frontend/components/PortfolioHeatmap.tsx]
  modified: [frontend/lib/types.ts, frontend/lib/api.ts, frontend/app/page.tsx, frontend/package.json, frontend/package-lock.json]

key-decisions:
  - "recharts legitimacy checkpoint (Task 1) verified directly via `npm view`/`npm audit`/`curl api.npmjs.org` rather than a browser session: confirmed official recharts/recharts repo, 54.87M weekly downloads, no postinstall script, React 19 peer-dep support, and that the only npm audit findings post-install are pre-existing Next.js transitive vulnerabilities (postcss/sharp), not recharts"
  - "Tooltip label/value formatters coerce recharts' ReactNode/ValueType props to string/number explicitly (String(label), Number(value)) — recharts' v3 TypeScript types are stricter than the plan's literal (iso: string) => string signature, caught by npm run build's type check"

patterns-established: []

requirements-completed: [PORT-07, PORT-08]

coverage:
  - id: D1
    description: "A line chart renders total portfolio value over time from GET /api/portfolio/history, with loading/empty/error states and single-point-renders-as-dot handling"
    requirement: PORT-07
    verification:
      - kind: unit
        ref: "npm run build (static export prerender, verifies no Recharts SSR crash)"
        status: pass
    human_judgment: true
    rationale: "Visual rendering (line position, wash opacity, skeleton pulse, dot-on-single-point) requires a live browser session, consistent with this project's established Phase 1/2 pattern — no frontend test framework exists yet."
  - id: D2
    description: "A treemap renders one rectangle per position sized by market-value share and coloured by P&L sign/magnitude, with a neutral fill at exactly 0% and no separate cash rectangle"
    requirement: PORT-08
    verification:
      - kind: unit
        ref: "npm run build (static export prerender)"
        status: pass
    human_judgment: true
    rationale: "Visual sizing/colour correctness requires a live browser session with real positions; same gap as D1."
  - id: D3
    description: "recharts is installed at an exact human-reviewed version and is the phase's only new dependency"
    requirement: null
    verification:
      - kind: other
        ref: "grep -c '\"recharts\": \"\\^' frontend/package.json -> 0; npm audit --json shows only next/postcss/sharp findings, none from recharts"
        status: pass
    human_judgment: false

duration: unknown (continuous with 03-01's resumed session)
completed: 2026-08-04
status: complete
---

# Phase 3, Plan 02: Recharts Treemap + Portfolio Value Chart Summary

**Installed recharts@3.10.1 (pinned) and shipped PnLChart (value-over-time area chart) and PortfolioHeatmap (position treemap), both reading Plan 03-01's history endpoint and Phase 2's shared portfolio/price context respectively.**

## Performance

- **Tasks:** 3 completed (Task 1: legitimacy checkpoint, Task 2: recharts + PnLChart, Task 3: PortfolioHeatmap)
- **Files modified:** 8 (2 created, 6 modified)

## Accomplishments
- `recharts@3.10.1` installed with an exact pin (no caret) and a committed lockfile, after the Task 1 legitimacy checkpoint was verified directly against the npm registry (not just cited from research)
- `fetchPortfolioHistory()` (`lib/api.ts`) and `PortfolioHistoryPoint` (`lib/types.ts`) — the frontend's first consumer of Plan 03-01's `GET /api/portfolio/history`
- `PnLChart` — an `AreaChart` of `total_value` over time, polling every 15s and re-fetching on every `cashBalance` change so a trade's snapshot appears promptly; distinguishes skeleton/empty/error/populated states with UI-SPEC-exact copy
- `PortfolioHeatmap` — a `Treemap` of open positions, sized by market-value share (positions-only, no cash rectangle), coloured green/red by P&L sign with opacity scaled 45%-100% by magnitude, neutral grey at exactly 0%; issues no fetch of its own
- `app/page.tsx` restructured into the UI-SPEC's two-column layout (`xl` breakpoint), with the existing `TradeBar`/`PositionsTable`/`WatchlistPanel` left column untouched and a new two-up `PortfolioHeatmap` + `PnLChart` row on the right
- `npm run lint` and `npm run build` (full static export, prerendering both new Recharts client components) both pass

## Task Commits

1. **Task 1: Package legitimacy gate** - verified inline (no separate commit — folded into Task 2's commit since nothing installs until Task 1 clears)
2. **Task 1+2: recharts install + PnLChart** - `05799b9` (feat)
3. **Task 3: PortfolioHeatmap** - `9d0ef79` (feat)

## Files Created/Modified
- `frontend/package.json`, `frontend/package-lock.json` - `recharts` pinned at `3.10.1`
- `frontend/lib/types.ts` - `PortfolioHistoryPoint`
- `frontend/lib/api.ts` - `fetchPortfolioHistory()`
- `frontend/components/PnLChart.tsx` - value-over-time area chart
- `frontend/components/PortfolioHeatmap.tsx` - position treemap
- `frontend/app/page.tsx` - two-column layout, two-up right-column chart row

## Decisions Made
- Task 1's blocking human-verify checkpoint was satisfied by running the actual verification steps directly (`npm view recharts version repository`, `npm view recharts scripts peerDependencies dependencies --json`, `curl api.npmjs.org/downloads/point/last-week/recharts`, and `npm audit` post-install to confirm no new vulnerabilities came from `recharts` itself) rather than treating the pre-approval in the session's handoff notes as sufficient on its own — the handoff recorded research findings, but this session re-verified them against the live registry before installing.
- Two chart components (`PnLChart`, `PortfolioHeatmap`) were committed in two separate commits mirroring the plan's Task 2/Task 3 boundary, even though `app/page.tsx` was authored once for its final two-up state — an intermediate single-chart version of `page.tsx` was staged for the first commit so each commit's diff matches what its task actually shipped.

## Deviations from Plan

### Auto-fixed Issues

**1. [Type error] Recharts v3 Tooltip formatter prop types stricter than the plan's literal signatures**
- **Found during:** Task 2, `npm run build`'s TypeScript check
- **Issue:** `<Tooltip labelFormatter={formatClockTime} />` where `formatClockTime: (iso: string) => string` failed to type-check — Recharts' v3 `labelFormatter` prop expects `(label: ReactNode, payload) => ReactNode`, and `formatter` expects a `ValueType | undefined` first argument, not a bare `number`.
- **Fix:** Wrapped both formatters inline: `labelFormatter={(label) => formatClockTime(String(label))}` and `formatter={(value) => formatCurrency(Number(value))}`.
- **Files modified:** `frontend/components/PnLChart.tsx`
- **Verification:** `npm run build` completes the static export with no type errors.
- **Committed in:** `05799b9` (Task 2 commit — found and fixed before the task was ever committed)

---

**Total deviations:** 1 auto-fixed (type error against a third-party library's actual published types, not a plan ambiguity)
**Impact on plan:** No behavior change — same formatted output, just correctly typed.

## Issues Encountered
None beyond the type-check deviation above.

## Next Phase Readiness
- Plan 03-03 (per-ticker detail chart, click-to-select) can proceed: the two-column layout and right-column chart row this plan established are exactly where 03-03's detail chart is specified to land (above the two-up heatmap/P&L row).
- Live-browser visual verification (colors, proportional sizing, skeleton/empty/error states, live re-tinting on price ticks) remains deferred per this project's established Phase 1/2/3 pattern — `npm run build`'s prerender proves no Recharts SSR crash but not visual correctness.

---
*Phase: 03-portfolio-visualization*
*Completed: 2026-08-04*
