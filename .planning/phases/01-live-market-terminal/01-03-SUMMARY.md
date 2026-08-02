---
phase: 01-live-market-terminal
plan: 03
subsystem: ui
tags: [nextjs, react, sse, eventsource, sparkline, react-context]

requires:
  - phase: 01-live-market-terminal (plan 02)
    provides: "Next.js terminal shell (layout, AppHeader status-dot slot), WatchlistPanel/WatchlistRow with em-dash placeholders, lib/types.ts (PriceUpdate, PriceMap, ConnectionStatus), lib/api.ts (API_BASE)"
provides:
  - "lib/useSseStream.ts: single-EventSource hook (usePriceStream), MAX_SPARKLINE_POINTS=60, session baselines, capped per-ticker history"
  - "components/PriceStreamProvider.tsx: React context sharing one stream between header and grid (PriceStreamProvider, usePriceStreamContext)"
  - "components/ConnectionStatusDot.tsx: fixed 8px three-state connection indicator"
  - "components/Sparkline.tsx: hand-written inline SVG polyline sparkline with flat-baseline placeholder"
  - "Live-wired AppHeader, WatchlistRow (price flash + CHG% + sparkline), WatchlistPanel (stream-context consumption)"
affects: [phase-02-manual-trading, phase-03-portfolio-visualization, phase-04-ai-copilot, phase-05-one-command-ship]

actuals:
  tokens: 4271
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Single shared EventSource via React context (PriceStreamProvider) — header and grid are siblings under one provider, so neither can accidentally open a second connection"
    - "Ref-accumulate, state-publish: usePriceStream mutates history/baselines in a ref (survives re-render, never resets) then publishes a shallow-copied snapshot into useState after each frame — required because this repo's Next.js 16 / eslint-config-next ships the react-hooks/refs ESLint rule, which forbids reading ref.current during render"
    - "CHG% computed client-side against a per-ticker session baseline (first price observed since page load), never against the wire's tick-to-tick change_percent"
    - "Error handler only sets connection status; it never closes/reopens the EventSource, leaving reconnection entirely to the browser's native retry (server's `retry: 1000` directive)"

key-files:
  created:
    - frontend/lib/useSseStream.ts
    - frontend/components/PriceStreamProvider.tsx
    - frontend/components/ConnectionStatusDot.tsx
    - frontend/components/Sparkline.tsx
  modified:
    - frontend/app/layout.tsx
    - frontend/components/AppHeader.tsx
    - frontend/components/WatchlistPanel.tsx
    - frontend/components/WatchlistRow.tsx

key-decisions:
  - "Deviated from the plan's literal ref-only accumulator + separate version-counter shape: this repo's installed eslint-config-next (Next.js 16) enforces the react-hooks/refs rule, which errors on reading ref.current during render. Kept the refs as the mutation/accumulation owner (never reset, capped, baseline-once) but publish a shallow copy into useState after each SSE frame, and render reads state — same behavioral guarantees (survives re-render, only grows, capped at 60), lint-clean shape."
  - "CHG% color in WatchlistRow is driven by the sign of the computed session-baseline changePercent, not the wire's per-tick `direction` field, per the plan's explicit operative definition. `direction` remains an accepted-but-currently-unused WatchlistRow prop (still passed by WatchlistPanel) since the UI-SPEC and plan reserve it for the tick-to-tick data, distinct from the session CHG% column."

patterns-established:
  - "Any future component needing live price data reads it from usePriceStreamContext(), never opens its own EventSource — enforced by a grep gate in this plan's verify block and worth keeping as a standing convention"

requirements-completed: [STREAM-02, WATCH-04, WATCH-05]

coverage:
  - id: D1
    description: "Prices in the watchlist grid update live from the SSE stream without any user action or page refresh; exactly one EventSource connection is opened per page load, shared by the header dot and every grid row"
    requirement: STREAM-02
    verification:
      - kind: other
        ref: "grep -rc 'new EventSource' frontend/lib frontend/components frontend/app -> 1 (only in lib/useSseStream.ts)"
        status: pass
      - kind: other
        ref: "cd frontend && npx tsc --noEmit && npm run build && npx eslint app components lib"
        status: pass
      - kind: manual_procedural
        ref: "curl -N http://localhost:8000/api/stream/prices confirms retry: 1000 directive + data: frames matching PriceUpdate shape, verified this session"
        status: pass
    human_judgment: true
    rationale: "Live resilience behavior (dot turning yellow on backend stop, green + resumed prices on backend restart, exactly-one-network-request in devtools) requires a real browser session; no browser automation tool was available/reliable in this unattended run. Backend-side precondition (retry directive, frame shape) and all static/type/lint/build gates were verified directly."
  - id: D2
    description: "A price cell flashes green on an uptick and red on a downtick, fading within ~500ms; CHG% is a signed percentage against the session baseline, green when positive and red when negative; each row shows a progressively-drawn sparkline accumulated since page load, and a ticker with zero ticks renders a flat baseline placeholder"
    requirement: WATCH-04, WATCH-05
    verification:
      - kind: other
        ref: "grep -q 'duration-500' components/WatchlistRow.tsx; grep -q 'polyline' components/Sparkline.tsx; grep -q 'usePriceStreamContext' components/WatchlistPanel.tsx; grep -c 'new EventSource' components/WatchlistPanel.tsx -> 0"
        status: pass
      - kind: other
        ref: "cd frontend && npx tsc --noEmit && npm run build && npx eslint app components lib"
        status: pass
    human_judgment: true
    rationale: "Visual flash timing/color, sparkline progressive drawing, and stream-interruption sparkline continuity require a real browser session to confirm visually; not performed this session for the same reason as D1 (see Issues Encountered)."

duration: 22min
completed: 2026-08-02
status: complete
---

# Phase 1 Plan 03: Live SSE Price Stream, Flash, Sparklines, Connection Dot Summary

**One shared `EventSource` (via `usePriceStream`/`PriceStreamProvider`) drives a green/yellow/red header dot, per-row 500ms price flashes, session-baseline CHG%, and hand-rolled SVG sparklines that survive re-render and stream interruption — turning the Plan 02 static grid into a live trading terminal.**

## Performance

- **Duration:** ~22 min
- **Started:** 2026-08-02T16:10Z (approx, first commit)
- **Completed:** 2026-08-02T16:32Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Built `lib/useSseStream.ts`: exactly one `EventSource` per mount against `${API_BASE}/api/stream/prices`, exporting `MAX_SPARKLINE_POINTS = 60` and the `usePriceStream(url)` hook. Session baselines are recorded once per ticker and never overwritten; per-ticker history is truncated to 60 points every frame; tickers absent from a frame have their history/baseline entries deleted so removed tickers never leak memory. The error handler only flips status to `reconnecting` — it never closes/reopens the connection, leaving all retry behavior to the browser's native `EventSource` retry driven by the server's `retry: 1000` directive.
- Built `components/PriceStreamProvider.tsx` (context + `usePriceStreamContext()`, throws when used outside the provider) and wired it into `app/layout.tsx` wrapping both `AppHeader` and `{children}` — the structural reason exactly one connection exists per page load.
- Converted `AppHeader` to a client component rendering the new `ConnectionStatusDot` (fixed 8px, no text content, green/yellow/red mapped to the `positive`/`accent`/`destructive` tokens, `animate-pulse` only while reconnecting).
- Built `components/Sparkline.tsx`: a pure, stateless inline SVG `polyline`; fewer than two points renders a flat baseline placeholder (shared by the empty and loading cases per the UI-SPEC); a zero min-max range is guarded so a perfectly flat series still renders as a flat line.
- Updated `WatchlistRow` to own a `flash` state keyed off price changes (500ms fade via `transition-colors duration-500`, in-flight timer cleared before starting a new one so rapid ticks restart rather than stack) and to render CHG% colored by the sign of the session-baseline change percent.
- Updated `WatchlistPanel` to source `prices`/`history`/`baselines` from `usePriceStreamContext()` and compute `changePercent = (price - baseline) / baseline * 100` per this plan's operative definition, leaving the REST watchlist fetch and all four grid states (loading/error/empty/overflow) from Plan 02 untouched.
- Verified the backend precondition directly: `curl -N http://localhost:8000/api/stream/prices` emits the `retry: 1000` directive followed by `data:` frames matching the frozen `PriceUpdate` shape.

## Task Commits

1. **Task 1: One shared price stream and a connection-status dot that tells the truth** - `45b55d6` (feat)
2. **Task 2: Live price cells with flash, session change %, and progressive sparklines** - `ed7e29f` (feat)

_No TDD tasks in this plan; each task is a single atomic commit._

## Files Created/Modified
- `frontend/lib/useSseStream.ts` - Single-`EventSource` hook: status, prices, capped history, session baselines
- `frontend/components/PriceStreamProvider.tsx` - Context sharing the one stream across the page
- `frontend/components/ConnectionStatusDot.tsx` - Fixed 8px three-state indicator
- `frontend/components/Sparkline.tsx` - Inline SVG polyline, flat-baseline placeholder, zero-range guard
- `frontend/app/layout.tsx` - Wraps `AppHeader` + `children` in `PriceStreamProvider`
- `frontend/components/AppHeader.tsx` - Now a client component rendering the dot from stream context
- `frontend/components/WatchlistRow.tsx` - Flash-on-change, session CHG% color, sparkline wiring
- `frontend/components/WatchlistPanel.tsx` - Sources price/history/baseline from stream context, computes CHG%

## Decisions Made
- **Ref-accumulate, state-publish shape (deviation from the plan's literal wording):** the plan specified holding `history`/`baselines` in a ref plus a separate `version` counter in state. Implementing that literally hit a lint error: this repo's installed Next.js 16 / `eslint-config-next` enables the `react-hooks/refs` rule, which forbids reading `ref.current` during render (discovered via `npx eslint`, not anticipated by the plan or its research). Resolved by keeping the refs as the sole mutation/accumulation owner (still never reset, still capped at 60, still baseline-once) and publishing a shallow copy into `useState` right after folding each frame into the refs — the render path reads state, never `ref.current`. Same behavioral guarantees the plan's must-haves require; different implementation shape to satisfy the environment's actual lint rules. This is exactly the class of thing `frontend/AGENTS.md`'s "this is NOT the Next.js you know" warning flagged.
- **CHG% color by sign of the computed baseline percent, not by the wire's `direction` field** — matches the plan's explicit `## Operative definition — the CHG% column` and behavior spec ("green when positive and red when negative... 0.00% on the very first tick"). `direction` is still accepted as a `WatchlistRow` prop (still passed through by `WatchlistPanel`) for a future consumer, but isn't destructured/used in this plan since nothing in the behavior spec calls for tick-to-tick direction to drive CHG%'s color.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `react-hooks/refs` ESLint rule blocked the plan's literal ref-read-during-render pattern**
- **Found during:** Task 1 (`lib/useSseStream.ts`)
- **Issue:** The plan's action text specifies returning `historyRef.current`/`baselinesRef.current` directly from the hook. `npx eslint app components lib` (a required verify-gate command) failed with 3 `react-hooks/refs` errors: "Cannot access refs during render."
- **Fix:** Kept `historyRef`/`baselinesRef` as the accumulator (mutated in the `onmessage` handler — an effect, not render), and added `useState` for `history`/`baselines` that receive a shallow copy of the ref contents immediately after each frame is folded in. The hook's return statement reads the state variables, not `ref.current`. Removed the separate `version` counter the plan suggested, since the `history`/`baselines`/`prices` state updates themselves already trigger the necessary re-render.
- **Files modified:** `frontend/lib/useSseStream.ts`
- **Verification:** `npx eslint app components lib` exits 0; `npx tsc --noEmit` and `npm run build` both pass; `MAX_SPARKLINE_POINTS = 60` and `usePriceStream` still exported per the plan's artifact spec.
- **Committed in:** `45b55d6` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — lint rule incompatibility with the plan's literal implementation guidance)
**Impact on plan:** No behavioral change to any must-have truth (accumulation still survives re-render and never resets, history is still capped at 60, baselines are still recorded once). Purely an implementation-shape fix required by this repo's actual installed toolchain, not anticipated by the plan or its research (both pre-date discovering this specific lint rule in this Next.js 16 install).

## Issues Encountered

**Live browser verification not performed.** The plan's two `<human-check>` blocks (stop/restart backend and observe the dot + prices in a real browser; watch the grid for 30 seconds and observe flash/CHG%/sparkline behavior visually) require an interactive browser session. No browser automation tool completed reliably in this unattended run. In its place: (1) the backend precondition was verified directly via `curl -N http://localhost:8000/api/stream/prices`, confirming the `retry: 1000` directive and `data:` frames in the exact `PriceUpdate` shape the frontend code consumes; (2) every automated acceptance-criteria command in both tasks (`tsc --noEmit`, `npm run build`, `npx eslint`, and every specified `grep` gate) was run directly and passes. This is recorded as `human_judgment: true` in the `coverage:` block above (D1, D2) rather than silently claimed as verified, consistent with Plan 02's precedent for the same limitation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1's full vertical slice (DB, watchlist REST + persistence, SSE mount, live terminal UI) is now complete pending Plan 04 (add/remove ticker UI) and the phase-level UAT/human verification pass.
- `usePriceStreamContext()` is the established pattern any later phase should reuse for live price data — never open a second `EventSource`.
- Recommend a human (or a future `/gsd-ui-review` pass) do a visual spot-check of the running app once Plan 04 completes the full Phase 1 slice — flash timing, sparkline drawing, and connection-dot resilience all need eyes-on confirmation that this unattended session could not provide.

## Self-Check: PASSED

All 4 created files verified present on disk (`frontend/lib/useSseStream.ts`, `frontend/components/PriceStreamProvider.tsx`, `frontend/components/ConnectionStatusDot.tsx`, `frontend/components/Sparkline.tsx`); both task commits (`45b55d6`, `ed7e29f`) verified present in `git log --oneline --all`.

---
*Phase: 01-live-market-terminal*
*Completed: 2026-08-02*
