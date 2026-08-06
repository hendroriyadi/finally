---
phase: 03-portfolio-visualization
plan: 03
subsystem: ui
tags: [recharts, react, nextjs, accessibility]

requires:
  - phase: 03-portfolio-visualization
    provides: "recharts@3.10.1 (pinned) and the chart-panel shell/styling conventions established in Plan 03-02"
  - phase: 01-live-market-terminal
    provides: "usePriceStream's per-ticker history accumulator (historyRef), whose retention cap this plan raises in place"
provides:
  - "DetailChart — full-width per-ticker price-history panel driven by watchlist row selection"
  - "Clickable, keyboard-operable WatchlistRow with a persistent selected-row indicator"
  - "Lifted selectedTicker state in app/page.tsx, with default-on-load and removal-reconciliation logic in WatchlistPanel"
  - "MAX_SPARKLINE_POINTS raised from 60 to 300, serving both the sparkline and the detail chart from one accumulator"
affects: []

actuals:
  tokens: 9000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Selection state lifted to the nearest common parent (app/page.tsx) rather than a new React context, when all consumers are direct children of that parent"
    - "A one-time default applied inside an existing fetch-on-mount .then() chain, guarded by a ref rather than a value comparison, to make 'apply once, never again' independent of later state changes"

key-files:
  created: [frontend/components/DetailChart.tsx]
  modified: [frontend/lib/useSseStream.ts, frontend/components/WatchlistRow.tsx, frontend/components/WatchlistPanel.tsx, frontend/app/page.tsx]

key-decisions:
  - "WatchlistRow's hover/selected left-border classes were restructured from a hover-only 2px border to a permanent 2px border that only changes colour (transparent -> accent), which also removes a pre-existing hover layout jitter as a side effect, not just satisfying the plan's no-shift acceptance criterion"

patterns-established:
  - "A row/list-item that both displays data and drives shared selection state keeps its interactive semantics on the root element (role=button, tabIndex, aria-pressed, onKeyDown) rather than promoting to <button>, when it already nests an actual <button> (WatchlistRow's remove control) — nesting buttons is invalid HTML"

requirements-completed: [UI-02]

coverage:
  - id: D1
    description: "Clicking a watchlist row loads that ticker into a full-width detail chart that keeps updating live, with a persistent selected-row indicator and keyboard operability"
    requirement: UI-02
    verification:
      - kind: unit
        ref: "npm run build (static export prerender, verifies no Recharts SSR crash and correct prop wiring)"
        status: pass
    human_judgment: true
    rationale: "Click interaction, sticky visual indicator, and live chart redraw require a live browser session — no frontend test framework exists yet, consistent with this project's established Phase 1/2/3 pattern."
  - id: D2
    description: "The default-selected ticker is the first watchlist entry on load; removals reconcile the selection; an emptied watchlist shows the no-ticker-selected prompt"
    requirement: UI-02
    verification:
      - kind: unit
        ref: "grep -c 'defaultSelectionAppliedRef' frontend/components/WatchlistPanel.tsx; grep -vE comment-lines frontend/components/WatchlistPanel.tsx | grep -c 'selectedTicker === null' -> 0"
        status: pass
    human_judgment: true
    rationale: "The reconciliation logic is source-verified (grep-based acceptance criteria all pass) but the actual UX sequence (load -> default appears -> remove -> reselection -> empty -> prompt) needs a live browser session to confirm visually."

duration: unknown (continuous with 03-01/03-02's resumed session)
completed: 2026-08-04
status: complete
---

# Phase 3, Plan 03: Watchlist-Driven Detail Chart Summary

**Clicking (or Enter/Space-selecting) a watchlist row now loads that ticker into a full-width live-updating price chart, defaulting to the first seeded ticker on load and following removals so the selection is never stale.**

## Performance

- **Tasks:** 2 completed
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments
- `MAX_SPARKLINE_POINTS` raised from 60 to 300 in `lib/useSseStream.ts` — one accumulator, two consumers (the existing sparkline and the new detail chart), no second buffer
- `DetailChart` — reads `usePriceStreamContext().history[ticker]` directly, opens no `EventSource` and issues no fetch; renders a flat-baseline placeholder under two points, an `AreaChart` otherwise, and the exact no-selection copy when `ticker` is `null`
- `WatchlistRow` is now operable by mouse and keyboard (`role="button"`, `tabIndex`, `aria-pressed`, Enter/Space handling), with a permanent 2px left border that only changes colour on hover/selection — removing a pre-existing hover jitter as a side effect — and a remove-control wrapper that stops click/key propagation so removal never also selects
- `WatchlistPanel` applies the first fetched ticker as the default selection exactly once (ref-guarded, inside the existing fetch effect — no new effect added) and skips the default on a failed or empty fetch; `removeItem` reconciles the selection to the first remaining ticker or `null` when the removed ticker was the selected one
- `app/page.tsx` is now a client component owning `selectedTicker` state, passed to both `WatchlistPanel` and `DetailChart` — no new React context, since both consumers are direct children
- `npm run lint` (exit 0) and `npm run build` (full static export, both new/changed client components prerendering cleanly) pass throughout

## Task Commits

1. **Task 1: Click a ticker, watch its chart** - `3b0213e` (feat)
2. **Task 2: A selection that is never wrong** - `fb038c9` (feat)

## Files Created/Modified
- `frontend/lib/useSseStream.ts` - `MAX_SPARKLINE_POINTS` 60 → 300, doc comment updated
- `frontend/components/DetailChart.tsx` - new full-width per-ticker chart panel
- `frontend/components/WatchlistRow.tsx` - operable root element, sticky selected indicator, propagation-stopped remove control
- `frontend/components/WatchlistPanel.tsx` - `selectedTicker`/`onSelectTicker` props, default-selection ref, removal reconciliation
- `frontend/app/page.tsx` - lifted `selectedTicker` state, renders `DetailChart` above the two-up heatmap/P&L row

## Decisions Made
- None beyond what `03-03-PLAN.md` specified — plan executed as written, including all of its "Claude's-discretion" resolutions (lifted `useState` over a new context, hidden X axis on the detail chart, existing root `<div>` given button semantics rather than promoted to `<button>`).

## Deviations from Plan
None — plan executed exactly as written. (One `eslint-disable-next-line react-hooks/exhaustive-deps` comment was added to the existing fetch-on-mount effect in `WatchlistPanel.tsx` to keep it running exactly once despite now also calling the `onSelectTicker` prop inside it; `npm run lint` passes with no unused-directive warning, confirming the suppression is both necessary and correctly scoped.)

## Issues Encountered
None.

## Next Phase Readiness
- Phase 3's three planned surfaces (treemap, P&L chart, detail chart) are all shipped and wired into the two-column layout. Ready for Phase 3 code review.
- Live-browser visual/interaction verification (click-through, sticky indicator, keyboard selection, chart redraw cadence) remains deferred per this project's established Phase 1/2/3 pattern.

---
*Phase: 03-portfolio-visualization*
*Completed: 2026-08-04*
