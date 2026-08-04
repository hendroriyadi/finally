# Phase 4: AI Copilot - Research

**Researched:** 2026-08-04
**Domain:** LLM structured-output tool-calling (LiteLLM/OpenRouter/Cerebras), FastAPI service composition, React chat UI over a non-streaming JSON endpoint
**Confidence:** HIGH (backend integration points — all read directly from source this session) / MEDIUM (LLM provider runtime behavior — validated mechanically, not with a live key)

## Summary

Phase 4 adds exactly one new backend integration point (`litellm.completion()` → OpenRouter → Cerebras,
already spike-validated this session per `04-CONTEXT.md`) and wires it into the project's existing
"one module, one table, reuse don't reimplement" discipline. The critical engineering risk in this phase
is not the LLM call itself — that pattern is fixed by `.claude/skills/cerebras/SKILL.md` and is not
Claude's discretion — it is making sure the AI's trade and watchlist actions produce **exactly** the same
side effects a manual action produces. Reading the existing manual routes (`app/routes/portfolio.py`,
`app/routes/watchlist.py`) surfaced two side effects `04-CONTEXT.md`'s reuse-contract language does not
explicitly mention but that Phase 4's own success criteria require: every trade must also trigger
`record_portfolio_snapshot()` (so the P&L chart updates immediately, not up to 30s later), and every
watchlist add/remove must also call `request.app.state.market_source.add_ticker()`/`remove_ticker()`
(so a newly-added ticker actually starts streaming a price instead of sitting in the DB with no price
feed). Both are documented below as concrete, non-optional implementation requirements, not options.

The rest of the phase is comparatively low-risk: a new `chat_messages` table already exists unwritten,
`litellm`/`pydantic` are already installed and version-confirmed in this sandbox, and the frontend chat
panel reuses the exact `.then()`-chain fetch idiom and non-optimistic mutation pattern three prior phases
already established. No new test framework is needed — `pytest` already covers this project's entire
backend test surface, and this phase's only test requirement (TEST-02) is a backend-only requirement;
UI-04 is validated manually since frontend component testing (TEST-03) is explicitly Phase 5's scope.

**Primary recommendation:** Build `app/llm/client.py` (real, blocking `litellm.completion()` wrapped in
`asyncio.to_thread()`) and `app/llm/mock.py` (deterministic, keyword-triggered) behind one small
`_get_llm_response()` dispatcher in `app/routes/chat.py` that reads `LLM_MOCK` **per-request**, not at
app-startup like `create_market_data_source()` does — this is what lets tests flip mock mode per-test via
`monkeypatch.setenv()` against the existing shared `client` fixture without touching `create_app()`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| LLM invocation (LiteLLM → OpenRouter → Cerebras) | API / Backend | External service (OpenRouter) | Server-side only — the API key never reaches the browser; `app/llm/client.py` is the sole caller |
| Portfolio/watchlist context construction | API / Backend | Database / Storage | Reuses `get_portfolio_state()`/`value_portfolio()`/`list_watchlist()` — the same read path Phase 2/3 routes use, not a new read |
| Structured-output schema validation | API / Backend | — | Pydantic `model_validate_json()` runs server-side; the frontend never parses raw LLM output |
| Trade / watchlist auto-execution | API / Backend | Database / Storage | Calls the exact same `execute_trade()`/`add_watchlist_ticker()`/`remove_watchlist_ticker()` the manual routes call — no new mutation path |
| Chat message persistence | Database / Storage | API / Backend | `chat_messages` table (schema already exists); `app/db/chat.py` is the sole reader/writer, mirroring `app/db/snapshots.py`'s relationship to `portfolio_snapshots` |
| `LLM_MOCK` deterministic responses | API / Backend | — | Backend-side substitution for the real LLM call; the frontend/route layer above it is unaware which ran |
| Chat panel UI (input, transcript, loading, collapse) | Browser / Client | — | Component-local `useState`, no new context (per `04-CONTEXT.md`/UI-SPEC — a single component subtree, no sibling consumer) |

## User Constraints (from CONTEXT.md)

<user_constraints>

### Locked Decisions

- **LLM client pattern is fixed, not exploratory.** The live spike this session confirmed
  `litellm.completion(model="openrouter/openai/gpt-oss-120b", response_format=SomePydanticModel,
  reasoning_effort="low", extra_body={"provider": {"order": ["cerebras"]}})` is mechanically correct
  end-to-end short of authentication (a 401 came back from OpenRouter itself, not a client-side
  validation error). `OPENROUTER_API_KEY` resolves to an empty string in this sandbox (a sandbox
  boundary, not a project misconfiguration). Do not re-run the spike; trust and build on this finding.
  `LLM_MOCK=true` is load-bearing for this phase's automated test suite.
- **New `app/llm/` package**: `client.py` (real client — model constant, `EXTRA_BODY`, a
  `chat_completion(messages, response_format) -> BaseModel` helper) and `mock.py` (`LLM_MOCK=true`
  deterministic responses). `app/routes/chat.py` calls one or the other based on the `LLM_MOCK` env var,
  never both — same shape as `create_market_data_source()`'s simulator-vs-Massive split.
- **Structured output schema** (from `planning/PLAN.md` §9, authoritative, reproduce exactly):
  `{"message": "...", "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
  "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]}` — three Pydantic classes (`Trade`,
  `WatchlistChange`, `ChatCompletionResult`), `trades`/`watchlist_changes` both optional, default `[]`.
- **New router** `backend/app/routes/chat.py`, mounted in `create_app()` alongside the existing three
  routers.
- **Per-turn flow**: load portfolio context (`get_portfolio_state()`+`value_portfolio()` — the same pair
  Phase 3's snapshot writer calls, no third valuation path), load the watchlist with live prices, load
  recent `chat_messages` history (Claude's discretion: ~10 turns), build system+context+history+user
  prompt, call the LLM client (real or mock), auto-execute any `trades`/`watchlist_changes`, persist the
  user message and the assistant's reply (+ executed actions as JSON) to `chat_messages`, return the full
  structured response.
- **CHAT-03 reuse contract (locked, not discretion)**: every AI-initiated trade calls
  `app.db.portfolio.execute_trade()` directly — the exact function `POST /api/portfolio/trade` calls. No
  parallel trade path. `execute_trade()`'s own docstring already names itself "the documented CHAT-03
  entry point Phase 4's AI copilot calls directly" — this phase does not modify that function.
- **CHAT-04 reuse contract**: watchlist changes call `add_watchlist_ticker()`/`remove_watchlist_ticker()`
  directly, through `normalize_ticker()` first (from `app/routes/watchlist.py`) so an LLM-supplied ticker
  string gets identical shape validation to a manual `POST /api/watchlist` body.
- **CHAT-06 (graceful failure)**: each trade/watchlist action executes inside its own try/except; a
  rejection (`InsufficientCashError`, `InsufficientSharesError`, `NoPriceAvailableError`,
  `WatchlistCapReachedError`, a normalize failure, etc.) is caught, turned into a short human-readable
  string, included in the response's per-action result list — never a raw 500, never silently dropped. A
  malformed/unparseable model response is caught at the `chat_completion()` boundary and turned into a
  single graceful assistant-role message, stored and returned with empty `trades`/`watchlist_changes` —
  never a 500.
- **Database**: `chat_messages` table already exists (Phase 1's `schema.sql`, unwritten until now). New
  module `backend/app/db/chat.py` (`append_chat_message()`, `list_recent_chat_messages()`) — writes
  exactly this one table, mirroring `db/snapshots.py`'s discipline.
- **Frontend**: docked/collapsible chat panel (layout mechanics = Claude's discretion, resolved in
  UI-SPEC as a 384px right-docked sidebar with a 56px collapsed rail). Message input, scrolling
  transcript, loading indicator, no token streaming (`POST /api/chat` returns one complete JSON body).
  Trade/watchlist actions execute automatically, shown inline as confirmations (CHAT-05) immediately
  after the assistant's reply renders.
- **CHAT-01 persistence**: the panel loads recent `chat_messages` on mount via a `GET` path (resolved:
  `GET /api/chat/history`, reusing the same recent-history query the chat route's context-building uses).
- **No new chat context/provider**: component-local state suffices (single component subtree, no sibling
  consumer), unlike `PortfolioProvider`/`PriceStreamProvider`.
- **`LLM_MOCK=true`**: `backend/app/llm/mock.py` returns deterministic responses so Phase 5's Playwright
  suite and this phase's own backend tests never depend on network access or a real key. Mock responses
  must still round-trip through the exact same `ChatCompletionResult` Pydantic shape the real client
  produces, and mock-triggered trades/watchlist-changes must still go through the real
  `execute_trade()`/`add_watchlist_ticker()` functions — only the LLM call itself is faked.
- **CHAT-02 freshness**: portfolio context is re-fetched fresh every `POST /api/chat` call, never cached
  from a prior turn.
- **Zero-confirmation auto-execution is deliberate** (PLAN.md §9) — must not be second-guessed with an
  added confirmation step. The mitigation is transparency (CHAT-05's inline confirmation), not friction.
- **`reasoning_effort="low"`** is part of the validated skill pattern — keep it.

### Claude's Discretion

- Exact prompt/system-message wording (must follow PLAN.md §9's guidance: "FinAlly, an AI trading
  assistant," analyze composition/risk/P&L, suggest and execute trades, manage watchlist proactively,
  concise and data-driven, always valid structured JSON).
- How many recent `chat_messages` to include as context (recommend ~10 turns).
- Exact shape of the per-action result (status/error field).
- Chat panel exact layout (sidebar vs. slide-over), collapse mechanism, context-vs-local-state choice —
  all resolved by `04-UI-SPEC.md` (already approved): 384px right-docked sidebar, component-local state.
- `GET /api/chat/history` existing at all vs. folding into `POST /api/chat`'s first call — resolved:
  build the dedicated `GET /api/chat/history` endpoint.
- Mock response design in `app/llm/mock.py`.

### Deferred Ideas (OUT OF SCOPE)

- Live, real-API-key verification of the Cerebras structured-output path's actual model behavior
  (response quality, latency, schema adherence on every call) — deferred to human verification, same
  posture as this project's deferred live-browser checks for Phases 1-3. Recorded as a blocker/concern in
  STATE.md.
- Docker packaging, Playwright E2E — Phase 5.

</user_constraints>

## Phase Requirements

<phase_requirements>

| ID | Description | Research Support |
|----|-------------|------------------|
| CHAT-01 | Send a chat message, receive a complete structured JSON response; conversation survives a page refresh | `POST /api/chat` (non-streaming, single JSON body) + `GET /api/chat/history` (backed by `app/db/chat.py`'s shared `list_recent_chat_messages()`) — see Code Examples |
| CHAT-02 | AI receives current portfolio context + recent history on every turn | Context builder re-fetches `get_portfolio_state()`/`value_portfolio()`/`list_watchlist()` fresh per request, never cached — see Architecture Patterns |
| CHAT-03 | AI trades route through the exact same validated `execute_trade()` | `_execute_trade_action()` calls `app.db.portfolio.execute_trade()` directly, **plus** `record_portfolio_snapshot()` (new finding — see Common Pitfalls #3) |
| CHAT-04 | AI can add/remove watchlist tickers | `_execute_watchlist_action()` calls `add_watchlist_ticker()`/`remove_watchlist_ticker()`, **plus** `request.app.state.market_source.add_ticker()`/`remove_ticker()` (new finding — see Common Pitfalls #2) |
| CHAT-05 | AI trade/watchlist actions shown inline as confirmations | `ChatResponse.actions: list[ActionResult]` carries per-action `status`/human-readable fields the frontend renders as confirmation cards (UI-SPEC's already-approved copy contract) |
| CHAT-06 | Failed AI actions surface a graceful explanation, never crash the request | Per-action try/except around each `execute_trade()`/`add_watchlist_ticker()`/`remove_watchlist_ticker()` call; `chat_completion()` boundary never raises, returns `None` on any failure mode |
| CHAT-07 | Deterministic `LLM_MOCK=true` mode | `app/llm/mock.py`'s pure, keyword-triggered `mock_chat_completion()` — never imports/calls `litellm` |
| UI-04 | Docked/collapsible chat panel, input, scrolling history, loading indicator | Fully specified in `04-UI-SPEC.md` (approved) — see Architecture Patterns' frontend section |
| TEST-02 | Backend unit tests cover LLM structured-output parsing incl. malformed/invalid responses | `tests/llm/test_client.py` — see Validation Architecture |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `litellm` | 1.95.0 (installed, confirmed via `importlib.metadata.version()` this session) `[VERIFIED: backend/pyproject.toml:13, importlib.metadata]` | Unified LLM client — routes `completion()` to OpenRouter with Cerebras as the inference provider | Already the project's chosen LLM SDK (`.claude/skills/cerebras/SKILL.md`); handles provider-specific structured-output schema translation so this phase never hand-rolls a JSON-mode prompt |
| `pydantic` | 2.12.5 (installed, confirmed via `importlib.metadata.version()` this session) `[VERIFIED: backend/pyproject.toml:14, importlib.metadata]` | Structured-output schema (`Trade`, `WatchlistChange`, `ChatCompletionResult`) + request/response models | Already a transitive FastAPI dependency, now an explicit one since `app/llm/` imports it directly; `response_format=SomeBaseModel` is litellm's native structured-output mechanism |

No other new backend dependencies. No new frontend dependencies (`lucide-react` already present; UI-SPEC confirms zero new npm packages this phase).

### Supporting

None beyond what's already installed — this phase adds zero new packages beyond `litellm`/`pydantic`, both already added to `backend/pyproject.toml` and installed this session per `04-CONTEXT.md`.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `litellm.completion()` (sync, wrapped in `asyncio.to_thread()`) | `litellm.acompletion()` (native async) | `SKILL.md` (the authoritative, already-validated pattern for this project) only demonstrates the sync `completion()` call — deviating to `acompletion()` would mean re-validating a pattern the spike didn't test. Wrapping the sync call in `asyncio.to_thread()` gets the same non-blocking behavior while staying inside the validated shape, and mirrors `run_db()`'s own established `asyncio.to_thread()` seam for blocking I/O |
| A dedicated chat React context (`ChatProvider`) | Component-local `useState` | Already resolved in `04-CONTEXT.md`/UI-SPEC: the chat panel is a single component subtree with no sibling consumer, unlike `PortfolioProvider`/`PriceStreamProvider` |
| A new `GET /api/chat` endpoint returning full unbounded history | `GET /api/chat/history` bounded to the same limit as LLM context (~10 turns) | An unbounded history endpoint has no cap analogous to `portfolio_snapshots`' `MAX_HISTORY_POINTS`; reusing the same bounded query CONTEXT.md explicitly suggests avoids a second, uncapped read path |

**Installation:** No new installation needed — `litellm>=1.95.0` and `pydantic>=2.12.5` are already present in `backend/pyproject.toml` and installed in `backend/.venv`. If a fresh checkout needs them: `cd backend && uv sync --extra dev`.

**Version verification:** Verified directly this session via `uv run python -c "import importlib.metadata as m; print(m.version('litellm')); print(m.version('pydantic'))"` → `litellm 1.95.0`, `pydantic 2.12.5`. Both match the floor versions pinned in `backend/pyproject.toml:13-14`.

## Package Legitimacy Audit

| Package | Registry | Age (latest version publish) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-------------------------------|-----------|-------------|---------|-------------|
| `litellm` | PyPI | Recent version publish flagged "too-new" by the legitimacy seam | Unavailable (`weeklyDownloads: null` — seam has no PyPI download-stats source) | `https://litellm.ai` (official BerriAI project — `github.com/BerriAI/litellm`, the same org the project's own `.claude/skills/cerebras/SKILL.md` is built on) | `SUS` (signals: `too-new`, `unknown-downloads`) | **Approved, contextual override** — see note below |
| `pydantic` | PyPI | n/a | Unavailable (`weeklyDownloads: null`) | `github.com/pydantic/pydantic` (official; a mandatory FastAPI dependency already present transitively in every phase of this project) | `SUS` (signal: `unknown-downloads`) | **Approved, contextual override** — see note below |

**Contextual override rationale:** Both `SUS` verdicts stem entirely from the legitimacy seam's inability
to retrieve PyPI download-count data (`unknown-downloads`) — not from any actual suspicious signal
(no missing repo, no deprecation, no postinstall script). `litellm`'s `too-new` flag reflects the publish
date of its *latest released version*, not the age of the project itself (BerriAI/litellm is a
long-established, widely-used OSS project and the explicit named dependency of this project's own
`cerebras-inference` skill). Both packages were already added to `backend/pyproject.toml` and installed
**in a prior session action**, not as a new install this phase, and both were exercised successfully in
this session's live spike (SKILL.md's pattern, which routed a real request to OpenRouter). No
`checkpoint:human-verify` task is recommended before proceeding — this is a documented judgment call, not
a silent override; flag it in the plan if a stricter posture is preferred.

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `litellm`, `pydantic` — both dispositioned "Approved" above with rationale; no planner-inserted checkpoint recommended, but the planner may choose to add one for extra caution given the `SUS` verdict is real (not fabricated) even if the underlying reason is a seam limitation.

## Architecture Patterns

### System Architecture Diagram

```
Browser (ChatPanel)
   │
   │  1. GET /api/chat/history            (on mount)
   │  2. POST /api/chat  { message }      (on send)
   ▼
FastAPI route: app/routes/chat.py
   │
   ├─ list_recent_chat_messages(limit=~10)  ──────► app/db/chat.py ──► chat_messages table
   │      (fetched BEFORE persisting the new user turn — avoids double-counting it)
   │
   ├─ get_portfolio_state() + value_portfolio()  ──► app/db/portfolio.py (Phase 2, unmodified)
   ├─ list_watchlist() + price_cache.get_price()  ─► app/db/watchlist.py + app/market/PriceCache
   │
   ├─ append_chat_message(role="user", ...)  ─────► chat_messages table
   │
   ├─ build system+context+history+user prompt
   │
   ├─ _get_llm_response(messages)
   │     │
   │     ├─ LLM_MOCK=true  ──► app/llm/mock.py::mock_chat_completion()   (pure, no network)
   │     └─ LLM_MOCK=false ──► asyncio.to_thread(app/llm/client.py::chat_completion)
   │                                │
   │                                ▼
   │                         litellm.completion(model="openrouter/openai/gpt-oss-120b",
   │                                             response_format=ChatCompletionResult,
   │                                             reasoning_effort="low",
   │                                             extra_body={"provider":{"order":["cerebras"]}})
   │                                │
   │                                ▼
   │                         OpenRouter ──► Cerebras inference ──► gpt-oss-120b
   │                                │
   │                         returns ChatCompletionResult | None (never raises)
   │
   ├─ None?  ──► fallback graceful message, actions=[]
   │
   └─ result.trades / result.watchlist_changes  ──► per-action executor loop
          │
          ├─ Trade  ──► normalize_ticker() ──► execute_trade() ──► record_portfolio_snapshot()
          │                (app/routes/watchlist.py)  (app/db/portfolio.py, unmodified — CHAT-03 contract)
          │
          └─ WatchlistChange ──► normalize_ticker() ──► add_watchlist_ticker()/remove_watchlist_ticker()
                                                          ──► request.app.state.market_source.add_ticker()/
                                                              remove_ticker()  (CHAT-04 full contract)
   │
   ├─ append_chat_message(role="assistant", content=result.message, actions=[...])
   │
   ▼
ChatResponse { message, actions: [{kind, status, ticker, ..., error?}] }  ──► Browser renders inline confirmations
```

### Recommended Project Structure

```
backend/app/
├── llm/                       # new package
│   ├── __init__.py
│   ├── schemas.py             # Trade, WatchlistChange, ChatCompletionResult (Pydantic)
│   ├── client.py              # MODEL, EXTRA_BODY, chat_completion() — the real LiteLLM/Cerebras call
│   └── mock.py                # mock_chat_completion() — LLM_MOCK=true deterministic responses
├── db/
│   └── chat.py                # new — append_chat_message(), list_recent_chat_messages()
└── routes/
    └── chat.py                # new — create_chat_router(): POST /api/chat, GET /api/chat/history

frontend/
├── components/
│   └── ChatPanel.tsx           # new — owns message list, input, loading, collapse (component-local state)
├── lib/
│   ├── api.ts                  # + sendChatMessage(), fetchChatHistory()
│   └── types.ts                # + ChatRole, ChatActionResult, ChatMessage, ChatResponse
```

### Pattern 1: Blocking LLM call wrapped in `asyncio.to_thread()`, mirroring `run_db()`

**What:** `litellm.completion()` is a synchronous, network-bound call. Calling it directly inside an
`async def` route handler blocks the entire FastAPI event loop for the full round-trip latency — this
would stall the SSE price stream (`/api/stream/prices`) and every other concurrent request while a chat
reply is in flight.

**When to use:** Every real (non-mock) LLM call.

**Example:**
```python
# app/llm/client.py — Source: pattern from backend/app/db/connection.py's run_db() seam,
# applied to the LiteLLM call the same way it's applied to sqlite3.Connection calls.
from __future__ import annotations

import logging

from litellm import completion
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}


def chat_completion(
    messages: list[dict], response_format: type[BaseModel]
) -> BaseModel | None:
    """Blocking call — the caller must run this via asyncio.to_thread().

    Returns a validated `response_format` instance, or None on ANY failure
    (network, auth, rate limit, malformed/unparseable response) — never
    raises, so app/routes/chat.py treats every failure mode identically
    (CHAT-06's graceful-fallback contract).
    """
    try:
        response = completion(
            model=MODEL,
            messages=messages,
            response_format=response_format,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
        )
    except Exception:
        logger.exception("LLM completion call failed")
        return None

    raw = response.choices[0].message.content
    try:
        return response_format.model_validate_json(raw)
    except (ValidationError, TypeError, ValueError):
        logger.exception("LLM response failed schema validation: %r", raw)
        return None
```
```python
# app/routes/chat.py — dispatcher
import asyncio
import os

from app.llm.client import chat_completion
from app.llm.mock import mock_chat_completion
from app.llm.schemas import ChatCompletionResult


def _is_mock_mode() -> bool:
    # Read fresh on every request — deliberately NOT resolved once at
    # app-startup like create_market_data_source() is. This is what lets
    # tests flip LLM_MOCK per-test via monkeypatch.setenv() against the
    # existing shared `client` fixture, with no app-reconstruction needed.
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


async def _get_llm_response(messages: list[dict]) -> ChatCompletionResult | None:
    if _is_mock_mode():
        return mock_chat_completion(messages)
    return await asyncio.to_thread(chat_completion, messages, ChatCompletionResult)
```
`[VERIFIED: .claude/skills/cerebras/SKILL.md:22-42]` — the `completion(...)` call shape, `MODEL`, and
`EXTRA_BODY` constants above are copied verbatim from the skill's own snippets:
```
MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
...
response = completion(model=MODEL, messages=messages, response_format=MyBaseModelSubclass, reasoning_effort="low", extra_body=EXTRA_BODY)
result = response.choices[0].message.content
result_as_object = MyBaseModelSubclass.model_validate_json(result)
```

### Pattern 2: Per-action executor — never let one bad action fail the whole reply

**What:** `ChatCompletionResult.trades`/`.watchlist_changes` are lists — a single reply can request
multiple actions. Each must be executed and reported independently; one rejection must not stop or fail
the others, and must never raise past the route handler (CHAT-06).

**When to use:** Executing every trade/watchlist action the LLM's structured output requests.

**Example:**
```python
# app/routes/chat.py
from fastapi import HTTPException, Request

from app.db.portfolio import (
    InsufficientCashError, InsufficientSharesError, NoPriceAvailableError,
    TradeRejectedError, execute_trade,
)
from app.db.snapshots import record_portfolio_snapshot
from app.db.watchlist import (
    WatchlistCapReachedError, add_watchlist_ticker, remove_watchlist_ticker,
)
from app.llm.schemas import Trade, WatchlistChange
from app.routes.watchlist import MAX_WATCHLIST_SIZE, normalize_ticker


async def _execute_trade_action(trade: Trade, request: Request) -> ActionResult:
    # normalize_ticker() raises HTTPException directly (see Pitfall 1) —
    # it MUST be caught here, not left to propagate past this one action.
    try:
        ticker = normalize_ticker(trade.ticker)
    except HTTPException:
        return ActionResult(
            kind="trade", status="error", ticker=trade.ticker, side=trade.side,
            error=f"Couldn't {trade.side} {trade.ticker} — invalid ticker symbol.",
        )

    try:
        result = await execute_trade(
            ticker, trade.side, trade.quantity, price_cache=request.app.state.price_cache
        )
    except NoPriceAvailableError:
        return ActionResult(kind="trade", status="error", ticker=ticker, side=trade.side,
                             error=f"Couldn't {trade.side} {ticker} — no live price available.")
    except InsufficientCashError:
        return ActionResult(kind="trade", status="error", ticker=ticker, side=trade.side,
                             error=f"Couldn't buy {ticker} — insufficient cash.")
    except InsufficientSharesError:
        return ActionResult(kind="trade", status="error", ticker=ticker, side=trade.side,
                             error=f"Couldn't sell {ticker} — you don't own that many shares.")
    except TradeRejectedError as exc:
        return ActionResult(kind="trade", status="error", ticker=ticker, side=trade.side, error=str(exc))

    # CHAT-03's full contract, per phase success criterion 3 ("...charts all
    # update"): mirror routes/portfolio.py's post-trade snapshot trigger
    # exactly — logged, never raised, so a snapshot failure can't turn an
    # already-filled trade into an error response (see Pitfall 3).
    try:
        await record_portfolio_snapshot(price_cache=request.app.state.price_cache)
    except Exception:
        logger.exception("record_portfolio_snapshot failed after AI-initiated trade on %s", ticker)

    return ActionResult(kind="trade", status="success", ticker=ticker, side=trade.side,
                         quantity=result["quantity"], price=result["price"])
```

### Pattern 3: Fetch-on-mount `.then()` idiom (required by `react-hooks/set-state-in-effect`)

**What:** `eslint-config-next` 16 flags an awaited async function called directly inside `useEffect` as
"setState synchronously within an effect," even though the actual state update happens after a network
round trip. The existing codebase's fix is to wire the fetch via `.then()/.catch()` instead.

**When to use:** `ChatPanel`'s history-fetch-on-mount effect.

**Example:**
```typescript
// Source: frontend/components/WatchlistPanel.tsx:39-63 (existing, established idiom)
useEffect(() => {
  let cancelled = false;

  fetchChatHistory()
    .then((messages) => {
      if (!cancelled) {
        setMessages(messages);
        setHistoryError(false);
      }
    })
    .catch(() => {
      if (!cancelled) {
        setHistoryError(true);
      }
    })
    .finally(() => {
      if (!cancelled) {
        setHistoryLoading(false);
      }
    });

  return () => {
    cancelled = true;
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps -- fetch-on-mount is intentionally run once
}, []);
```

### Anti-Patterns to Avoid

- **A second trade/watchlist mutation path for AI actions:** CHAT-03/CHAT-04 lock this — always call
  `execute_trade()`/`add_watchlist_ticker()`/`remove_watchlist_ticker()`, never a parallel SQL statement.
- **Caching portfolio/watchlist context across turns:** CHAT-02 requires a fresh read every
  `POST /api/chat` call — a stale cache would show the AI a stale cash balance mid-conversation.
- **Calling `litellm.completion()` synchronously inside the async route handler:** blocks the event loop
  and the SSE stream for the LLM round-trip duration (Common Pitfall 5).
- **Resolving `LLM_MOCK` once at app-startup:** unlike `create_market_data_source()` (a deliberate
  once-per-process choice for market data), `LLM_MOCK` must be read per-request (Common Pitfall 4).
- **Letting `normalize_ticker()`'s `HTTPException` propagate out of the per-action executor:** turns one
  bad LLM-suggested ticker into a 400 for the entire chat turn instead of one failed action among others
  (Common Pitfall 1).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Trade execution/validation | A second, LLM-facing trade path | `app.db.portfolio.execute_trade()` | CHAT-03 locked reuse contract; the atomic cash/quantity guards (`cursor.rowcount`-checked `UPDATE`) are already proven correct in Phase 2's test suite — a second implementation would need to re-prove all of Phase 2's race-safety work |
| Watchlist mutation | A second insert/delete path | `app.db.watchlist.add_watchlist_ticker()`/`remove_watchlist_ticker()` | CHAT-04 locked reuse contract; the atomic cap+uniqueness enforcement (`INSERT ... WHERE (SELECT COUNT(*) ...) < max_size`) is a single compound statement — a hand-rolled version risks reintroducing the check-then-act race it exists to prevent |
| Ticker shape validation | A second regex for LLM-supplied tickers | `app.routes.watchlist.normalize_ticker()`/`TICKER_PATTERN` | Single source of truth for what counts as a valid ticker string — the LLM's raw output is exactly the kind of untrusted input this function was written to gate |
| Structured LLM output parsing | Manual JSON extraction / regex on the raw completion text | `response_format=SomePydanticModel` + `model_validate_json()` | LiteLLM natively translates a Pydantic model into the provider's structured-output schema; hand-parsing would re-litigate a problem the SDK already solves and lose the provider-level schema enforcement |
| Portfolio valuation for chat context | A third valuation function | `get_portfolio_state()` + `value_portfolio()` (`app/db/portfolio.py`) | Already the exact pair Phase 2's route and Phase 3's snapshot writer both call — a third implementation risks drifting in rounding/precision from the other two (this project's own D-01/D-04 Decimal-precision discipline exists specifically to prevent that kind of drift) |

**Key insight:** every "don't hand-roll" item in this phase is a function this codebase already wrote and
already tested in an earlier phase. The actual net-new code this phase contributes is thin: the LLM call
wrapper, the prompt/context builder, the per-action dispatch loop, and the chat-message persistence
module — everything else is composition of existing, proven functions.

## Common Pitfalls

### Pitfall 1: `normalize_ticker()` raises `HTTPException` directly — it must be caught per-action, not left to propagate
**What goes wrong:** `app/routes/watchlist.py:46-55`'s `normalize_ticker()` raises `HTTPException(400)`
directly rather than a plain exception. If the chat route's per-action executor calls it without an
explicit `try/except HTTPException`, one malformed ticker from the LLM (e.g. a hallucinated symbol) would
turn the **entire** `POST /api/chat` request into a 400, discarding the other valid actions in the same
reply and violating CHAT-06 ("never crash the request").
**Why it happens:** `normalize_ticker()` was written for a single-action HTTP route, where raising is the
correct behavior. Reusing it verbatim inside a loop over multiple actions changes that contract.
**How to avoid:** Wrap every `normalize_ticker()` call inside the per-action executor in its own
`try/except HTTPException`, converting the exception's `.detail` (or a fixed message) into an
`ActionResult(status="error", ...)`, exactly as shown in Pattern 2 above.
**Warning signs:** A chat test where the LLM (mock or real) proposes two actions and only one is
malformed — if the whole response is a 400 instead of one error + one success, this pitfall was hit.

### Pitfall 2: Watchlist changes must also sync the live market source — not just the DB row
**What goes wrong:** `add_watchlist_ticker()`/`remove_watchlist_ticker()` (`app/db/watchlist.py`) only
touch the `watchlist` table. The manual `POST /api/watchlist` route additionally calls
`request.app.state.market_source.add_ticker(ticker)`/`.remove_ticker(ticker)` (`app/routes/watchlist.py:
95-105, 122-133`) — that is what actually starts/stops the ticker's price feed in `PriceCache`. If the
chat route calls only the DB function, an AI-added ticker appears in the watchlist grid but never gets a
live price (stays "—" until a full backend restart), which directly fails Phase 4's success criterion 4
("Asking the assistant to add or remove a watchlist ticker updates the watchlist grid").
**Why it happens:** `04-CONTEXT.md`'s CHAT-04 reuse-contract language names only
`add_watchlist_ticker()`/`remove_watchlist_ticker()` — the market-source sync is a second, easy-to-miss
side effect that only becomes visible by reading the manual route's own body.
**How to avoid:** The chat route's watchlist-action executor must mirror
`app/routes/watchlist.py`'s add/remove handlers in full, including the exact same compensating-rollback
logic on a `market_source` failure (re-add or re-remove the DB row so the DB and the live stream never
diverge, per WR-02). Recommended: factor the two handlers' shared logic (DB call + market_source call +
compensation) out of `app/routes/watchlist.py` into two importable helpers so both the HTTP route and
`app/routes/chat.py` call the same code, rather than maintaining two independent copies.
**Warning signs:** A ticker the AI adds shows in the watchlist grid but its price cell never populates and
its sparkline never accumulates points.

### Pitfall 3: AI-initiated trades must also trigger a portfolio snapshot — not just `execute_trade()`
**What goes wrong:** `app/routes/portfolio.py:142-146`'s manual trade route calls
`record_portfolio_snapshot()` immediately after every successful `execute_trade()`, so the P&L chart
(`PnLChart`, PORT-07) gets an immediate data point rather than waiting for the 30-second periodic
recorder. `04-CONTEXT.md`'s CHAT-03 reuse-contract text names only `execute_trade()`. Skipping the
snapshot trigger for AI-initiated trades means Phase 4's own success criterion 3 ("cash, positions, header
value, **and charts** all update") is not actually satisfied for the chart half until up to 30 seconds
later.
**Why it happens:** Same root cause as Pitfall 2 — the reuse contract's plain-language description names
the primary function, and the secondary side effect is only visible in the calling route's body.
**How to avoid:** `_execute_trade_action()` must call `record_portfolio_snapshot(price_cache=...)`
immediately after a successful `execute_trade()`, inside its own try/except that logs (never raises) on
failure — the exact same non-blocking-failure posture the manual route uses (Pattern 2 above).
**Warning signs:** A manual buy immediately adds a P&L chart point; an AI-initiated buy of the same ticker
does not until the next 30-second tick.

### Pitfall 4: `LLM_MOCK` must be read per-request, not resolved once at app-startup
**What goes wrong:** `create_market_data_source()` (the closest existing precedent) is called exactly
once, inside `create_app()`'s lifespan, and the choice is frozen for the process's lifetime. If
`app/routes/chat.py` copies that pattern for `LLM_MOCK` (e.g., resolving which client to use at router
construction time), tests using the shared `client` fixture (`tests/conftest.py`) cannot flip `LLM_MOCK`
per-test via `monkeypatch.setenv()` — the app object is already built with the real-vs-mock choice baked
in before the test body runs.
**Why it happens:** Copying the market-data factory pattern verbatim seems consistent, but `LLM_MOCK` has
a different testing requirement: individual tests need to toggle it (e.g., one test proves the mock path
never calls `litellm`, another proves error handling on a monkeypatched real client), while
`MASSIVE_API_KEY`'s simulator-vs-real choice is never toggled mid-test-suite.
**How to avoid:** Resolve `LLM_MOCK` inside the request handler (`_is_mock_mode()` in Pattern 1), not at
`create_app()`/router-construction time.
**Warning signs:** A test that does `monkeypatch.setenv("LLM_MOCK", "true")` then `client.post("/api/chat", ...)`
still attempts a real network call.

### Pitfall 5: A synchronous `litellm.completion()` call inside an `async def` route handler blocks the whole server
**What goes wrong:** FastAPI's async route handlers run on a single event loop shared by every concurrent
request, including the long-lived SSE connection at `/api/stream/prices`. A blocking, network-bound call
made directly (not via `asyncio.to_thread()` or an async client) stalls that event loop for the full
LLM round-trip — every other in-flight request, including price-stream ticks to already-connected
clients, pauses for the duration of the chat call.
**Why it happens:** `SKILL.md`'s example (correctly) shows the simplest possible call — `completion(...)`
— with no mention of the async/threading concern, because the skill is provider-pattern documentation,
not a FastAPI integration guide.
**How to avoid:** Always call the real client via `await asyncio.to_thread(chat_completion, messages, ChatCompletionResult)`,
exactly mirroring `app/db/connection.py`'s `run_db()` seam for blocking SQLite calls (Pattern 1).
**Warning signs:** Watchlist prices visibly stop updating in the browser for several seconds every time a
chat message is sent.

### Pitfall 6: Don't let a `chat_messages.role` value ever originate from parsed LLM output
**What goes wrong:** `chat_messages.role` is `CHECK (role IN ('user', 'assistant'))`
(`backend/app/db/schema.sql:49`). The value passed to `append_chat_message(role=...)` must always be the
Python string literal `"assistant"` (for the model's own reply) or `"user"` (for what the person typed) —
never a value read off `ChatCompletionResult` or any other parsed LLM field. This is naturally true by
construction if `app/db/chat.py`'s call sites always pass a literal, but worth stating explicitly since
it's the one column where "the AI decides the value" would be a real integrity risk if the code were
written more generically.
**Why it happens:** Easy to introduce accidentally if a future refactor tries to make the
persistence call "more generic" by passing through a role field from somewhere in the LLM's structured
output.
**How to avoid:** `append_chat_message()`'s two call sites in `app/routes/chat.py` always pass a hardcoded
string literal for `role=`, never a variable sourced from `result` (the parsed `ChatCompletionResult`).
**Warning signs:** N/A at this phase's implementation — this is a "don't regress this later" note, not a
currently-present bug.

## Code Examples

### The three Pydantic schemas (structured-output contract, exact per `planning/PLAN.md` §9)

```python
# app/llm/schemas.py
# Source: planning/PLAN.md §9 (authoritative schema, reproduced exactly) +
# 04-CONTEXT.md's Pydantic-modeling decision.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Trade(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class ChatCompletionResult(BaseModel):
    message: str
    # default_factory=list (not `= []`) is the idiomatic Pydantic v2 form —
    # avoids any ambiguity about mutable-default sharing across instances,
    # even though Pydantic v2 already deep-copies `= []` safely.
    trades: list[Trade] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)
```

### `app/db/chat.py` — mirrors `app/db/snapshots.py`'s "one module, one table" shape exactly

```python
# app/db/chat.py
# Source pattern: backend/app/db/snapshots.py:1-56 (verified this session,
# read in full) — same DESC+LIMIT-then-reverse-in-Python idiom as
# list_snapshots(), same run_db() seam, same "reuses existing functions,
# writes nothing else" module discipline.
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone

from .connection import DEFAULT_USER_ID, run_db

logger = logging.getLogger(__name__)

# Shared by both POST /api/chat's context-builder AND GET /api/chat/history,
# per 04-CONTEXT.md's explicit "reuse the same recent-history query" guidance.
# 20 rows ~= 10 conversational turns (one user + one assistant message per
# turn) — see Assumptions Log A2 for the reasoning behind this exact number.
MAX_CONTEXT_MESSAGES = 20


async def append_chat_message(
    *,
    role: str,
    content: str,
    actions: list[dict] | None = None,
    user_id: str = DEFAULT_USER_ID,
) -> dict:
    """Insert one chat_messages row. `actions` is None (-> SQL NULL) for a
    user-role message, and a (possibly empty) list for an assistant-role
    message — an empty list is a real "zero actions were taken" value,
    distinct from NULL's "not applicable to this role"."""
    message_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    actions_json = json.dumps(actions) if actions is not None else None

    def _txn(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (message_id, user_id, role, content, actions_json, created_at),
        )

    await run_db(_txn)
    return {
        "id": message_id, "role": role, "content": content,
        "actions": actions, "created_at": created_at,
    }


async def list_recent_chat_messages(
    *, limit: int = MAX_CONTEXT_MESSAGES, user_id: str = DEFAULT_USER_ID
) -> list[dict]:
    """Return up to `limit` most-recent messages, oldest first — same
    DESC-then-reverse idiom as list_snapshots() (app/db/snapshots.py:59-84)."""

    def _query(conn: sqlite3.Connection) -> list[dict]:
        rows = conn.execute(
            "SELECT role, content, actions, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "actions": json.loads(row["actions"]) if row["actions"] else None,
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    rows = await run_db(_query)
    rows.reverse()
    return rows
```
`[VERIFIED: backend/app/db/schema.sql:46-53]` — the table this module reads/writes, quoted verbatim:
```sql
CREATE TABLE IF NOT EXISTS chat_messages (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL DEFAULT 'default',
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    actions    TEXT,
    created_at TEXT NOT NULL
);
```

### `app/llm/mock.py` — deterministic, keyword-triggered, never imports `litellm`

```python
# app/llm/mock.py
from __future__ import annotations

import re

from app.llm.schemas import ChatCompletionResult, Trade, WatchlistChange

# Deliberately simple keyword patterns — this is a test/demo fixture, not a
# real NLU layer. Every match still round-trips through the exact same
# ChatCompletionResult Pydantic shape the real client produces (CHAT-07).
_BUY_RE = re.compile(r"\bbuy\s+(\d+(?:\.\d+)?)\s+(?:shares?\s+of\s+)?([a-z.]{1,10})\b", re.I)
_SELL_RE = re.compile(r"\bsell\s+(\d+(?:\.\d+)?)\s+(?:shares?\s+of\s+)?([a-z.]{1,10})\b", re.I)
_ADD_RE = re.compile(r"\badd\s+([a-z.]{1,10})\s+to\s+(?:my\s+)?watchlist\b", re.I)
_REMOVE_RE = re.compile(r"\bremove\s+([a-z.]{1,10})\s+from\s+(?:my\s+)?watchlist\b", re.I)


def mock_chat_completion(messages: list[dict]) -> ChatCompletionResult:
    """Pure function — no network, no litellm import. Parses the latest
    user turn for buy/sell/add/remove keywords and returns a deterministic,
    schema-valid ChatCompletionResult every time."""
    user_text = messages[-1]["content"]

    trades: list[Trade] = []
    if m := _BUY_RE.search(user_text):
        trades.append(Trade(ticker=m.group(2).upper(), side="buy", quantity=float(m.group(1))))
    if m := _SELL_RE.search(user_text):
        trades.append(Trade(ticker=m.group(2).upper(), side="sell", quantity=float(m.group(1))))

    watchlist_changes: list[WatchlistChange] = []
    if m := _ADD_RE.search(user_text):
        watchlist_changes.append(WatchlistChange(ticker=m.group(1).upper(), action="add"))
    if m := _REMOVE_RE.search(user_text):
        watchlist_changes.append(WatchlistChange(ticker=m.group(1).upper(), action="remove"))

    if trades or watchlist_changes:
        message = "Done — I've made the changes you asked for."
    else:
        message = "This is a mock response (LLM_MOCK=true) — ask me to buy/sell a ticker or update your watchlist."

    return ChatCompletionResult(message=message, trades=trades, watchlist_changes=watchlist_changes)
```

### Frontend types (mirrors the existing `lib/types.ts` convention)

```typescript
// frontend/lib/types.ts additions
// Source pattern: existing WatchlistItem/TradeResult interfaces in this file.

export type ChatRole = "user" | "assistant";

export interface ChatActionResult {
  kind: "trade" | "watchlist";
  status: "success" | "error";
  ticker: string;
  side?: "buy" | "sell";
  action?: "add" | "remove";
  quantity?: number;
  price?: number;
  error?: string;
}

export interface ChatMessage {
  role: ChatRole;
  content: string;
  actions: ChatActionResult[] | null;
  created_at: string;
}

export interface ChatResponse {
  message: string;
  actions: ChatActionResult[];
}
```

```typescript
// frontend/lib/api.ts additions
// Source pattern: existing executeTrade()/addWatchlistTicker() in this file.

export async function fetchChatHistory(): Promise<ChatMessage[]> {
  const response = await fetch(`${API_BASE}/api/chat/history`);
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  const body = (await response.json()) as { messages: ChatMessage[] };
  return body.messages;
}

export async function sendChatMessage(message: string): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as ChatResponse;
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-------------------|---------------|--------|
| Hand-rolled "respond in JSON" prompt + manual `json.loads()`/regex extraction | Provider-native structured outputs via `response_format=SomePydanticModel` | Already the project's chosen approach (not a change made in this phase) | No brittle prompt-engineering-for-JSON-shape needed; the provider enforces the schema at generation time, and `model_validate_json()` gives a typed, IDE-checkable result object |

**Deprecated/outdated:** Not applicable — this is this project's first and only LLM integration; there is
no prior implementation in this codebase to compare against.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | LLM-call-level failures (network error, auth failure, rate limit — not just structured-output parse failures) are treated identically to "unparseable model output" at the `chat_completion()` boundary: both return `None`, both produce the same graceful fallback message, HTTP 200. `04-CONTEXT.md`'s CHAT-06 language explicitly names "unparseable model output" but doesn't explicitly address a total call failure (e.g. the empty-API-key case this very sandbox exhibits). | Architecture Patterns Pattern 1, Code Examples | Low — if this judgment call is wrong and the intended behavior is instead a distinct HTTP error status for call-level failures vs. parse failures, the fix is a small branch inside `chat_completion()`'s except block; no data-model or schema change needed |
| A2 | `MAX_CONTEXT_MESSAGES = 20` (≈10 conversational turns of user+assistant pairs) is the exact number for both the LLM context window and `GET /api/chat/history`'s bound, per CONTEXT.md's "reuse the same recent-history query" + "~10 turns" discretion grant. Interpreted "10 turns" as 10 user+assistant *pairs* = 20 rows, not 10 rows. | `app/db/chat.py`'s `MAX_CONTEXT_MESSAGES` constant | Low — a one-line constant change if a different exact number is preferred; does not affect any other design decision |
| A3 | `ChatRequest.message` is capped at `Field(min_length=1, max_length=2000)` — a judgment call for defense-in-depth against an unbounded prompt-size/cost DoS vector, no explicit requirement or UI-SPEC text specifies this exact number. | Security Domain, `ChatRequest` Pydantic model | Low — a display/UX-only concern if wrong (the input textarea has no hard client-side cap specified either); adjustable without touching any other code |
| A4 | The watchlist-action executor's `market_source.add_ticker()`/`remove_ticker()` calls and the trade-action executor's `record_portfolio_snapshot()` call are NOT explicitly named in `04-CONTEXT.md`'s reuse-contract text, but are required by Phase 4's own ROADMAP.md success criteria (3 and 4) and by direct inspection of the manual routes' full bodies. Treated as locked requirements (not optional discretion) in this research, since without them two of the five phase success criteria cannot be satisfied. | Common Pitfalls 2 & 3, Phase Requirements table | Medium — if the planner disagrees these are in-scope, CHAT-04/CHAT-03's live-demo behavior visibly regresses (a newly-added ticker never streams a price; an AI trade doesn't move the P&L chart for up to 30s) even though the DB-level "execute the trade/mutate the watchlist" requirement is technically met |
| A5 | `litellm`'s and `pydantic`'s `SUS` package-legitimacy verdicts are dispositioned "Approved, no checkpoint" rather than gated behind a `checkpoint:human-verify` task, on the basis that both were already installed and exercised in a prior session action (not a new install this phase) and the `SUS` signal traces to a seam limitation (no PyPI download-count source), not an actual suspicious-package signal. | Package Legitimacy Audit | Low — worst case, the planner adds a `checkpoint:human-verify` task anyway; no functional impact either way since the packages are already installed and were already used successfully in this session's spike |

## Open Questions

1. **Does the real Cerebras-served `gpt-oss-120b` model reliably honor the `trades: []`/`watchlist_changes: []` empty-array default when the schema is translated to a provider-side strict JSON schema (which typically marks all object properties as required)?**
   - What we know: the spike confirmed the *request* is accepted (structurally valid, reached OpenRouter). The *response* shape/adherence under a real key was never observed (401 before any model output was returned).
   - What's unclear: whether the model ever omits the `trades`/`watchlist_changes` keys entirely (which the Pydantic model's `default_factory=list` would silently paper over during parsing — `model_validate_json()` fills the default if the key is missing) vs. whether it always emits an empty array explicitly.
   - Recommendation: no code change needed — `Field(default_factory=list)` already covers both cases (key present-and-empty, and key entirely absent) equally correctly. This is purely a "what does the live model actually do" curiosity, not a code risk. No action required.

2. **Should `POST /api/chat` reject with an HTTP error (e.g. 503) if `LLM_MOCK` is false and `OPENROUTER_API_KEY` is empty, rather than going through the full graceful-fallback-message flow?**
   - What we know: in this sandbox, an empty key produces a `litellm.AuthenticationError`-shaped failure, which Pattern 1's broad `except Exception` already catches and turns into the same graceful assistant message as any other call failure (per Assumption A1).
   - What's unclear: whether a "the app isn't configured with a working key" state deserves a more diagnostic error (visible in logs, at minimum) versus reading identically to "the model returned nonsense."
   - Recommendation: `logger.exception(...)` inside `chat_completion()`'s except block already logs the full exception server-side for diagnosis — the graceful chat-facing message can stay generic. No further action needed unless the planner wants a distinct startup-time warning log line when `LLM_MOCK` is false and `OPENROUTER_API_KEY` is empty (a nice-to-have, not a requirement).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| `litellm` (PyPI) | `app/llm/client.py` real calls | ✓ | 1.95.0 (confirmed via `importlib.metadata` this session) | — |
| `pydantic` (PyPI) | Structured-output schemas, request/response models | ✓ | 2.12.5 (confirmed via `importlib.metadata` this session) | — |
| `OPENROUTER_API_KEY` | Real (non-mock) LLM calls — CHAT-01 through CHAT-05's live-key behavior | ✗ in this sandbox (present in `.env` but resolves to an empty string — a sandbox security boundary, per `04-CONTEXT.md`'s spike finding) | — | `LLM_MOCK=true` for all automated tests this phase; live-key verification deferred to human, per `04-CONTEXT.md`'s Deferred Ideas |
| Network egress to `openrouter.ai` | Real LLM calls | ✓ (confirmed by this session's spike — the request reached OpenRouter and received a structured 401 JSON body, not a connection failure) | — | — |
| pytest / pytest-asyncio / httpx (TestClient) | All backend automated tests, including this phase's new `tests/llm/`, `tests/db/test_chat.py`, `tests/routes/test_chat.py` | ✓ (already installed, used by every prior phase) | per `backend/pyproject.toml`'s `[dev]` extras | — |
| Frontend test framework (Vitest/RTL/etc.) | UI-04's automated verification | ✗ — not installed anywhere in this repo | — | None needed this phase — `TEST-03` (frontend component tests) is explicitly Phase 5's requirement per `.planning/REQUIREMENTS.md`'s traceability table; UI-04 is validated manually this phase (see Validation Architecture) |

**Missing dependencies with no fallback:** none blocking — `OPENROUTER_API_KEY` has a documented,
locked fallback (`LLM_MOCK=true`) for every automated-test purpose this phase needs.

**Missing dependencies with fallback:** `OPENROUTER_API_KEY` (fallback: `LLM_MOCK=true`); frontend test
framework (fallback: manual verification, framework installation deferred to Phase 5 per existing
requirement scoping).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ / pytest-asyncio 0.24+ (already configured, `backend/pyproject.toml:33-39`) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `testpaths = ["tests"]` |
| Quick run command | `cd backend && uv run --extra dev pytest tests/llm/ tests/db/test_chat.py tests/routes/test_chat.py -x` |
| Full suite command | `cd backend && uv run --extra dev pytest` |

No frontend test framework exists in this repo (`frontend/package.json` has no Vitest/Jest/RTL — verified
this session). `TEST-03` (frontend component tests) is Phase 5's requirement, not this phase's — UI-04 is
covered by manual verification only, consistent with that scoping.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| CHAT-01 | `POST /api/chat` returns a complete `{message, actions}` JSON body; `GET /api/chat/history` returns persisted messages after a send, proving refresh-durability | integration | `pytest tests/routes/test_chat.py::test_post_chat_returns_message_and_actions tests/routes/test_chat.py::test_history_reflects_a_prior_send -x` | ❌ Wave 0 |
| CHAT-02 | Portfolio context (cash, positions w/ P&L, watchlist w/ live prices) and recent history are included in the prompt sent to the LLM, fresh on every call | unit | `pytest tests/routes/test_chat.py::test_context_builder_includes_cash_and_positions tests/routes/test_chat.py::test_context_builder_reflects_a_trade_made_between_two_turns -x` (build the prompt-builder as a directly-callable, un-exported-but-testable function; assert on its output dict/string, not on a live LLM call) | ❌ Wave 0 |
| CHAT-03 | AI-initiated buy/sell debits/credits cash and updates positions identically to a manual trade, via `execute_trade()`; a post-trade snapshot is recorded (Pitfall 3) | integration | `pytest tests/routes/test_chat.py::test_mock_triggered_trade_updates_portfolio_like_a_manual_trade tests/routes/test_chat.py::test_mock_triggered_trade_records_a_snapshot -x` (env: `LLM_MOCK=true`, message text matching `mock.py`'s buy/sell keyword pattern) | ❌ Wave 0 |
| CHAT-04 | AI-initiated watchlist add/remove updates the `watchlist` table AND the live market source (Pitfall 2) | integration | `pytest tests/routes/test_chat.py::test_mock_triggered_add_ticker_updates_watchlist_and_starts_streaming tests/routes/test_chat.py::test_mock_triggered_remove_ticker_stops_streaming -x` (assert on `client.app.state.market_source`'s tracked tickers, or on `price_cache.get_price(ticker)` eventually returning non-None, in addition to the watchlist row) | ❌ Wave 0 |
| CHAT-05 | The response's `actions` array carries one entry per executed action with `status`/human-readable fields | integration | `pytest tests/routes/test_chat.py::test_response_actions_include_one_entry_per_executed_action -x` | ❌ Wave 0 |
| CHAT-06 | A failed action (insufficient cash) produces `status: "error"` with a human-readable message, HTTP 200, not a 500; a malformed model response produces a graceful fallback message, HTTP 200 | unit + integration | `pytest tests/llm/test_client.py::test_malformed_json_returns_none tests/routes/test_chat.py::test_insufficient_cash_action_returns_error_status_not_500 tests/routes/test_chat.py::test_llm_failure_returns_graceful_fallback_message -x` | ❌ Wave 0 |
| CHAT-07 | `LLM_MOCK=true` never imports/calls `litellm`, and produces the same schema-valid `ChatCompletionResult` shape as the real client on repeated identical input | unit | `pytest tests/llm/test_mock.py::test_mock_never_calls_litellm tests/llm/test_mock.py::test_mock_is_deterministic_for_identical_input -x` (the never-calls-litellm test monkeypatches `litellm.completion` to raise, proving the mock path truly never reaches it) | ❌ Wave 0 |
| UI-04 | Chat panel is docked/collapsible with input, scrolling history, loading indicator | manual-only | N/A — no frontend test framework this phase (see Environment Availability); verified via `checkpoint:human-verify` / conversational UAT against the running dev server | N/A |
| TEST-02 | Backend unit tests cover LLM structured-output parsing, including malformed/invalid responses | unit | `pytest tests/llm/test_client.py -x` — covers: valid JSON parses correctly; missing optional fields default to `[]`; malformed/non-JSON string returns `None`; a schema-violating JSON (wrong field type) returns `None`; a raised `litellm` exception (monkeypatched) returns `None` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && uv run --extra dev pytest tests/llm/ tests/db/test_chat.py tests/routes/test_chat.py -x` (this phase's new surface only, fast feedback)
- **Per wave merge:** `cd backend && uv run --extra dev pytest` (full backend suite — proves this phase didn't regress Phases 1-3)
- **Phase gate:** Full suite green before `/gsd-verify-work`, plus a manual UAT pass covering UI-04's docked/collapsible/loading-indicator behavior (no automated frontend coverage exists yet)

### Wave 0 Gaps
- [ ] `tests/llm/__init__.py` — new test package
- [ ] `tests/llm/test_client.py` — covers TEST-02, CHAT-06's malformed-output clause
- [ ] `tests/llm/test_mock.py` — covers CHAT-07
- [ ] `tests/db/test_chat.py` — covers `append_chat_message()`/`list_recent_chat_messages()` in isolation, mirroring `tests/db/test_snapshots.py`'s style (writer correctness, restart durability via a fresh `connect()`, ordering)
- [ ] `tests/routes/test_chat.py` — covers CHAT-01 through CHAT-06's integration angles, using the existing `client`/`temp_db` fixtures from `tests/conftest.py` with `monkeypatch.setenv("LLM_MOCK", "true")` set per-test (enabled specifically by Pitfall 4's per-request `LLM_MOCK` resolution)
- [ ] No new fixtures needed beyond what `tests/conftest.py` already provides — `client` (TestClient with real lifespan) and `temp_db` (isolated SQLite file) cover every test above; `LLM_MOCK` is set via `monkeypatch.setenv()` inside each test function, not a new fixture, since it must vary per-test

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|-----------------|---------|--------------------|
| V2 Authentication | No | This app has no auth anywhere (`user_id="default"` hardcoded project-wide, per `planning/PLAN.md` §7 and `.planning/REQUIREMENTS.md`'s explicit Out-of-Scope entry for multi-user/login) — unchanged by this phase |
| V3 Session Management | No | No sessions exist in this app |
| V4 Access Control | No | Single hardcoded user, no authorization boundaries to enforce |
| V5 Input Validation | Yes | `ChatRequest.message` bounded via Pydantic `Field(min_length=1, max_length=2000)` (Assumption A3); every LLM-supplied ticker string routed through `normalize_ticker()`/`TICKER_PATTERN` before touching the DB or `market_source` (same control already proven for manual input in Phase 1); `Trade.quantity`/`Trade.side` and `execute_trade()`'s own internal guard (`if not quantity_dec.is_finite() or quantity_dec <= 0: raise TradeRejectedError`, `[VERIFIED: backend/app/db/portfolio.py:117-118]`) reject a non-positive/NaN/infinite quantity even though the LLM's output bypasses the HTTP route's `Field(gt=0, le=1_000_000_000)` layer entirely — `execute_trade()`'s own docstring explicitly names this as the reason its internal guard exists: `"this function is the documented CHAT-03 entry point Phase 4's AI copilot calls directly, bypassing that layer entirely"` `[VERIFIED: backend/app/db/portfolio.py:108-116]` |
| V6 Cryptography | No | No new cryptographic operations this phase; `OPENROUTER_API_KEY` is read from the process environment by `litellm` directly (never logged, never stored in SQLite, never echoed to the client) |

### Known Threat Patterns for this phase's stack (LLM structured-output tool-calling)

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| Prompt injection via chat message content (user tries to get the model to propose an oversized/malicious trade or bypass validation through crafted phrasing) | Tampering / Elevation of Privilege | The LLM's output is never trusted as validated input — every proposed `Trade`/`WatchlistChange` still passes through the exact same `normalize_ticker()` + `execute_trade()`'s atomic cash/quantity guards + `add_watchlist_ticker()`'s cap/uniqueness constraint that a manual, human-typed request would. No prompt-injection payload can skip these checks because the checks live in the DB-layer functions, not in the prompt |
| Unbounded LLM-driven request cost/latency (a very long user message inflates token cost per call) | Denial of Service | `ChatRequest.message` capped at `Field(max_length=2000)` (Assumption A3) |
| Leaking `OPENROUTER_API_KEY` into logs or chat responses | Information Disclosure | The key is read only by `litellm` internally from the process environment; `app/llm/client.py`'s `logger.exception(...)` calls log the exception object/response body, never the request headers or the key itself — this matches `litellm`'s own behavior of never echoing the API key in its exception messages |
| A single malformed/adversarial action in a multi-action reply causing the whole request to fail (a form of application-level DoS against the user's own conversation) | Denial of Service | Pitfall 1/Pattern 2 — every action executes inside its own try/except; one failure never aborts the others or the request |
| SQL injection via an LLM-hallucinated ticker string reaching a raw query | Tampering | Every SQL statement in `app/db/chat.py`, `app/db/portfolio.py`, `app/db/watchlist.py` uses `?` placeholders exclusively — no LLM-derived string is ever interpolated into SQL text (same discipline already documented at the top of `app/db/watchlist.py`: `"Every statement in this module uses ? placeholders; no value is ever interpolated into SQL text, even a ticker that has already passed shape validation upstream"`) |

## Sources

### Primary (HIGH confidence)
- `backend/app/db/portfolio.py` (read in full this session) — `execute_trade()`, `get_portfolio_state()`, `value_portfolio()`, error hierarchy
- `backend/app/db/watchlist.py` (read in full this session) — `add_watchlist_ticker()`, `remove_watchlist_ticker()`, `WatchlistCapReachedError`
- `backend/app/db/snapshots.py` (read in full this session) — the `chat.py` module's structural precedent
- `backend/app/db/schema.sql` (read in full this session) — `chat_messages` table definition
- `backend/app/db/connection.py` (read in full this session) — `run_db()`, `DEFAULT_USER_ID`
- `backend/app/routes/watchlist.py` (read in full this session) — `normalize_ticker()`, `TICKER_PATTERN`, market-source compensation pattern
- `backend/app/routes/portfolio.py` (read in full this session) — router-factory pattern, post-trade snapshot trigger (the pattern behind Pitfall 3)
- `backend/app/main.py` (read in full this session) — `create_app()` mount point, `create_market_data_source()`'s startup-time-resolution pattern (the anti-pattern behind Pitfall 4)
- `backend/app/market/factory.py` (read in full this session) — the env-var-driven factory pattern `LLM_MOCK`'s dispatcher deliberately does NOT copy verbatim
- `backend/pyproject.toml` (read in full this session) — confirmed `litellm>=1.95.0`, `pydantic>=2.12.5` already present
- `importlib.metadata.version()` executed directly this session — confirmed installed versions `litellm 1.95.0`, `pydantic 2.12.5`
- `.claude/skills/cerebras/SKILL.md` (read in full this session) — the authoritative, spike-validated LiteLLM/OpenRouter/Cerebras call pattern
- `frontend/components/PortfolioProvider.tsx`, `PriceStreamProvider.tsx`, `WatchlistPanel.tsx`, `TradeBar.tsx`, `AddTickerForm.tsx`, `PositionsTable.tsx` (all read in full this session) — the `.then()`-chain idiom, non-optimistic-mutation pattern, skeleton/error/empty-state conventions
- `frontend/lib/api.ts`, `frontend/lib/types.ts` (read in full this session) — existing fetch-helper and wire-type conventions
- `frontend/app/layout.tsx`, `frontend/app/page.tsx` (read in full this session) — provider-mount and dashboard-grid structure `ChatPanel` slots alongside
- `.planning/phases/04-ai-copilot/04-CONTEXT.md`, `04-UI-SPEC.md` (read in full this session) — locked decisions, approved UI contract
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md` (read in full this session) — CHAT-01–07/UI-04/TEST-02 exact text, Phase 4 success criteria
- `backend/tests/db/test_snapshots.py`, `backend/tests/routes/test_portfolio.py`, `backend/tests/conftest.py` (read in full this session) — testing style/fixtures this phase's new tests mirror
- `gsd_run query package-legitimacy check --ecosystem pypi litellm pydantic` executed this session — legitimacy seam verdicts (both `SUS`, dispositioned in Package Legitimacy Audit)

### Secondary (MEDIUM confidence)
- Context7 `/berriai/litellm` — exception hierarchy (`AuthenticationError`, `Timeout`, `APIConnectionError` all wrap `openai.*` counterparts and are exported at `litellm.<ExceptionName>`) and structured-output usage patterns (`response_format=SomePydanticModel`, `model_validate_json()`). Informed the decision to catch broad `Exception` in `chat_completion()` rather than enumerate litellm's specific exception subclasses, since the hierarchy's exact inheritance relative to a single "catch-all" base class was not confirmed with full certainty from the docs alone.

### Tertiary (LOW confidence)
- None — no unverified WebSearch-only claims were used in this research; the one genuinely open runtime-behavior question (does the live model reliably emit the schema) is recorded in Open Questions rather than asserted as fact.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — both packages version-confirmed installed this session; the call pattern is copied verbatim from the project's own already-spike-validated skill file
- Architecture: HIGH — every reused function (`execute_trade()`, `add_watchlist_ticker()`, `get_portfolio_state()`, etc.) was read in full this session; the two non-obvious integration requirements (Pitfalls 2 & 3) were discovered by reading the manual routes' complete bodies, not inferred
- Pitfalls: HIGH for the six documented here (all traced to specific lines in already-read source); MEDIUM for live-model runtime behavior (Open Question 1) since no real API key was available to observe actual generation output this session

**Research date:** 2026-08-04
**Valid until:** 30 days for the backend/architecture findings (stable, internal codebase); the LLM provider-behavior findings (Open Question 1, litellm exception hierarchy) should be re-checked if `litellm` is upgraded past `1.95.0` or if OpenRouter/Cerebras's structured-output contract changes, given the fast-moving nature of that ecosystem
