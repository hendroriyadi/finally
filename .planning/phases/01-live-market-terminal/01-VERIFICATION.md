---
phase: 01-live-market-terminal
verified: 2026-08-03T04:35:00Z
status: human_needed
score: 5/5 truths present+wired, 5 behavior-unverified (live browser rendering not exercised)
behavior_unverified: 5
behavior_unverified_items:
  - truth: "Prices in the grid update live from the SSE stream, flashing green on an uptick and red on a downtick, fading out within about 500ms"
    test: "Start backend (uv run uvicorn app.main:create_app --factory --port 8000) and frontend (npm run dev), open http://localhost:3000, watch a row for at least one price tick"
    expected: "Price cell background briefly tints green/red then fades to normal within ~500ms, driven by the CSS transition-colors duration-500 class"
    why_human: "The flash timer/color logic is unit-provable from source (WatchlistRow.tsx price-comparison effect + 500ms setTimeout), but the actual visual fade timing and color rendering require a real browser paint — no test exercises it"
  - truth: "Each watchlist row shows daily change % and a sparkline that fills in progressively from prices received since page load"
    test: "Watch a row's sparkline over several SSE ticks after page load"
    expected: "Sparkline SVG polyline gains points and its shape updates as more prices arrive, never resetting"
    why_human: "Sparkline accumulation logic (useSseStream's historyRef) and rendering (Sparkline.tsx polyline) are both source-verified as correct, but progressive visual fill-in over real time requires a live session to observe"
  - truth: "User can add and remove tickers; the change survives a page refresh and a backend restart, and a newly added ticker starts streaming prices"
    test: "Add a ticker, refresh the page, restart the backend, confirm it's still there and its price cell fills in; remove a ticker and repeat"
    expected: "Ticker persists in the grid and price stream across refresh and backend restart"
    why_human: "DB persistence (backend/tests/db/, backend/tests/routes/test_watchlist.py) and market-source tracking (lifespan re-seeds from persisted watchlist in main.py) are both unit/integration-tested against the DB and mocked market source, but the full page-refresh + backend-restart round trip in a real browser was not exercised"
  - truth: "If the price stream drops, prices resume on their own without a manual refresh"
    test: "Kill the backend while the frontend is open, then restart it, without reloading the page"
    expected: "Connection-status dot goes yellow (or red once WR-05's readyState fix applies), then prices resume streaming once the backend is back, all without a page reload"
    why_human: "EventSource's native retry behavior is a browser platform guarantee (no custom reconnect code exists, by design — see 01-CONTEXT.md), and the WR-05 fix to distinguish CONNECTING vs CLOSED is source-verified, but observing the actual reconnect sequence requires a live browser session"
  - truth: "User opens the app at a single URL with no login or signup and sees a dark, data-dense terminal layout listing the 10 default tickers"
    test: "Open http://localhost:3000 fresh (empty DB) with no prior session/cookies"
    expected: "Page loads directly into the dark terminal (no auth screen), ten tickers visible in seed order"
    why_human: "No auth code exists anywhere in the app (confirmed by source inspection — no login routes, no session middleware), and the static export (frontend/out/index.html) builds successfully with the watchlist panel as the only content region, but the actual rendered dark-palette appearance was not visually confirmed in a browser"
---

# Phase 1: Live Market Terminal Verification Report

**Phase Goal:** A user opens one URL with no login and watches a live, editable watchlist stream real prices in a dark trading-terminal UI
**Verified:** 2026-08-03T04:35:00Z
**Status:** human_needed

## Goal Achievement

### Observable Truths

| # | Truth (from ROADMAP success criteria) | Status | Evidence |
|---|-------|--------|----------|
| 1 | User opens app at single URL, no login, dark terminal, 10 default tickers | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | No auth code anywhere (grep confirms no login/session routes); `frontend/app/page.tsx` renders only `WatchlistPanel`; `backend/app/db/init.py` seeds exactly the 10 `SEED_PRICES` tickers; `npm run build` produces `frontend/out/index.html` successfully. Live visual rendering not exercised. |
| 2 | Prices flash green/red on tick, fade ~500ms | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `WatchlistRow.tsx`'s price-comparison `useEffect` sets `flash` state on price change and clears it via `setTimeout(..., 500)`; `transition-colors duration-500` CSS class applies the fade. Logic and timer are source-correct; real-browser paint not observed. |
| 3 | Change % + progressive sparkline shown per row | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `useSseStream.ts`'s `historyRef`/`baselinesRef` accumulate per-ticker series since mount, capped at `MAX_SPARKLINE_POINTS=60`; `Sparkline.tsx` renders a flat baseline below 2 points, a polyline above; `WatchlistRow.tsx` derives change-% color from the session-baseline percentage. Wiring confirmed end-to-end; progressive visual fill-in not observed live. |
| 4 | Add/remove ticker persists across refresh + backend restart, streams without restart | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `backend/app/routes/watchlist.py` persists then tracks (add) / untracks then persists-removal (remove), both with WR-02 compensation on market-source failure; `main.py`'s lifespan re-seeds the market source from the *persisted* watchlist on every startup, so a restart reloads exactly what's in SQLite. Covered by `backend/tests/routes/test_watchlist.py` and `backend/tests/db/`. Full page-refresh + process-restart round trip in a live browser not exercised. |
| 5 | Stream resumes on its own after a drop, no manual refresh | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | No custom reconnect logic exists by design (`01-CONTEXT.md` decision) — relies entirely on native `EventSource` retry driven by the server's `retry: 1000` directive (frozen `market/stream.py`, unmodified this phase). `useSseStream.ts`'s `onerror` (post-WR-05 fix) correctly distinguishes `CONNECTING` (still retrying) from `CLOSED` (given up). Platform behavior + source-correct status handling; live reconnect sequence not observed. |

**Score:** 5/5 truths present and wired; all 5 flagged as behavior-unverified pending a live browser session (not a gap — the underlying logic for every one is directly verified in source and, where applicable, by automated tests).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/db/schema.sql` + `init.py` | Six-table lazy-init schema, idempotent, race-safe | ✓ EXISTS + SUBSTANTIVE | `INSERT OR IGNORE` seed (post-WR-04 fix); `backend/tests/db/test_init.py` covers idempotency and concurrent-call safety |
| `backend/app/db/connection.py` | WAL + busy_timeout connection factory | ✓ EXISTS + SUBSTANTIVE | Verified via `backend/tests/db/test_connection.py` |
| `backend/app/routes/watchlist.py` | GET/POST/DELETE `/api/watchlist` | ✓ EXISTS + SUBSTANTIVE | Cap enforcement (WR-01), compensation (WR-02), tightened validation (IN-02/03) all present per REVIEW-FIX.md |
| `backend/app/main.py` | FastAPI app assembly, lifespan, CORS, SSE mount | ✓ EXISTS + SUBSTANTIVE | `create_app()` wires DB init, market source (re-seeded from persisted watchlist), exact-origin CORS allowlist, both routers |
| `frontend/app/layout.tsx` + `page.tsx` | Dark shell, single-panel app | ✓ EXISTS + SUBSTANTIVE | `PriceStreamProvider` wraps `AppHeader` + page content; `page.tsx` renders only `WatchlistPanel` |
| `frontend/components/WatchlistPanel.tsx` | Grid owning loading/error/empty/populated/overflow states | ✓ EXISTS + SUBSTANTIVE | All 5 states implemented per `01-02-PLAN.md`/`01-04-PLAN.md` acceptance criteria, verified by `grep` gates in those plans |
| `frontend/lib/useSseStream.ts` | Single shared `EventSource`, accumulator refs | ✓ EXISTS + SUBSTANTIVE | Exactly one `new EventSource` in the whole tree (grep-verified in `01-03-SUMMARY.md`); WR-05 readyState fix applied |
| `frontend/components/{AddTickerForm,RemoveTickerButton}.tsx` | Non-optimistic add/remove with full state coverage | ✓ EXISTS + SUBSTANTIVE | WR-06 error-handling fix applied to both |

**Artifacts:** 8/8 verified

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `main.py` lifespan | `init_db()` | `await init_db()` before market source starts | ✓ WIRED | Line 34 |
| `main.py` lifespan | market source | `create_market_data_source(cache)` seeded from `list_watchlist()` | ✓ WIRED | Lines 36-39 — restart-safe: reloads from DB, not `SEED_PRICES` directly |
| `main.py` | SSE stream | `app.include_router(create_stream_router(cache))` | ✓ WIRED | Line 62, frozen market subsystem mounted unmodified |
| `main.py` | watchlist routes | `app.include_router(create_watchlist_router())` | ✓ WIRED | Line 63 |
| `layout.tsx` | `PriceStreamProvider` | wraps `AppHeader` + `{children}` | ✓ WIRED | Single EventSource for the whole page |
| `AppHeader.tsx` | `ConnectionStatusDot` | `usePriceStreamContext().status` | ✓ WIRED | Line 12, 18 |
| `WatchlistPanel.tsx` | `usePriceStreamContext` | reads `prices`/`history`/`baselines` for each row | ✓ WIRED | Confirmed via `01-03-SUMMARY.md` and direct read |
| `WatchlistPanel.tsx` | `AddTickerForm`/`RemoveTickerButton` | `onAdded`/`onRemoved` mutate `items` state | ✓ WIRED | Confirmed via `01-04` diffs |
| `lib/api.ts` | `backend/app/routes/watchlist.py` | fetch against `${API_BASE}/api/watchlist` | ✓ WIRED | `encodeURIComponent` used on path params |

**Wiring:** 9/9 connections verified

## Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|-----------------|
| DB-01 (persist cash/watchlist/positions/trades/snapshots/chat) | ✓ SATISFIED | All 6 tables in schema.sql |
| DB-02 (lazy init, no manual migration) | ✓ SATISFIED | `init_db()`, race-safe post-WR-04 |
| DB-03 (WAL + busy_timeout) | ✓ SATISFIED | `connection.py`, tested |
| STREAM-01 (SSE at `/api/stream/prices`) | ✓ SATISFIED | Mounted, frozen subsystem |
| STREAM-02 (frontend auto-reconnect) | ✓ SATISFIED | Native `EventSource`, no custom logic by design |
| WATCH-01 (10 default tickers) | ✓ SATISFIED | Seeded from `SEED_PRICES` |
| WATCH-02 (add ticker) | ✓ SATISFIED | POST route + `AddTickerForm` |
| WATCH-03 (remove ticker) | ✓ SATISFIED | DELETE route + `RemoveTickerButton` |
| WATCH-04 (live price/change%/sparkline) | ✓ SATISFIED | `useSseStream` + `Sparkline` |
| WATCH-05 (flash animation ~500ms) | ✓ SATISFIED | `WatchlistRow` flash effect |
| UI-01 (dark, data-dense, no login) | ✓ SATISFIED | No auth code; dark theme tokens in `globals.css` |

**Coverage:** 11/11 requirements satisfied (all pending the same live-browser confirmation noted above — none are code-level gaps)

## Anti-Patterns Found

None. No `TODO`, no placeholder returns, no stub components found in the reviewed source. The Phase 1 code review (`01-REVIEW.md`) found 6 Warning + 3 Info logic/race issues (no security blockers); all 9 are fixed and verified in `01-REVIEW-FIX.md`.

**Anti-patterns:** 0 found

## Human Verification Required

All 5 items below stem from the same root cause: **no live browser session was exercised during this phase's execution.** Three separate automated attempts (2× UI-auditor, 3× phase-verifier across this and a prior session) to run live dev servers or take browser screenshots stalled or crashed — root-caused mid-session to foreground (non-backgrounded) server-start Bash calls hanging the tool call indefinitely. Every item below is source-correct and, where testable without a browser, test-covered; what's missing is purely the visual/live-session confirmation.

### 1. Fresh-load appearance and no-auth flow
**Test:** `cd backend && uv run uvicorn app.main:create_app --factory --port 8000` (backgrounded) and `cd frontend && npm run dev` (backgrounded), open `http://localhost:3000` in a browser.
**Expected:** Dark terminal loads directly, no login/signup screen, 10 tickers visible (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX) in that order.
**Why human:** Visual rendering and the absence of any auth interstitial can only be confirmed by looking at the page.

### 2. Price flash animation
**Test:** Watch a watchlist row through at least one price tick.
**Expected:** Price cell briefly tints green (up) or red (down), fades to normal over ~500ms.
**Why human:** CSS transition timing/visual appearance requires a real paint.

### 3. Progressive sparkline fill-in
**Test:** Watch a row's sparkline over several seconds after page load.
**Expected:** The line gains points and its shape changes as new prices arrive.
**Why human:** Progressive visual accumulation over real time.

### 4. Add/remove ticker persistence across refresh and backend restart
**Test:** Add a ticker, refresh, restart the backend process, confirm it's still present and streaming; remove a ticker and repeat.
**Expected:** State survives both refresh and backend restart; a newly added ticker starts showing live prices without further action.
**Why human:** Full round-trip across process restart + browser session.

### 5. Stream auto-resume after a drop
**Test:** Kill the backend while the frontend tab stays open, wait, restart the backend, do not reload the page.
**Expected:** Connection dot changes color appropriately and prices resume on their own once the backend returns.
**Why human:** Live network-failure/recovery sequence.

## Gaps Summary

**No gaps found.** Every observable truth is present, wired, requirement-mapped, and free of anti-patterns. Status is `human_needed` rather than `passed` solely because live-browser confirmation of visual/timing behavior was not performed in this unattended session (see Human Verification Required above) — this is an honest recording of an unverified-but-implemented state, not a defect. Recommend running `/gsd-verify-work 1` (or a manual pass through the 5 items above) with a real browser session before considering Phase 1 fully closed, but there is no code-level reason to block progress to Phase 2 in the meantime — Phase 2 (Manual Trading) builds on the persistence layer and API contracts, both of which are independently unit/integration-tested and unaffected by whether the Phase 1 UI has been eyeballed yet.

## Verification Metadata

**Verification approach:** Goal-backward (derived from ROADMAP.md Phase 1 success criteria), performed via direct source-code reading and automated test suite runs (not by a fresh subagent — after 3 consecutive stalls/crashes on this exact task, likely caused by unbackgrounded dev-server starts, the orchestrator completed this verification directly rather than risk a 4th failed attempt).
**Must-haves source:** ROADMAP.md Phase 1 section + all 4 plans' `must_haves` blocks
**Automated checks:** backend `uv run --extra dev pytest -q` → 94/94 passed, `ruff check` clean; frontend `npx tsc --noEmit`, `npx eslint app components lib`, `npm run build` → all clean
**Human checks required:** 5 (all live-browser confirmations, none blocking)
**Total verification time:** ~15 min (direct source inspection, no subagent dispatch)

---
*Verified: 2026-08-03T04:35:00Z*
*Verifier: Claude (orchestrator, direct — see Verification Metadata)*
