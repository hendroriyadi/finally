---
phase: 04-ai-copilot
plan: 02
subsystem: api
tags: [sqlite, fastapi, pydantic, chat, portfolio-context]

requires:
  - phase: 02-portfolio-engine
    provides: get_portfolio_state() and value_portfolio() — the sole valuation pair, reused unchanged
  - phase: 04-ai-copilot
    provides: "Plan 04-01's POST /api/chat, ChatResponse/ActionResult, and LLM_MOCK dispatch"
provides:
  - "app/db/chat.py: append_chat_message() / list_recent_chat_messages() — the sole reader/writer of chat_messages"
  - "GET /api/chat/history — bounded, chronological, no client-controlled input, survives a restart"
  - "POST /api/chat persists both turns of every conversation with actions JSON attached to the assistant row"
  - "SYSTEM_PROMPT + build_chat_messages() — pure prompt builder grounding every turn in fresh cash, holdings, P&L, watchlist prices, and bounded history"
affects: [04-03-watchlist-actions, 04-04-chat-panel-ui, phase-05-e2e]

actuals:
  tokens: 8600
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "app/db/chat.py copies db/snapshots.py's exact shape: prose docstring naming the one table it owns, module-level cap constant (MAX_CONTEXT_MESSAGES=20), inner _txn/_query handed to run_db, select-descending-then-reverse-in-Python idiom riding the existing index"
    - "build_chat_messages() is a pure, module-level function (no await, no I/O, no request) taking already-loaded portfolio/watchlist/history as arguments — the same 'context builder testable without a live call' shape 04-VALIDATION.md asked for"
    - "Persona and volatile context kept in two separate system messages so 'is the context fresh?' is answerable by looking at one string rather than diffing a concatenation"

key-files:
  created:
    - backend/app/db/chat.py
    - backend/tests/db/test_chat.py
  modified:
    - backend/app/routes/chat.py
    - backend/tests/routes/test_chat.py

key-decisions:
  - "actions=None stores SQL NULL (does not apply to this row kind); actions=[] stores a JSON empty array (this reply executed nothing) — the two are distinguished by a passing test, never collapsed"
  - "History is read before the new user row is written, so the message being answered can never appear in its own history — verified by a test that counts occurrences of the current turn's text in the recorded model input"
  - "Context rendering uses plain (non-comma-grouped) $X.XX formatting and an explicit 'unavailable' marker for a None price-derived field, never a zero — a zero price would read to the model as a worthless holding and could provoke a sell"
  - "No total, P&L, or percentage is computed in app/routes/chat.py — build_chat_messages() renders exactly the fields get_portfolio_state()+value_portfolio() already computed, avoiding a third valuation path"
  - "watchlist entries are re-priced per request via price_cache.get_price() at the call site, kept as plain {ticker, price} dicts rather than reusing WatchlistItem, since the prompt renderer needs the live price the wire model doesn't carry"

patterns-established:
  - "Pattern: a data-access module that owns exactly one table proves it with a test that inspects its own source for the other tables' names via regex, not just prose discipline (test_module_touches_only_chat_messages_table)"
  - "Pattern: freshness of a per-request-built context is proven by monkeypatching the LLM entry point with a message-recording double and asserting on what was *sent to the model*, not on what it replied — CHAT-02's recorder tests are the second instance of this after Plan 04-01's determinism tests"

requirements-completed: [CHAT-01, CHAT-02]

coverage:
  - id: D1
    description: "Every chat turn writes two durable rows (user + assistant), the assistant row's actions match the response body's actions, and a turn whose model call fails still leaves both rows with the fallback message and an empty action list"
    requirement: CHAT-01
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_a_completed_turn_leaves_exactly_two_new_rows"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_assistant_row_stored_actions_equal_response_body_actions"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_a_failed_model_call_still_leaves_both_rows_with_fallback_and_empty_actions"
        status: pass
    human_judgment: false
  - id: D2
    description: "append_chat_message()/list_recent_chat_messages() are correct in isolation: role/content/timestamp round-trip, actions JSON round-trips with nested numeric fields intact, NULL vs empty-array distinction holds, the cap keeps the newest window while still ordering oldest-first, and rows written through the async seam are readable from a brand-new independently opened connection (the restart-durability proof)"
    requirement: CHAT-01
    verification:
      - kind: unit
        ref: "backend/tests/db/test_chat.py (9 tests, all pass)"
        status: pass
    human_judgment: false
  - id: D3
    description: "GET /api/chat/history returns 200 with an empty list on a fresh database (never 404), returns both rows oldest-first with actions as a real JSON array after a turn, and declares no query/path/body parameter"
    requirement: CHAT-01
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_history_on_fresh_database_returns_200_with_empty_list"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_history_after_a_turn_returns_both_rows_oldest_first_with_actions_as_json_array"
        status: pass
    human_judgment: false
  - id: D4
    description: "build_chat_messages() renders live cash, holdings (with P&L), total value, and watchlist prices into a message list ordered persona/context/history/new-message, with a None price rendering an explicit unavailable marker rather than a zero, and the persona byte-identical across different portfolios"
    requirement: CHAT-02
    verification:
      - kind: unit
        ref: "backend/tests/routes/test_chat.py (7 pure-function tests, all pass)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Portfolio and watchlist context is re-read on every POST /api/chat call — a trade or watchlist addition made between two turns is visible in the second turn's recorded model input but absent from the first, proven by recording the input handed to the model rather than asserting on its output"
    requirement: CHAT-02
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_a_trade_between_two_turns_is_visible_in_the_second_recorded_context"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_a_watchlist_ticker_added_between_two_turns_is_visible_in_the_second_context"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_history_never_includes_the_message_currently_being_answered"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-08-04
status: complete
---

# Phase 4 Plan 2: Conversation Durability and Portfolio Grounding Summary

**`app/db/chat.py` gives the chat transcript a durable home (append/list over `chat_messages`, bounded by `MAX_CONTEXT_MESSAGES=20`) behind a new `GET /api/chat/history`, and `build_chat_messages()` grounds every `POST /api/chat` turn in cash, holdings with unrealized P&L, total value, and live watchlist prices re-read fresh on each request.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 2/2 completed
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `app/db/chat.py`: sole reader/writer of `chat_messages`, mirroring `db/snapshots.py`'s module shape exactly — module docstring naming the one table it owns, `MAX_CONTEXT_MESSAGES=20` bounding both the prompt window and the history endpoint, and the select-descending/reverse-in-Python idiom that keeps the newest window while returning it oldest-first
- `POST /api/chat` now persists both turns of every conversation: the user's row is written before the model call (so a failed call still leaves a record of what was asked), and the assistant's row carries the exact reply text and executed actions the response body returns
- `GET /api/chat/history` — no query/path/body parameter, 200 with `{"messages": []}` on a fresh database, both rows oldest-first with `actions` as a real JSON array after a turn
- `SYSTEM_PROMPT` (FinAlly persona, all six `PLAN.md` §9 behaviours plus a never-invent-a-figure instruction) and `build_chat_messages()` — a pure function assembling persona / volatile context / bounded history / new user message, with a `None` price rendering an explicit "unavailable" marker instead of a zero
- The POST handler re-reads `get_portfolio_state()` + `value_portfolio()` + `list_watchlist()` fresh on every request — proven by two recorder-based tests showing a manual trade and a watchlist addition made between two chat turns are visible in the second turn's model input but absent from the first
- 20 new tests (9 in `tests/db/test_chat.py`, 11 net-new in `tests/routes/test_chat.py`); full backend suite (193 tests) green

## Task Commits

1. **Task 1: A conversation that survives the request** - `95929cb` (test, RED) → `47c0392` (feat, GREEN)
2. **Task 2: An assistant that can see** - `c10f642` (test, RED) → `ec5c2a7` (feat, GREEN)

_Both tasks were `tdd="true"`; each RED commit's tests were run and observed failing (`ModuleNotFoundError` / 404 for Task 1's persistence and history endpoint; `ImportError`/assertion failures against the still-minimal inline prompt for Task 2) before the matching GREEN commit landed._

## Files Created/Modified
- `backend/app/db/chat.py` - `MAX_CONTEXT_MESSAGES`, `append_chat_message()`, `list_recent_chat_messages()` — the sole data-access module for `chat_messages`
- `backend/app/routes/chat.py` - extended: `SYSTEM_PROMPT`, `build_chat_messages()`, `ChatMessageOut`/`ChatHistoryResponse`, `GET /api/chat/history`, and a `POST ""` handler that persists both turns and builds its prompt from live portfolio/watchlist/history context
- `backend/tests/db/test_chat.py` - 9 tests: writer correctness, actions NULL-vs-empty-array distinction, cap-keeps-newest-window, oldest-first ordering, fresh-database empty list, independent-connection durability proof, and a source-inspection test proving the module touches only `chat_messages`
- `backend/tests/routes/test_chat.py` - extended with 20 new tests: route-level persistence (two rows per turn, stored actions match response, fallback-path persistence), the history endpoint's fresh/populated states, 7 pure-function `build_chat_messages()` tests, and 4 freshness/ordering proofs against a message-recording double

## Decisions Made
- `actions=None` stores SQL `NULL` (the column does not apply — every user row); `actions=[]` stores a JSON empty array (a real statement that this reply executed nothing). A db-layer test and a route-layer test each assert the distinction survives a round trip.
- The POST handler reads history via `list_recent_chat_messages()` *before* writing the new user row, so the message currently being answered can never appear in its own history — verified by counting occurrences of the current turn's exact text in the recorded model input.
- Context rendering avoids comma-grouped numeric formatting (`$8000.00`, not `$8,000.00`) — a minor formatting choice with no functional bearing, noted only because an early draft of the test suite assumed the former.
- `build_chat_messages()` takes an already-priced `watchlist: list[{"ticker", "price"}]` rather than reusing `WatchlistItem` (which carries `added_at`, not a live price) — the POST handler builds this list at the call site from `list_watchlist()` + `price_cache.get_price()`, keeping the pure builder free of any DI-specific type.
- No total, P&L, or percentage is computed anywhere in `app/routes/chat.py`; `build_chat_messages()` renders exactly the fields `get_portfolio_state()` + `value_portfolio()` already produced, so the chat context can never numerically drift from what `/api/portfolio` reports for the same state.

## Deviations from Plan

None — plan executed exactly as written. Every acceptance criterion and both tasks' automated `<verify>` blocks pass as specified; `backend/app/db/portfolio.py`, `backend/app/db/watchlist.py`, `backend/app/db/snapshots.py`, and `backend/app/db/connection.py` are untouched (confirmed via `git diff --stat`).

## Issues Encountered

None requiring rework beyond ordinary test-writing iteration: two Task 2 tests were adjusted after their first RED-to-GREEN pass revealed test-construction mistakes rather than implementation bugs — one used a substring assertion that didn't match `$X.XX` non-comma-grouped formatting, and the freshness-proof test's chosen "new" ticker (`NFLX`) turned out to already be part of the seeded default watchlist, so it was already visible in the first turn's watchlist section; the test was corrected to assert on the "Open holdings" section transitioning from empty to populated instead, which is the actual claim CHAT-02 makes.

## User Setup Required

None - no external service configuration required this plan. As in Plan 04-01, `OPENROUTER_API_KEY` resolving empty in this sandbox does not block any test — every test here exercises the code path via `LLM_MOCK=true` or a monkeypatched recorder over `mock_chat_completion`, per this plan's constraints.

## Next Phase Readiness

- `GET /api/chat/history`'s `{"messages": [...]}` envelope and `ChatMessageOut`'s `role`/`content`/`actions`/`created_at` shape are stable and ready for Plan 04-04's chat panel to consume on mount
- `build_chat_messages()`'s signature (`portfolio`, `watchlist`, `history`, `user_message`) is stable for Plan 04-03, which only needs to add the watchlist-changes execution loop `POST /api/chat` already reads `result.watchlist_changes` from (Plan 04-01's explicit scope boundary) — no change to the context builder is anticipated
- `MAX_CONTEXT_MESSAGES=20` is the one constant bounding both the prompt window and the history endpoint; no second, larger read path exists into `chat_messages`
- No blockers. Live-key verification of the real Cerebras-served model actually honoring the schema, and manual confirmation of steps 3-6 in `04-02-PLAN.md`'s `<verification>` block (which require a running backend), remain deferred to human/CI verification outside this sandbox — consistent with `04-CONTEXT.md`'s posture and this plan's dispatch constraints

---
*Phase: 04-ai-copilot*
*Completed: 2026-08-04*

## Self-Check: PASSED

All 5 created/modified files confirmed present on disk; all 4 task commits
(`95929cb`, `47c0392`, `c10f642`, `ec5c2a7`) confirmed in `git log`.
