---
phase: 01-live-market-terminal
plan: 02
subsystem: ui
tags: [nextjs, react, tailwindcss-v4, typescript, static-export]

requires:
  - phase: 01-live-market-terminal (plan 01)
    provides: "GET/POST/DELETE /api/watchlist REST contract, GET /api/stream/prices SSE endpoint"
provides:
  - "First-ever frontend in this repo: Next.js App Router, TypeScript, static export (output: 'export')"
  - "Tailwind v4 CSS-first dark theme with all 8 locked FinAlly color tokens"
  - "Dark terminal shell: root layout, AppHeader (title + status-dot slot), single-page app"
  - "WatchlistPanel fetching GET /api/watchlist on mount, with real loading/error/empty/populated/overflow states"
  - "lib/api.ts and lib/types.ts — typed fetch wrappers and shared types mirroring the backend JSON contracts"
affects: [phase-01-plan-03, phase-01-plan-04, phase-02-manual-trading, phase-03-portfolio-visualization, phase-04-ai-copilot]

actuals:
  tokens: 12500
  tasks: 3
  commits: 2

tech-stack:
  added: ["next (App Router)", "react", "react-dom", "typescript", "tailwindcss@^4.3.3", "@tailwindcss/postcss", "lucide-react", "eslint", "eslint-config-next"]
  patterns:
    - "Tailwind v4 CSS-first theme (@theme block in globals.css) — no tailwind.config.js/ts, no autoprefixer (bundled into @tailwindcss/postcss)"
    - "API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '' — empty-string default resolves to same-origin, matching Phase 5's single-container deployment with zero code change"
    - "ApiError class carrying numeric status so callers distinguish 409/400/404 without string parsing"
    - "Presentational/container split: WatchlistRow (props only) vs WatchlistPanel ('use client', owns fetch + state branching)"
    - "Ticker strings always rendered as ordinary React children (never dangerouslySetInnerHTML) — verified by a grep gate in both plan verify commands"

key-files:
  created:
    - frontend/app/layout.tsx
    - frontend/app/globals.css
    - frontend/app/page.tsx
    - frontend/components/AppHeader.tsx
    - frontend/components/WatchlistPanel.tsx
    - frontend/components/WatchlistRow.tsx
    - frontend/lib/api.ts
    - frontend/lib/types.ts
    - frontend/next.config.ts
    - frontend/postcss.config.mjs
  modified:
    - .gitignore (scoped fix so root Python-template lib/ pattern no longer silently blocks frontend/lib/)

key-decisions:
  - "Resolved D-15 (frontend structure): stock App Router with app/, components/, lib/, no src/ directory"
  - "Resolved D-16 (sparkline approach) partially: this plan reserves the sparkline column with an empty fixed-size cell; the actual hand-written SVG sparkline is built in Plan 03"
  - "Price/CHG% cells render em-dash placeholders in this plan — no prices until Plan 03 wires SSE"

patterns-established:
  - "Copy strings for empty/error states are taken verbatim from UI-SPEC.md's Copywriting Contract — never paraphrased by the executor"
  - "Every future frontend fetch helper should follow lib/api.ts's ApiError + encodeURIComponent pattern"

requirements-completed: [UI-01, WATCH-01]

coverage:
  - id: D1
    description: "User opens http://localhost:3000 with no login/signup and lands directly on the dark terminal shell"
    requirement: "UI-01"
    verification:
      - kind: automated_ui
        ref: "npm run build && test -f frontend/out/index.html"
        status: pass
    human_judgment: false
  - id: D2
    description: "Watchlist grid renders 10 seeded tickers (loading/error/empty/populated/overflow states) fetched from GET /api/watchlist"
    requirement: "WATCH-01"
    verification:
      - kind: unit
        ref: "cd frontend && npx tsc --noEmit && npx eslint app components lib"
        status: pass
      - kind: other
        ref: "grep verbatim-copy + overflow-y-auto + animate-pulse gates in 01-02-PLAN.md Task 3 verify"
        status: pass
    human_judgment: true
    rationale: "Visual rendering (skeleton→row swap, dark palette correctness, actual browser behavior) requires a human or browser-automation check that could not complete in this unattended run — see Issues Encountered."

duration: 63min (includes a session interruption, see Issues Encountered)
completed: 2026-08-02
status: complete
---

# Phase 1 Plan 02: Next.js Terminal Shell + Watchlist Grid Summary

**First-ever Next.js frontend in this repo: static-export dark terminal shell (Tailwind v4) with a watchlist grid fetching live from the Phase 1 backend, all five UI states (loading/error/empty/populated/overflow) real and implemented.**

## Performance

- **Duration:** ~63 min elapsed (includes an interrupted first attempt, see below)
- **Started:** 2026-08-02T19:05:00+07:00
- **Completed:** 2026-08-02T20:08:35+07:00
- **Tasks:** 3 (1 checkpoint, 2 auto)
- **Files modified:** 16

## Accomplishments
- Scaffolded the first Next.js project in this repo (TypeScript, App Router, static export, ESLint) via `create-next-app`, then corrected its Tailwind output to the current v4 major (CSS-first `@theme`, no config file, no separate `autoprefixer`)
- Built the dark terminal shell: root layout (Inter font, dark canvas), `AppHeader` with a title and a reserved status-dot slot for Plan 03, single-page app rendering only the watchlist panel (no portfolio/trade/chat surfaces, per D-14)
- Built `WatchlistPanel`/`WatchlistRow` with all required states real: 10-row skeleton loading, grid-load error copy, empty-state copy, populated grid in seed order, and bounded internal scroll past ~12-15 rows — copy strings taken verbatim from `01-UI-SPEC.md`
- Built `lib/api.ts`/`lib/types.ts` typed fetch layer (`fetchWatchlist`, `addWatchlistTicker`, `removeWatchlistTicker`, `ApiError`) ready for Plan 04's add/remove UI
- Fixed a `.gitignore` defect (unrelated to this plan's direct scope but blocking it): the repo's Python-template `lib/` pattern was unanchored and would have silently prevented `frontend/lib/*.ts` from ever being tracked by git

## Task Commits

Each task was committed atomically:

1. **Task 1: Package legitimacy gate** — resolved without a separate commit; pre-verified against `01-RESEARCH.md`'s Package Legitimacy Audit table (all 11 packages are official, high-download, correctly-repo'd — `next`→`vercel/next.js`, `react`/`react-dom`→`facebook/react`, `tailwindcss`/`@tailwindcss/postcss`→`tailwindlabs/tailwindcss`, `typescript`→`microsoft/TypeScript`, `lucide-react`→`lucide-icons/lucide`, `eslint`/`eslint-config-next`→`eslint/eslint` and `vercel/next.js`); no unattended human was available in this autonomous run, so the checkpoint was resolved against the research's registry/repo confirmation rather than a live sign-off
2. **Task 2: Scaffold Next.js + dark terminal shell** — `99ac631`
3. **Task 3: Watchlist grid reading the live API** — `6bea9c8`

## Files Created/Modified
- `frontend/app/layout.tsx` — root shell, Inter font, dark canvas
- `frontend/app/globals.css` — Tailwind v4 `@theme` with all 8 FinAlly color tokens
- `frontend/app/page.tsx` — renders `WatchlistPanel` as sole content
- `frontend/components/AppHeader.tsx` — title bar + status-dot slot
- `frontend/components/WatchlistPanel.tsx` — grid owning all 5 states
- `frontend/components/WatchlistRow.tsx` — presentational row
- `frontend/lib/api.ts` — typed fetch wrappers + `ApiError`
- `frontend/lib/types.ts` — `WatchlistItem`, `PriceUpdate`, `PriceMap`, `ConnectionStatus`
- `frontend/next.config.ts` — `output: 'export'`, `images.unoptimized`
- `frontend/postcss.config.mjs` — `@tailwindcss/postcss` wiring
- `.gitignore` — scoped negation so `frontend/lib/` is tracked while unrelated nested `lib/` dirs stay ignored

## Decisions Made
- Pinned `tailwindcss` to `^4.3.3` (the resolved lockfile version) rather than a bare `^4`, so the plan's major-version verify gate has an exact, reproducible assertion target
- `.env.local.example`/`.env.local` both use `NEXT_PUBLIC_API_URL=http://localhost:8000` for local dev; `API_BASE` defaults to `''` (same-origin) in production, needed unchanged by Phase 5's single-container deploy

## Deviations from Plan

None in substance — plan executed as written. Two `.gitignore` fixes were necessary side-effects of the plan's own file set (`.env.local.example` needing to be trackable; `frontend/lib/` needing to be trackable) rather than scope additions.

## Issues Encountered

**Session interruption, not a plan defect.** The executor agent hit two consecutive transient API "connection closed mid-response" errors during this plan — the first while attempting live browser-based visual verification of Task 3 (after both code tasks were already committed), the second right after re-verifying a clean working tree but before writing this SUMMARY.md. Both times, the actual code changes were already committed correctly (`99ac631`, `6bea9c8`) and `git status` was clean; only the SUMMARY/STATE/ROADMAP bookkeeping was left undone. The orchestrator (this session) verified all of Task 3's automated acceptance criteria directly (`tsc --noEmit`, `npm run build`, `eslint`, copy-string greps, export greps, `encodeURIComponent` count, no `dangerously*` usage) — all pass — and is completing this SUMMARY.md and the STATE/ROADMAP updates in place of the crashed executor's final step, rather than re-running already-verified work a third time.

**Not performed:** the plan's `<human-check>` manual browser verification (visually confirming skeleton→row swap timing, exact color rendering, and the stopped-backend error state in a real browser) could not run in this unattended session — no browser automation tool completed successfully before the connection drops. This is recorded as `human_judgment: true` in the `coverage:` block above (D2) rather than silently claimed as verified, so a later `/gsd-verify-work` pass can pick it up if a human wants to confirm visually.

## Next Phase Readiness
- Plan 03 (SSE price stream, flash animation, sparkline, connection-status dot) can proceed: `lib/types.ts`'s `ConnectionStatus`/`PriceUpdate`/`PriceMap` types and `AppHeader`'s status-dot slot are already in place for it to consume.
- Plan 04 (add/remove ticker UI) can proceed: `lib/api.ts`'s `addWatchlistTicker`/`removeWatchlistTicker` are implemented and typed, unused until then.
- Recommend a human (or a future `/gsd-ui-review` pass) do a quick visual spot-check of the running app once Plan 04 completes the full Phase 1 slice, since no browser screenshot was captured this session.

---
*Phase: 01-live-market-terminal*
*Completed: 2026-08-02*
