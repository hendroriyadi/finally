# Phase 4: AI Copilot - Context

**Gathered:** 2026-08-04
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run — grey areas resolved directly from PLAN.md/REQUIREMENTS.md/codebase state rather than interactive discussion, per explicit user direction to build the full project without interactive check-ins)

<domain>
## Phase Boundary

This phase delivers the AI copilot: a docked chat panel where the user converses with an LLM that is
grounded in their real portfolio state and can execute trades and watchlist changes on their behalf,
through the exact same validated paths (`execute_trade()`, `add_watchlist_ticker()`/
`remove_watchlist_ticker()`) the manual UI already uses. It introduces the project's only LLM
integration: LiteLLM → OpenRouter → Cerebras inference for `openrouter/openai/gpt-oss-120b`, with
structured outputs, plus a deterministic `LLM_MOCK=true` mode for testing.

Out of scope: Docker packaging and the Playwright E2E suite (Phase 5, though `LLM_MOCK` mode built here
is what Phase 5's E2E tests will run against).

</domain>

<decisions>
## Implementation Decisions

### LLM Client Spike (pre-planning validation)
A live spike was run in this session using the exact pattern from the `cerebras-inference` skill
(`.claude/skills/cerebras/SKILL.md`) — `litellm.completion(model="openrouter/openai/gpt-oss-120b",
response_format=SomePydanticModel, reasoning_effort="low", extra_body={"provider": {"order":
["cerebras"]}})`. **Finding:** the request was constructed correctly and reached OpenRouter — LiteLLM
raised no client-side validation error, and OpenRouter's own API returned a normal HTTP 401 JSON error
body (`{"error":{"message":"No cookie auth credentials found","code":401}}`), confirming the
model name, structured-output request shape, and Cerebras provider-ordering `extra_body` are all
accepted by the API. The 401 itself is because `OPENROUTER_API_KEY` resolves to an **empty string** in
this sandboxed session (the `.env` file's key line exists but its value is redacted/stripped by the
execution sandbox — confirmed by direct inspection: `OPENROUTER_API_KEY=` with zero-length value, not a
missing line). This is a sandbox security boundary, not a project misconfiguration; the real key exists
in the user's actual `.env` outside this sandbox. **Conclusion:** the code pattern is validated
end-to-end short of authentication; live-key verification (does a real call return a valid structured
JSON body, does Cerebras actually serve `gpt-oss-120b`, what does `reasoning_effort="low"` cost in
latency) is deferred to human verification alongside this project's other live-only checks (browser
UI), not because the mechanism is unproven, but because this sandbox cannot supply a working key.
`LLM_MOCK=true` is therefore load-bearing for this phase's own automated test suite, not just a nicety.

### Backend: `app/llm/` module (new)
- New package `backend/app/llm/` — a `client.py` wrapping the exact `cerebras-inference` skill pattern
  (model constant, `EXTRA_BODY`, a `chat_completion(messages, response_format) -> BaseModel` helper),
  and a `mock.py` providing `LLM_MOCK=true`'s deterministic responses. `app/routes/chat.py` calls one or
  the other based on the `LLM_MOCK` env var, never both, and the route/service layer above it does not
  know which one ran — same shape as Phase 1's real-simulator-vs-Massive-client split
  (`create_market_data_source`).
- Structured output schema (from `planning/PLAN.md` §9, authoritative — reproduce exactly):
  ```json
  {"message": "...", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}], "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]}
  ```
  Modeled as three Pydantic classes (`Trade`, `WatchlistChange`, `ChatCompletionResult`), `trades`/
  `watchlist_changes` both optional (default `[]`), matching the spike's validated shape.

### Backend: `POST /api/chat` route (new)
- New router `backend/app/routes/chat.py`, mounted in `create_app()` alongside the existing three
  routers.
- Per-turn flow (PLAN.md §9, `<how_it_works>`): load portfolio context
  (`get_portfolio_state()`+`value_portfolio()`, the same pair Phase 3's snapshot writer calls — no
  third valuation path), load the watchlist with live prices, load recent `chat_messages` history
  (Claude's discretion: last 10 turns — enough for follow-up-question continuity per CHAT-02 without
  an unbounded prompt), build the system + context + history + user-message prompt, call the LLM
  client (real or mock), auto-execute any `trades`/`watchlist_changes` the response specifies, persist
  the user message and the assistant's reply (+ executed actions as JSON) to `chat_messages`, return
  the full structured response.
- **CHAT-03 reuse contract (locked, not Claude's discretion):** every AI-initiated trade calls
  `app.db.portfolio.execute_trade()` directly — the exact function `POST /api/portfolio/trade` calls.
  No parallel trade path is written. `execute_trade()`'s docstring already names itself "the documented
  CHAT-03 entry point Phase 4's AI copilot calls directly" (confirmed by reading
  `backend/app/db/portfolio.py` — this phase does not modify that function).
- **CHAT-04 reuse contract:** watchlist changes call `add_watchlist_ticker()`/`remove_watchlist_ticker()`
  directly (`backend/app/db/watchlist.py`), through `normalize_ticker()` first (from
  `app/routes/watchlist.py`) so an LLM-supplied ticker string gets the identical shape validation a
  manual `POST /api/watchlist` body gets.
- **CHAT-06 (graceful failure):** each trade/watchlist action from the model is executed inside its own
  try/except; a rejection (`InsufficientCashError`, `InsufficientSharesError`, `NoPriceAvailableError`,
  `WatchlistCapReachedError`, a normalize failure, etc.) is caught, turned into a short human-readable
  string, and included in the response's action-result list — never raised as a 500 and never left to
  silently fail. The chat response's `message` field is the LLM's own prose; a per-action `status`/
  `error` field (Claude's discretion on exact shape) is what the frontend uses to render inline
  confirmations (CHAT-05) versus inline failures.
- A malformed/unparseable model response (structured-output parsing failure) is caught at the
  `chat_completion()` boundary and turned into a single graceful assistant-role message ("I had trouble
  processing that — could you rephrase?" or similar), stored and returned with an empty `trades`/
  `watchlist_changes` list — never a 500, per CHAT-06's "unparseable model output" clause.

### Database: `chat_messages` (existing schema, first writer)
- Table already exists (Phase 1's `schema.sql`, unwritten until now) — `id, user_id, role, content,
  actions, created_at`, `role` constrained to `('user','assistant')`, `actions` nullable TEXT (JSON).
  This phase is its first reader/writer, mirroring Phase 3's relationship to `portfolio_snapshots`.
- New module `backend/app/db/chat.py` (Claude's discretion on exact name, following the `db/snapshots.py`
  precedent from Phase 3): `append_chat_message()`, `list_recent_chat_messages()`. Writes exactly this
  one table — same "one module, one table, no drift" discipline `snapshots.py` established.

### Frontend: Chat panel (new)
- PLAN.md §10 calls it "docked/collapsible sidebar." Claude's discretion on exact layout mechanics
  (fixed-width sidebar column vs. a slide-over), but it must be dockable alongside the existing
  two-column grid Phase 3 established, not replace or cover it, and collapsible (UI-04).
- Message input, scrolling transcript, loading indicator while awaiting a reply (no token streaming —
  PLAN.md §9 is explicit LiteLLM/Cerebras inference is fast enough that a single loading state
  suffices, matching this phase's `POST /api/chat` returning one complete JSON body, not SSE).
- Trade/watchlist actions execute automatically (no confirmation dialog, deliberate per PLAN.md §9) —
  shown inline in the transcript as confirmations (CHAT-05) immediately after the assistant's reply
  renders, using the per-action status the backend returns.
- **Conversation persists across a page refresh (CHAT-01):** the panel loads recent `chat_messages` on
  mount via a `GET` path (Claude's discretion: reuse the same recent-history query the chat route's
  context-building uses, exposed as its own endpoint, e.g. `GET /api/chat/history` — PLAN.md's endpoint
  table only lists `POST /api/chat`, so adding a read-only history endpoint is the phase's own
  discretion call, justified by CHAT-01's explicit "survives a page refresh" requirement having no
  other mechanism to satisfy it without one).
- New `ChatProvider`/`useChatContext` (Claude's discretion on whether this needs a context at all —
  likely component-local state suffices, since the chat panel is a single component tree with no
  sibling needing chat state, unlike `PortfolioProvider`/`PriceStreamProvider` which have multiple
  independent consumers spanning `layout.tsx`/`page.tsx`).

### `LLM_MOCK=true` (existing env var, first consumer)
- `backend/app/llm/mock.py` returns deterministic responses so Phase 5's Playwright suite (explicitly
  planned to run with `LLM_MOCK=true`) and this phase's own backend tests never depend on network
  access or a real API key. Claude's discretion on exact mock response content/triggers (e.g. keyword-
  matching the user's message to decide whether to include a mock trade), but every mock response must
  still round-trip through the exact same `ChatCompletionResult` Pydantic shape the real client
  produces, and mock-triggered trades/watchlist-changes must still go through the real
  `execute_trade()`/`add_watchlist_ticker()` functions — only the LLM call itself is faked, not the
  auto-execution path TEST-02/CHAT-07 need to exercise.

### Claude's Discretion
- Exact prompt/system-message wording (must follow PLAN.md §9's guidance: "FinAlly, an AI trading
  assistant," analyze composition/risk/P&L, suggest and execute trades, manage watchlist proactively,
  concise and data-driven, always valid structured JSON).
- How many recent `chat_messages` turns to include as context (recommend ~10).
- Exact shape of the per-action result Claude prompt outcome/error `Claude's discretion.
- Chat panel exact layout (sidebar vs. slide-over), collapse mechanism, and whether a context or local
  state carries its data.
- `GET /api/chat/history` route existing at all vs. folding history into `POST /api/chat`'s first call
  — pick whichever makes CHAT-01's "survives a page refresh" cleanest.
- Mock response design in `app/llm/mock.py`.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/db/portfolio.py` — `execute_trade()` (CHAT-03 entry point, already documented as such in
  its own docstring), `get_portfolio_state()`, `value_portfolio()` — this phase's context-builder and
  trade-executor both call these, reimplementing nothing.
- `backend/app/db/watchlist.py` — `add_watchlist_ticker()`, `remove_watchlist_ticker()`,
  `list_watchlist()`, `WatchlistCapReachedError`.
- `backend/app/routes/watchlist.py` — `normalize_ticker()`, `TICKER_PATTERN` — the LLM's raw ticker
  strings go through this before touching any watchlist function, same as a manual request.
- `backend/app/db/connection.py` — `run_db()`, `DEFAULT_USER_ID` — same seam every DB write uses.
- `backend/app/db/snapshots.py` — the closest precedent for this phase's new `chat.py` module: "one
  module, one table, reuses existing read/mutate functions, writes nothing else."
- `.claude/skills/cerebras/SKILL.md` — the authoritative, validated (this session) LiteLLM/OpenRouter/
  Cerebras call pattern, including the structured-output variant.
- `frontend/components/PortfolioProvider.tsx`, `PriceStreamProvider.tsx` — the two existing
  provider-in-`layout.tsx` precedents, and the `.then()`-chain fetch-effect idiom (not an awaited async
  function) that satisfies `eslint-config-next` 16's `react-hooks/set-state-in-effect` rule — the chat
  panel's message-send flow needs the same idiom.
- `frontend/components/TradeBar.tsx`, `AddTickerForm.tsx`, `RemoveTickerButton.tsx` — the existing
  non-optimistic-mutation, in-flight-disable, error-surfacing pattern this phase's message-send button
  should match (send button disabled while awaiting a reply, no optimistic assistant message rendered
  before the real one arrives).

### Established Patterns
- `from __future__ import annotations`, full type hints, `snake_case`/`PascalCase`, module-level
  `logger`, prose docstrings, `asyncio.to_thread()` via `run_db()` for all blocking I/O.
- Exception-per-failure-mode (`TradeRejectedError` subclasses) caught at the route layer and turned into
  either an HTTP error (manual trade route) or, this phase, an inline chat action-result (never a raw
  500 either way).
- `"use client"` on every component using hooks/browser APIs; static-export-safe (no SSR-only
  assumptions).

### Integration Points
- New `create_chat_router()` mounts on `create_app()` alongside `create_portfolio_router()`,
  `create_watchlist_router()`.
- `backend/pyproject.toml` gains `litellm` and `pydantic` as new dependencies (already added and
  installed this session: `litellm>=1.95.0`, `pydantic>=2.12.5` — `pydantic` was not previously a
  direct dependency, though FastAPI pulls it transitively; this phase makes it explicit since
  `app/llm/`'s response models import it directly).
- Frontend: new `ChatPanel` (or similarly named) component renders in `app/layout.tsx` (a page-spanning
  dock, consistent with `AppHeader`) or `app/page.tsx` (if scoped to the main dashboard only) —
  Claude's discretion, guided by "docked... sidebar" reading most naturally as layout-level.

</code_context>

<specifics>
## Specific Ideas

- CHAT-02's "receives current portfolio context... on each turn" must be re-fetched fresh every
  `POST /api/chat` call, not cached from a prior turn — prices and positions can change between
  messages in the same conversation.
- The zero-confirmation auto-execution design (PLAN.md §9, "Auto-Execution") is deliberate and must not
  be second-guessed with an added confirmation step — the mitigation is transparency (CHAT-05's inline
  confirmation), not friction.
- `reasoning_effort="low"` is part of the validated skill pattern — keep it; it's what the "fast enough
  for a single loading state, no token streaming" design assumption (PLAN.md §9) depends on.

</specifics>

<deferred>
## Deferred Ideas

- Live, real-API-key verification of the Cerebras structured-output path's actual model behavior
  (response quality, latency, whether `gpt-oss-120b` via Cerebras genuinely honors the schema on every
  call rather than just this session's one successfully-routed-but-401'd request) — deferred to human
  verification, same posture as this project's deferred live-browser checks for Phases 1-3. Recorded as
  a blocker/concern in STATE.md.
- Docker packaging, Playwright E2E — Phase 5.

</deferred>
