---
phase: 04-ai-copilot
plan: 01
subsystem: api
tags: [litellm, openrouter, cerebras, pydantic, fastapi, structured-output, llm]

requires:
  - phase: 02-portfolio-engine
    provides: execute_trade() — the sole cash/position/trade mutation path, reused unchanged
  - phase: 03-charts-and-snapshots
    provides: record_portfolio_snapshot() — the immediate post-fill value-chart writer, reused unchanged
provides:
  - "POST /api/chat: free-text message in, {message, actions[]} confirmation out, never a 5xx"
  - "app/llm/ package (schemas.py, mock.py, client.py) — the project's only model-facing code"
  - "LLM_MOCK=true deterministic dispatch, read per-request, proven to never reach litellm"
  - "Real LiteLLM/OpenRouter/Cerebras structured-output client that returns None on every failure mode"
affects: [04-02-conversation-grounding, 04-03-watchlist-actions, 04-04-chat-panel-ui, phase-05-e2e]

actuals:
  tokens: 8300
  tasks: 2
  commits: 2

tech-stack:
  added: [litellm@1.95.0 (already installed, first use), pydantic@2.12.5 (already installed, first direct import)]
  patterns:
    - "app/llm/ mock-vs-real dispatch resolved per-request (os.environ read inside the handler), mirroring create_market_data_source()'s shape but deliberately NOT its once-per-process resolution timing"
    - "Blocking SDK call wrapped in asyncio.to_thread(), mirroring run_db()'s seam for blocking SQLite I/O"
    - "Per-action try/except loop so one bad action never fails an entire multi-action reply"

key-files:
  created:
    - backend/app/llm/__init__.py
    - backend/app/llm/schemas.py
    - backend/app/llm/mock.py
    - backend/app/llm/client.py
    - backend/app/routes/chat.py
    - backend/tests/llm/__init__.py
    - backend/tests/llm/test_client.py
    - backend/tests/llm/test_mock.py
    - backend/tests/routes/test_chat.py
  modified:
    - backend/app/main.py

key-decisions:
  - "LLM_MOCK resolved fresh inside the request handler (_is_mock_mode()), not at router-construction time, so a single test can flip it via monkeypatch.setenv() against the shared client fixture"
  - "Every AI-initiated trade calls execute_trade() then record_portfolio_snapshot() directly — no shared helper extracted, mirroring the manual trade route's own two-line sequence rather than touching the money-path files Phases 2/3 froze"
  - "chat_completion() never raises: both the SDK call and the content-extraction+validation step sit inside their own exception guards, so an empty choices list returns None instead of an IndexError reaching the route as a 500"
  - "ActionResult is one flat model (kind/status/ticker + optional side/action/quantity/price/error) rather than a discriminated union, per 04-CONTEXT.md's discretion grant — a single frontend card component can render it without a runtime type switch"
  - "result.watchlist_changes is read by the mock and the real client but deliberately left unexecuted this plan — an explicit scope boundary comment names Plan 04-03 as its owner rather than silently omitting coverage"

patterns-established:
  - "Pattern: env-var-gated behavior that must vary per-test reads the env var inside the request handler, not at app/router construction time (LLM_MOCK is the second instance of this after MASSIVE_API_KEY's counter-example)"
  - "Pattern: a function whose docstring says 'never raises' proves it with two nested exception guards — one around the network call, one around extraction+validation — rather than one broad try/except that could mask which stage failed in logs"

requirements-completed: [CHAT-03, CHAT-05, CHAT-06, CHAT-07, TEST-02]

coverage:
  - id: D1
    description: "POST /api/chat returns one complete JSON body ({message, actions[]}) — no streaming, no partial response, and a mock-triggered buy fills through the exact execute_trade() the trade bar calls"
    requirement: CHAT-03
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_mock_triggered_buy_returns_200_with_one_success_action"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_mock_triggered_buy_debits_cash_exactly_like_a_manual_trade"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_manual_trade_of_same_size_produces_the_same_arithmetic"
        status: pass
    human_judgment: false
  - id: D2
    description: "An AI-initiated trade records a portfolio value snapshot immediately, exactly as a manual trade does"
    requirement: CHAT-03
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_mock_triggered_buy_increases_snapshot_count_by_exactly_one"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every rejection mode (insufficient cash, invalid ticker shape, a bad action beside a good one) returns HTTP 200 with a per-action error, never a 500 or a whole-request 4xx"
    requirement: CHAT-06
    verification:
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_mock_triggered_buy_far_beyond_cash_returns_200_with_error_action"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_mock_triggered_buy_and_sell_returns_one_success_and_one_error"
        status: pass
      - kind: integration
        ref: "backend/tests/routes/test_chat.py#test_mock_triggered_trade_on_shape_invalid_ticker_returns_200_with_error"
        status: pass
    human_judgment: false
  - id: D4
    description: "LLM_MOCK=true is deterministic and provably never reaches litellm; the real client returns the same ChatCompletionResult shape and never raises, including when the SDK call fails or the response is empty/malformed"
    requirement: CHAT-07
    verification:
      - kind: unit
        ref: "backend/tests/llm/test_mock.py#test_identical_input_produces_equal_results"
        status: pass
      - kind: integration
        ref: "backend/tests/llm/test_mock.py#test_mock_mode_never_reaches_a_sabotaged_real_client"
        status: pass
      - kind: integration
        ref: "backend/tests/llm/test_mock.py#test_mock_mode_off_with_real_client_returning_none_yields_graceful_fallback"
        status: pass
    human_judgment: false
  - id: D5
    description: "Structured-output parsing is covered for valid, defaulted, non-JSON, schema-violating, raising, and empty-choices responses, and the outgoing call carries the model/format/effort/provider-ordering contract"
    requirement: TEST-02
    verification:
      - kind: unit
        ref: "backend/tests/llm/test_client.py (6 behaviour tests + 1 call-shape test)"
        status: pass
    human_judgment: false

duration: ~15min
completed: 2026-08-04
status: complete
---

# Phase 4 Plan 1: AI-Driven Trade Tracer Summary

**A structured LLM reply — mock first, real LiteLLM/OpenRouter/Cerebras client second — becomes a second validated caller of `execute_trade()`, with every failure mode (engine rejection, invalid ticker, malformed model output, a dead SDK call) collapsing to a 200 with a readable per-action explanation.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2/2 completed
- **Files modified:** 10 (9 created, 1 modified)

## Accomplishments
- `POST /api/chat` end-to-end: free text in, one complete `{message, actions[]}` JSON body out, backed by the exact `execute_trade()` the trade bar calls and an immediate `record_portfolio_snapshot()` on every fill
- `app/llm/mock.py`: deterministic, keyword-triggered, network-free stand-in that still round-trips through the real `ChatCompletionResult` schema and drives real trades
- `app/llm/client.py`: the real LiteLLM/OpenRouter/Cerebras call, wrapped so every failure mode — network, auth, non-JSON output, schema-violating output, an empty `choices` list — returns `None` instead of raising
- Per-action executor that never lets one bad action (a rejected trade, a shape-invalid ticker) fail the other actions in the same reply or turn into a whole-request error
- 36 new tests across `tests/routes/test_chat.py`, `tests/llm/test_client.py`, and `tests/llm/test_mock.py`; full backend suite (168 tests) green

## Task Commits

1. **Task 1: One AI-driven trade, end to end — free text in, a filled order and a confirmation out** - `d7bef67` (feat)
2. **Task 2: The real model behind the same seam — a client that cannot raise, and the parsing suite that proves it** - `cdda15b` (feat)

_Both tasks were `tdd="true"`; each commit is the test-then-implementation pair landed together after the tests were written first and observed failing (404 for Task 1, `ModuleNotFoundError` for Task 2)._

## Files Created/Modified
- `backend/app/llm/__init__.py` - package docstring establishing the "one module, both callers share a return type" contract
- `backend/app/llm/schemas.py` - `Trade`, `WatchlistChange`, `ChatCompletionResult` — the wire contract from `planning/PLAN.md` §9, reproduced exactly
- `backend/app/llm/mock.py` - `mock_chat_completion()` — pure, keyword-triggered, no network, no `litellm` import
- `backend/app/llm/client.py` - `MODEL`, `EXTRA_BODY`, `chat_completion()` — the real call, never raises
- `backend/app/routes/chat.py` - `create_chat_router()`, `ChatRequest`/`ActionResult`/`ChatResponse`, `_is_mock_mode()`, `_get_llm_response()`, `_execute_trade_action()`
- `backend/app/main.py` - mounts `create_chat_router()` alongside the existing three routers
- `backend/tests/routes/test_chat.py` - 11 integration tests: success, insufficient-cash rejection, partial success, invalid-ticker rejection, no-action case, determinism, and request-body validation
- `backend/tests/llm/test_client.py` - 7 tests: valid/defaulted/non-JSON/schema-violating/raising/empty-choices parsing, plus the outgoing-call-shape assertion
- `backend/tests/llm/test_mock.py` - 7 tests: mock determinism/parsing, the sabotaged-real-client proof, and the mock-off graceful-fallback proof

## Decisions Made
- `LLM_MOCK` is read inside the request handler on every call (`_is_mock_mode()`), not resolved once at app-construction time like `create_market_data_source()` — this is what lets `monkeypatch.setenv("LLM_MOCK", ...)` work per-test against the shared `client` fixture without rebuilding the app
- No shared trade-executor helper was extracted between `app/routes/chat.py` and `app/routes/portfolio.py` — the chat route mirrors the manual route's two-line post-fill sequence (`execute_trade()` then a logged-and-continued `record_portfolio_snapshot()`) directly, keeping Phase 2/3's frozen money-path files untouched
- `chat_completion()`'s "never raises" claim is enforced with two separate exception guards (one around the SDK call, one around content extraction + `model_validate_json()`) rather than one broad `try/except`, so an empty `choices` list is caught explicitly instead of relying on a wide catch to happen to cover it
- `result.watchlist_changes` is parsed by both the mock and the real client (proving the mock is a complete reference implementation of the schema) but is not executed in this plan — a one-line comment in the route names Plan 04-03 as its owner

## Deviations from Plan

None — plan executed exactly as written. Both tasks' automated `<verify>` blocks and every acceptance criterion pass as specified; `backend/app/db/portfolio.py` and `backend/app/routes/portfolio.py` are byte-identical to their pre-task state (confirmed via `git diff --stat`).

## Issues Encountered

None. The plan's `<read_first>` guidance and the interface contracts documented in the plan (`execute_trade()`'s signature, `record_portfolio_snapshot()`, `normalize_ticker()`, the cerebras skill's call shape) matched the actual source exactly on first read — no rework was needed.

## User Setup Required

None - no external service configuration required this plan. `OPENROUTER_API_KEY` resolving empty in this sandbox is expected (per `04-CONTEXT.md`'s documented spike finding) and does not block any automated test — every test exercises the code path via `LLM_MOCK=true` or by monkeypatching `app.llm.client.completion`/`app.routes.chat.chat_completion` directly. Live-key verification of the real Cerebras call remains deferred to human verification, as already recorded in `04-CONTEXT.md`'s Deferred Ideas.

## Next Phase Readiness

- The `{message, actions[]}` wire contract this plan establishes is stable and ready for Plan 04-02 (conversation grounding — portfolio context, chat history persistence) and Plan 04-03 (watchlist action execution, which only needs to fill in the already-parsed `result.watchlist_changes` loop this plan left as an explicit scope boundary)
- `app/llm/client.py` and `app/llm/mock.py` are both complete and interchangeable behind `_get_llm_response()` — Plan 04-02's context-builder work does not need to touch either
- No blockers. The one open item — whether the live Cerebras-served model actually honors the schema under a real key — remains a human-verification concern outside this sandbox, unchanged from `04-CONTEXT.md`'s posture

---
*Phase: 04-ai-copilot*
*Completed: 2026-08-04*

## Self-Check: PASSED

All 9 created files confirmed present on disk; both task commits (`d7bef67`, `cdda15b`) confirmed in `git log`.
