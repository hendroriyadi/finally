---
phase: 04-ai-copilot
verified: 2026-08-04T13:30:00Z
status: human_needed
score: 5/5 truths present+wired, 4 behavior-unverified (live browser + live API key not exercised)
behavior_unverified: 4
behavior_unverified_items:
  - truth: "User opens a docked, collapsible chat panel, sends a message, sees a loading indicator while waiting, and receives a reply; the conversation scrolls and survives a page refresh"
    test: "Start backend and frontend (both backgrounded), open the app, send a message, reload the page"
    expected: "Panel docks right at xl and stacks below on narrow; the typed message appears immediately, then the thinking row, then the reply; reloading restores the transcript"
    why_human: "The send lifecycle, dock/stack responsiveness, and collapse behavior are source-verified and the static export prerenders cleanly, but no frontend test framework exists yet (TEST-03 is Phase 5's scope) and a live browser session was not exercised in this unattended run"
  - truth: "Asking about the portfolio produces a reply grounded in the user's actual cash, positions, P&L, and watchlist prices, and follow-up questions retain the earlier conversation"
    test: "With a real OPENROUTER_API_KEY, ask 'what do I hold?' then a follow-up referring to the first answer"
    expected: "The reply quotes actual holdings/cash, and the follow-up demonstrates the model saw the earlier turn"
    why_human: "The prompt-construction half is fully automated-tested (build_chat_messages is a pure function, with tests proving a trade made between two turns appears in the second turn's input but not the first). What cannot be verified here is the model's actual output quality, because OPENROUTER_API_KEY resolves to an empty string in this sandbox — a sandbox boundary, not a project misconfiguration"
  - truth: "Telling the assistant to buy or sell executes the trade through the exact same validated function the trade bar uses — cash, positions, header value, and charts all update — and the chat shows an inline confirmation"
    test: "With the backend under LLM_MOCK=true, send 'buy 2 AAPL' and watch the header, positions table, heatmap, and P&L chart"
    expected: "All four surfaces move, and a green confirmation card renders beneath the reply"
    why_human: "The backend half is fully test-proven (an AI trade debits cash identically to a manual one, and records a snapshot). The UI half — the four surfaces visibly updating via the shared provider's refresh(), and the card rendering — needs a live browser"
  - truth: "An impossible or malformed AI action produces a graceful explanation instead of a crash or an unvalidated trade, and LLM_MOCK=true returns deterministic replies without calling OpenRouter"
    test: "Send a message triggering an impossible action (e.g. a buy far beyond cash) and confirm the transcript explains it"
    expected: "HTTP 200 with a red failure card carrying the same sentence the trade bar would show"
    why_human: "Every branch of this is automated-tested at the API level (insufficient cash, unknown ticker, malformed model output, LLM call failure — all asserted to return 200 with a readable per-action error). Only the visual rendering of the failure card is unverified"
---

# Phase 4: AI Copilot Verification Report

**Phase Goal:** A user can converse with a portfolio-aware AI assistant that analyzes their holdings and executes trades and watchlist changes on their behalf
**Verified:** 2026-08-04T13:30:00Z
**Status:** human_needed

## Goal Achievement

### Observable Truths

| # | Truth (from ROADMAP success criteria) | Status | Evidence |
|---|-------|--------|----------|
| 1 | Docked collapsible panel; send, loading indicator, reply; scrolls; survives refresh | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `ChatPanel.tsx`: 384px `xl` dock / 56px rail, all five transcript states with UI-SPEC copy verbatim, thinking row as a status indicator (never an assistant bubble), `fetchChatHistory()` on mount for refresh-survival, bounded internally-scrolling transcript, collapse hides rather than unmounts. `npm run build` prerenders it cleanly. Live browser not exercised. |
| 2 | Reply grounded in actual cash/positions/P&L/watchlist; follow-ups retain conversation | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `build_chat_messages()` is a pure function with direct tests; the POST handler re-reads `get_portfolio_state()`+`value_portfolio()`+`list_watchlist()` fresh every turn (never cached), and history is read *before* the new user row is written so a message can't appear in its own history. Tests prove a trade made between two turns appears in the second turn's model input but not the first. Model output quality unverifiable — no working API key in this sandbox. |
| 3 | AI buy/sell runs through the same validated `execute_trade()`; all surfaces update; inline confirmation | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `_execute_trade_action()` calls `execute_trade()` directly (that function is byte-identical to its Phase 2 state) plus `record_portfolio_snapshot()`, so the P&L chart moves immediately rather than up to 30s later. A test asserts an AI-initiated buy debits cash *exactly* as a manual trade of the same size does. `ChatPanel` calls the shared `PortfolioProvider.refresh()` after any succeeded action, so header/positions/heatmap move from one source. Visual confirmation not exercised. |
| 4 | AI watchlist add/remove updates the grid, shown inline | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `_execute_watchlist_action()` calls the shared `apply_watchlist_add`/`apply_watchlist_remove` helpers, which own the only copy of the persist-then-track-then-compensate sequence. **Proven non-vacuous by a mutation spot-check**: stubbing out the `market_source.add_ticker` call makes `test_mock_triggered_watchlist_add_starts_the_price_feed` fail on the price lookup, exactly as 04-RESEARCH's Pitfall 2 predicts. Visual grid update not exercised. |
| 5 | Impossible/malformed action explains gracefully; `LLM_MOCK=true` is deterministic and offline | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Every failure branch asserted to return HTTP 200 with a readable per-action error: insufficient cash, unknown ticker, shape-invalid ticker, duplicate/not-found watchlist, malformed model JSON, schema-violating JSON, raised litellm exception, empty `choices`. `test_mock_never_calls_litellm` monkeypatches `litellm.completion` to raise, proving the mock path truly never reaches it. Only the failure card's rendering is unverified. |

**Score:** 5/5 truths present and wired; all 5 flagged behavior-unverified pending a live browser session (and, for truth 2, a working API key) — consistent with Phases 1-3's verification posture.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/app/llm/schemas.py` | The PLAN.md §9 structured-output contract | ✓ EXISTS + SUBSTANTIVE | Three models; `Literal` unions on side/action turn a hallucinated third value into a parse failure handled once |
| `backend/app/llm/client.py` | Real LiteLLM/OpenRouter/Cerebras call | ✓ EXISTS + SUBSTANTIVE | Skill pattern verbatim, 30s timeout, returns `None` on every failure mode, never raises |
| `backend/app/llm/mock.py` | Deterministic `LLM_MOCK=true` responses | ✓ EXISTS + SUBSTANTIVE | Pure, never imports litellm, round-trips the same Pydantic shape as the real client |
| `backend/app/db/chat.py` | Sole reader/writer of `chat_messages` | ✓ EXISTS + SUBSTANTIVE | Mirrors `snapshots.py`'s one-module-one-table discipline; `MAX_CONTEXT_MESSAGES=20` |
| `backend/app/routes/chat.py` | `POST /api/chat` + `GET /api/chat/history` | ✓ EXISTS + SUBSTANTIVE | Per-action executors with catch-alls; no SQL; no watchlist mutation import |
| `backend/app/routes/watchlist.py` | Extracted shared helpers | ✓ EXISTS + SUBSTANTIVE | Purpose-named errors; 11 pre-existing route tests pass with no test function edited |
| `frontend/components/ChatPanel.tsx` | The docked panel | ✓ EXISTS + SUBSTANTIVE | All five states; component-local state only (no new context, no localStorage) |
| `frontend/components/ChatActionCard.tsx` | Inline confirmation card | ✓ EXISTS + SUBSTANTIVE | Four success strings verbatim; failures render the backend's own sentence unchanged |

**Artifacts:** 8/8 verified

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| `routes/chat.py` | `db/portfolio.py` | `execute_trade()` directly — the CHAT-03 contract | ✓ WIRED |
| `routes/chat.py` | `db/snapshots.py` | `record_portfolio_snapshot()` after every AI fill (Pitfall 3) | ✓ WIRED |
| `routes/chat.py` | `routes/watchlist.py` | the shared helpers, never the data-access mutators (Pitfall 2) | ✓ WIRED |
| `routes/chat.py` | `db/chat.py` | both turns persisted; history read before the user row is written | ✓ WIRED |
| `main.py` | `routes/chat.py` | `create_chat_router()` mounted alongside the other three | ✓ WIRED |
| `ChatPanel.tsx` | `lib/api.ts` | `fetchChatHistory()` on mount, `sendChatMessage()` on send | ✓ WIRED |
| `ChatPanel.tsx` | `PortfolioProvider` | `refresh()` after any succeeded action — no second fetch path | ✓ WIRED |
| `layout.tsx` | `ChatPanel.tsx` | flex sibling of the page content, `min-w-0` on the content wrapper | ✓ WIRED |

**Wiring:** 8/8 connections verified

## Requirements Coverage

| Requirement | Status |
|-------------|--------|
| CHAT-01 (structured response; conversation survives refresh) | ✓ SATISFIED |
| CHAT-02 (fresh portfolio context + history every turn) | ✓ SATISFIED |
| CHAT-03 (trades via the exact same validated function) | ✓ SATISFIED |
| CHAT-04 (AI watchlist add/remove) | ✓ SATISFIED |
| CHAT-05 (actions shown inline as confirmations) | ✓ SATISFIED |
| CHAT-06 (failed actions explain gracefully, never crash) | ✓ SATISFIED |
| CHAT-07 (deterministic `LLM_MOCK=true`) | ✓ SATISFIED |
| UI-04 (docked/collapsible panel, input, scrolling history, loading indicator) | ✓ SATISFIED |
| TEST-02 (LLM structured-output parsing incl. malformed responses) | ✓ SATISFIED |

**Coverage:** 9/9 requirements satisfied

## Anti-Patterns Found

None remaining. The Phase 4 code review found 1 critical + 4 warning + 3 info; **all 8 are fixed** (see
`04-REVIEW-FIX.md`). Two proved more serious than filed: WR-01's suggested fix was measurably
insufficient on its own and needed a retry, and IN-03 was guarding a latent `.toFixed()` crash rather
than a cosmetic type mismatch.

**Anti-patterns:** 0 found

## Human Verification Required

1. **Live chat round trip with a real API key** — set a working `OPENROUTER_API_KEY` and confirm the
   model returns schema-valid structured output, that its replies are grounded in the real portfolio,
   and that latency is low enough for the single-loading-state design. This is the one item that could
   not be exercised *at all* here (the key resolves empty in this sandbox), and it is the phase's
   only genuinely unvalidated external dependency.
2. **Panel layout and interaction** — dock/stack responsiveness, collapse-to-rail preserving an unsent
   draft and scroll position, Enter-to-send with Shift+Enter for a newline.
3. **The four dashboard surfaces updating from a chat-initiated trade** — header total, positions
   table, heatmap, and P&L chart.
4. **Inline confirmation cards rendering** — green success, red failure, one per action, and still
   present after a page reload.

## Gaps Summary

**No gaps found.** Every observable truth is present, wired, requirement-mapped, and free of
anti-patterns. Status is `human_needed` rather than `passed` because live-browser confirmation was not
performed in this unattended run, and because the real LLM path could not be exercised without a
working API key. Neither is a code-level defect. Phase 5 (One-Command Ship) can proceed — it packages
and E2E-tests this phase under `LLM_MOCK=true`, which is fully verified here, and its Playwright suite
is the natural place for the browser-level checks listed above.

## Verification Metadata

**Verification approach:** Goal-backward from ROADMAP.md Phase 4's five success criteria, performed by
direct source reading and automated suite runs (consistent with Phases 1-3, and with this session's
pattern after repeated subagent session-limit failures).
**Automated checks:** backend `pytest -q` → 209/209 passed, 3 consecutive runs; `ruff check` clean;
`test_concurrent_init_db_calls_do_not_raise` 25/25 after the WR-01 fix; frontend `npm run lint` clean,
`npm run build` static export completes.
**Notable evidence:** the Pitfall-2 guard was proven non-vacuous by a mutation spot-check, and the
WR-01 fix was chosen by measurement (3 → 2 → 0 failures across three candidate implementations).
**Human checks required:** 4 (one blocking-for-confidence: the live API key path)

---
*Verified: 2026-08-04T13:30:00Z*
*Verifier: Claude (orchestrator, direct)*
