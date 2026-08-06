---
phase: 04-ai-copilot
plan: 04
subsystem: ui
tags: [react, nextjs, chat, lucide-react]

requires:
  - phase: 04-ai-copilot
    provides: "POST /api/chat returning {message, actions[]} and GET /api/chat/history returning {messages[]} (Plans 04-01, 04-02); watchlist action results in the same actions array (Plan 04-03)"
  - phase: 02-manual-trading
    provides: "PortfolioProvider's refresh(), and TradeBar's non-optimistic in-flight-disable mutation discipline"
provides:
  - "ChatPanel — the docked, collapsible AI Copilot panel with transcript, input, thinking indicator, and collapse rail"
  - "ChatActionCard — inline confirmation card for one executed action (trade/watchlist x success/failure)"
  - "fetchChatHistory()/sendChatMessage() api helpers and the four chat wire types"
affects: [05-one-command-ship]

actuals:
  tokens: 10000
  tasks: 2
  commits: 1

tech-stack:
  added: []
  patterns:
    - "A layout-level flex dock (page content + panel as siblings) rather than an overlay, so collapsing the panel lets the page content reclaim the width with no layout-file change"

key-files:
  created: [frontend/components/ChatPanel.tsx, frontend/components/ChatActionCard.tsx]
  modified: [frontend/lib/types.ts, frontend/lib/api.ts, frontend/app/layout.tsx]

key-decisions:
  - "Panel spacing (margins) lives on the aside inside ChatPanel.tsx rather than on the layout wrapper, because page.tsx's <main> already carries px-8 py-6 and the plan forbids modifying it — a padded wrapper would have double-padded the dashboard"
  - "No eslint-disable on the mount effect: unlike WatchlistPanel's, this effect closes over no prop or state value, so react-hooks/exhaustive-deps is already satisfied and the directive would be flagged as unused"

patterns-established: []

requirements-completed: [CHAT-01, CHAT-05, UI-04]

coverage:
  - id: D1
    description: "A docked, collapsible chat panel with message input, scrolling transcript, and loading indicator, on both wide and narrow viewports"
    requirement: UI-04
    verification:
      - kind: unit
        ref: "npm run build (static export prerender, verifies no SSR crash and correct prop wiring)"
        status: pass
    human_judgment: true
    rationale: "Dock/stack responsive behavior, collapse-rail interaction, and draft/scroll preservation across collapse require a live browser session — no frontend test framework exists yet (TEST-03 is Phase 5's scope)."
  - id: D2
    description: "Sending shows the user's text immediately, a thinking indicator while awaiting the reply, and the assistant's response when it arrives, with no optimistic assistant content; conversation survives a page refresh"
    requirement: CHAT-01
    verification:
      - kind: unit
        ref: "grep gates: 'FinAlly is thinking' present, fetchChatHistory called on mount, no assistant bubble rendered before response"
        status: pass
    human_judgment: true
    rationale: "The send lifecycle and reload persistence are source-verified but need a live session with a running backend to confirm end to end."
  - id: D3
    description: "Every executed action renders as its own inline card immediately after the reply and again after a reload, with failures carrying the backend's own sentence verbatim"
    requirement: CHAT-05
    verification:
      - kind: unit
        ref: "grep gates: ChatActionCard renders action.error unmodified; one card per entry; none when array empty/null"
        status: pass
    human_judgment: true
    rationale: "Card rendering/coloring correctness needs a live browser session with real executed actions."

duration: ~15min
completed: 2026-08-04
status: complete
---

# Phase 4, Plan 04: The Docked AI Copilot Panel Summary

**A 384px right-hand dock (collapsing to a 56px rail) with a scrolling transcript, growing input, thinking indicator, and one inline confirmation card per action the assistant executed — the surface the other three plans were only reachable through.**

## Performance

- **Tasks:** 2 completed
- **Files modified:** 5 (2 created, 3 modified)
- **Note:** executed directly by the orchestrator — the subagent dispatched for this plan failed on a session usage limit before writing any file, and the established recovery pattern after repeated subagent failure is to do it inline.

## Accomplishments
- Four chat wire types in `lib/types.ts` with the deliberate `ChatMessage.actions` nullable / `ChatResponse.actions` non-nullable asymmetry
- `fetchChatHistory()` / `sendChatMessage()` in `lib/api.ts`, built exactly like the existing envelope-unwrapping helpers
- `ChatPanel` — transcript with all five states (history error, skeleton, empty, populated, thinking), Enter-to-send with Shift+Enter for newline, a textarea growing to a 96px cap then scrolling internally, in-flight send disable, `role="alert"` send-failure copy, auto-scroll keyed on exactly the two moments new content arrives, and a collapse toggle that hides rather than unmounts
- `ChatActionCard` — four success strings verbatim from the UI-SPEC copy contract, failures rendering the backend's own sentence unchanged, positive/destructive washes with check/alert icons, `tabular-nums` figures
- Layout dock: header above a `xl:flex-row` region holding the page content (with the load-bearing `min-w-0`) and the panel
- `npm run lint` and `npm run build` (full static export) both clean; all 33 acceptance-criteria grep gates pass; `app/page.tsx` byte-identical

## Task Commits

Both tasks landed in one commit (`5d5898e`) — Task 2's card component and collapse control are inseparable from Task 1's transcript loop in a single new file, and splitting them would have meant committing a `ChatPanel` that renders no confirmations, i.e. a state violating this phase's own safety property.

## Files Created/Modified
- `frontend/lib/types.ts` - `ChatRole`, `ChatActionResult`, `ChatMessage`, `ChatResponse`
- `frontend/lib/api.ts` - `fetchChatHistory()`, `sendChatMessage()`
- `frontend/components/ChatPanel.tsx` - the docked panel
- `frontend/components/ChatActionCard.tsx` - inline confirmation card
- `frontend/app/layout.tsx` - the flex dock region

## Decisions Made
- **Panel spacing moved into `ChatPanel.tsx`.** The plan's literal layout snippet had no padding, but `page.tsx`'s `<main>` already carries `px-8 py-6` and the plan forbids touching it — a padded wrapper would have double-padded the dashboard. Putting the margins on the `aside` itself keeps the panel's spacing self-contained and leaves the dashboard exactly as it was.
- **Dropped the planned `eslint-disable` on the mount effect.** ESLint flagged it as an *unused* directive: unlike `WatchlistPanel`'s effect, this one closes over no prop or state value, so `react-hooks/exhaustive-deps` is already satisfied. Left an explanatory comment in its place so a later reader doesn't re-add it.

## Deviations from Plan
Both items above are minor mechanical adaptations to the existing codebase rather than departures from the plan's intent; no behavior specified by the plan was changed, added, or dropped.

## Issues Encountered
- The `gsd-executor` dispatched for this plan failed on a session usage limit before writing any file. Executed inline instead.

## Next Phase Readiness
- Phase 4 is code-complete across all four plans. Ready for code review → fix → phase verification.
- Live-browser verification of the panel (dock/stack responsiveness, collapse behavior, send lifecycle, card rendering) remains deferred per this project's established Phase 1/2/3 pattern.

---
*Phase: 04-ai-copilot*
*Completed: 2026-08-04*
