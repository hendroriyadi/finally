---
phase: 02-manual-trading
plan: 04
subsystem: ui
tags: [nextjs, react, context, sse, trading-ui]

requires:
  - phase: 02-manual-trading
    provides: "02-03's PortfolioProvider context (cashBalance, positions, totalValue, loading, error, refresh) and Position wire type"
provides:
  - "PositionsTable — one row per open position, ticker/qty/avg-cost/price/P&L/%chg, all price-derived cells recomputed per-tick from the live SSE price map rather than the server's stale unrealized_pnl/change_percent snapshot"
  - "AppHeader extended with live totalValue and cashBalance figures beside the connection dot, both read straight from PortfolioProvider with no independent fetch or recomputation"
affects: [03-portfolio-analytics]

actuals:
  tokens: 2200
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Per-row price-derived cell resolution: prices[ticker]?.price ?? position.current_price ?? null, then derive P&L/%chg from that resolved price rather than the server's precomputed unrealized_pnl/change_percent fields — keeps every price-driven cell in a row visually in step, since the server's copies of both can independently lag by up to a poll interval"
    - "Loading branch keyed on the context's `loading` boolean, never on an empty array — an empty portfolio and a not-yet-loaded portfolio are different states and collapsing them would show a skeleton forever to a user who owns nothing"
    - "Two independent context consumers (PositionsTable, AppHeader) both read the same PortfolioProvider-derived totalValue rather than each computing their own sum, eliminating any path for the two surfaces to disagree"

key-files:
  created:
    - frontend/components/PositionsTable.tsx
  modified:
    - frontend/components/AppHeader.tsx
    - frontend/app/page.tsx

key-decisions:
  - "Currency and quantity cells render bare formatted numbers (no leading $ sign), matching WatchlistRow's existing price-cell convention (price.toFixed(2) with no currency symbol) rather than introducing a new formatting style for this phase's cells"
  - "P&L and percent-change color is derived once per row from the sign of the computed P&L value and shared across both cells, rather than computing the color twice from potentially-diverging sources"

patterns-established:
  - "Pattern 4: any future panel reading PortfolioProvider must resolve price-derived values through the streamed price map with a fallback to the server snapshot and then null — never render a server-precomputed derived field (unrealized_pnl, change_percent) directly, since it can lag the raw price by up to one poll interval"

requirements-completed: [PORT-01, PORT-05, UI-03]

coverage:
  - id: D1
    description: "Positions table shows one row per open position (ticker, quantity, avg cost, current price, unrealized P&L, percent change), all six columns updating live off the SSE price stream rather than a table-owned fetch"
    requirement: PORT-01
    verification:
      - kind: unit
        ref: "cd frontend && npx tsc --noEmit"
        status: pass
      - kind: unit
        ref: "cd frontend && npx eslint app components lib"
        status: pass
      - kind: unit
        ref: "grep verify gates: usePortfolioContext, usePriceStreamContext present; grep -vE comment-lines | grep -cE 'unrealized_pnl|change_percent' returns 0 in components/PositionsTable.tsx"
        status: pass
    human_judgment: true
    rationale: "Confirming a row appears on buy, ticks twice a second in step with price, and disappears cleanly on a full sell requires a live browser session against a running backend — no headless/curl equivalent proves the per-frame visual update or the row's disappearance the way watching a real DOM does (Phase 1/02-03 precedent)."
  - id: D2
    description: "Header shows total portfolio value and cash balance updating live, alongside the existing connection-status dot, with no independent fetch or recomputation"
    requirement: PORT-05
    verification:
      - kind: unit
        ref: "cd frontend && npx tsc --noEmit && npx eslint app components lib && npm run build"
        status: pass
      - kind: unit
        ref: "grep verify gates: usePortfolioContext, totalValue, cashBalance, tabular-nums, ConnectionStatusDot present; grep -c fetchPortfolio returns 0 in components/AppHeader.tsx"
        status: pass
    human_judgment: true
    rationale: "Confirming the header's total value moves on its own as prices tick while cash holds still until a trade, and that neither figure ever flashes a misleading $0.00 before the first fetch resolves, requires a live browser session (Phase 1/02-03 precedent)."
  - id: D3
    description: "All six UI-SPEC positions-table states behave as specified: loading skeleton, load error, empty state, one-row, many-row overflow with pinned headers, and zero-one-many row-component reuse with no filter hiding zero-quantity rows"
    requirement: UI-03
    verification:
      - kind: unit
        ref: "grep verify gates: 'No open positions', empty-state body copy, load-error copy, max-h-[28rem], animate-pulse all present in components/PositionsTable.tsx"
        status: pass
    human_judgment: true
    rationale: "Exercising the actual skeleton-to-populated transition, the internal scroll behavior at 15+ rows, and the load-error path against a stopped backend all require a live browser session; the copy strings and structural branch ordering are source-verified above but the rendered states are not."
---

# Phase 2 Plan 4: Positions Table and Live Header Summary

**Positions table with per-row live P&L/%chg derived from the SSE price stream, and a header showing live total portfolio value and cash balance beside the connection dot**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-08-03T06:47:00Z (approx.)
- **Completed:** 2026-08-03T06:51:14Z
- **Tasks:** 2 completed
- **Files modified:** 3 (1 new, 2 modified)

## Accomplishments

- `PositionsTable` renders one row per open position — ticker, quantity, avg cost, current price, unrealized P&L, and percent change — as a near-mirror of `WatchlistPanel`'s panel shell, pinned column-header row, and `max-h-[28rem] overflow-y-auto` scroll container, so the two grids read as one system rather than two independently invented tables.
- Every price-derived cell (current price, P&L, percent change) is computed per-row in the render body from `prices[ticker]?.price ?? position.current_price ?? null`, never from the server's `unrealized_pnl`/`change_percent` snapshot fields — confirmed by the plan's grep gate that those two field names appear nowhere outside comments in the file.
- `AppHeader` now reads `totalValue`, `cashBalance`, and `loading` straight from `usePortfolioContext()` and renders both figures labelled, in `tabular-nums`, beside the unchanged `ConnectionStatusDot` — with an em-dash placeholder while `loading` is true instead of a misleading `$0.00`.
- Branch order inside the scroll container is error, then loading (keyed on the `loading` boolean, not an empty array), then empty, then rows — matching `WatchlistPanel`'s precedent so a refresh-time error is never masked by a skeleton.
- No filter excludes zero-quantity rows; a fully-sold position relies on the backend deleting the row rather than the frontend hiding a zero-quantity one.
- `cd frontend && npx tsc --noEmit`, `npx eslint app components lib`, and `npm run build` all exit 0; `cd backend && uv run --extra dev pytest -q` still passes all 124 tests (this plan touched no backend code).

## Task Commits

1. **Task 1: The positions table — every row derived live, every state real** - `9b1e58f` (feat)
2. **Task 2: The header — portfolio value and cash, live beside the dot** - `92257c4` (feat)

## Files Created/Modified

- `frontend/components/PositionsTable.tsx` (new) - positions grid with skeleton/error/empty/populated states, per-row live price/P&L/%chg derivation, `formatQuantity`/`formatCurrency`/`formatPercent` helpers
- `frontend/components/AppHeader.tsx` - extended with `PORTFOLIO VALUE` and `CASH` figures read from `usePortfolioContext()`, doc comment updated to no longer defer these to a later phase
- `frontend/app/page.tsx` - renders `PositionsTable` between `TradeBar` and `WatchlistPanel`

## Decisions Made

- Currency and quantity cells render bare formatted numbers (no `$` prefix), matching `WatchlistRow`'s existing `price.toFixed(2)` convention rather than introducing a new currency-symbol style for this phase.
- `formatQuantity` uses `toFixed(6).replace(/\.?0+$/, "")` to show fractional-share precision (e.g. `0.5`) while trimming trailing zeros so a whole-share position reads as `10`, not `10.000000`.
- P&L and percent-change share one color decision per row (derived once from the sign of the computed P&L value) rather than each cell computing its own color from a potentially-diverging source.

## Deviations from Plan

None - plan executed exactly as written. `PortfolioProvider`'s existing context shape (from 02-03) needed no changes; both new consumers read it unmodified.

## Issues Encountered

None. Both tasks' automated `<verify>` gates (tsc, eslint, build, and all grep-based copy/structure checks) passed on first attempt; the backend suite (124 tests) remained green after the phase's UI-only changes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 2 (Manual Trading) is now feature-complete at the code level: watchlist (Phase 1), trade execution (02-01), money-math/race-safety proofs (02-02), shared portfolio state and trade bar (02-03), and this plan's positions table + live header close the loop from "place a trade" to "see it reflected everywhere."
- Deferred to a live browser session (consistent with Phase 1 and 02-03's established precedent, `/gsd-verify-work`): the per-frame visual tick of the price/P&L columns, the skeleton-to-populated transition, the internal scroll behavior at 15+ positions, the header's `$0.00`-avoidance on reload, and the full buy/sell/empty-state round trip described in this plan's `<verify><human-check>` blocks.
- No blockers. `cd frontend && npx tsc --noEmit`, `npx eslint app components lib`, and `npm run build` all exit 0; `cd backend && uv run --extra dev pytest -q` passes 124/124.

---
*Phase: 02-manual-trading*
*Completed: 2026-08-03*

## Self-Check: PASSED

All created/modified files confirmed present on disk (`frontend/components/PositionsTable.tsx`, `frontend/components/AppHeader.tsx`, `frontend/app/page.tsx`). Both task commits (`9b1e58f`, `92257c4`) confirmed present in `git log --oneline --all`.
