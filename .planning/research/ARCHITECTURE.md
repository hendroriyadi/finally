# Architecture Research

**Domain:** Single-container FastAPI + SQLite + Next.js (static export) trading workstation — integrating a new DB/API/LLM layer on top of an existing real-time market-data subsystem
**Researched:** 2026-08-01
**Confidence:** MEDIUM (core FastAPI mechanisms verified against official docs; LLM-agent-reuse and build-order guidance are general community patterns, not FinAlly-specific)

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────┐
│  Browser                                                           │
│  EventSource → /api/stream/prices   fetch() → /api/*               │
└───────────────────────────┬─────────────────────────────────────┬─┘
                             │                                     │
┌────────────────────────────▼─────────────────────────────────────▼┐
│  FastAPI app (single process, port 8000)                           │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────┐    │
│  │ lifespan()  — startup/shutdown context manager             │    │
│  │  1. create_market_data_source(cache) + source.start()      │    │
│  │  2. db.init_db()  (create tables if missing, seed if empty)│    │
│  │  3. store cache + db handle on app.state                   │    │
│  │  4. start portfolio_snapshot background task (30s interval)│    │
│  └───────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │
│  │ /api/stream │ │ /api/portfolio│ │/api/watchlist│ │ /api/chat  │ │
│  │  (existing) │ │  (new route) │ │  (new route) │ │ (new route)│ │
│  └──────┬──────┘ └───────┬──────┘ └───────┬──────┘ └─────┬──────┘ │
│         │                │                │              │        │
│         │         ┌──────▼────────────────▼──────┐       │        │
│         │         │  portfolio/service.py         │◄──────┘        │
│         │         │  execute_trade(), get_state()  │  (LLM calls   │
│         │         │  — THE single trade code path  │   this too)   │
│         │         └──────┬────────────────┬────────┘               │
│         │                │                │                        │
│  ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐                │
│  │ PriceCache  │  │  db/ repo   │  │  llm/chat.py │                │
│  │ (existing,  │  │  layer      │  │  (new)       │                │
│  │  read-only  │  │  (new)      │  │  builds      │                │
│  │  from here) │  │  sqlite3    │  │  context,    │                │
│  └─────────────┘  └─────────────┘  │  calls       │                │
│                                     │  LiteLLM     │                │
│                                     └──────┬───────┘                │
│                                            │                        │
│  app.frontend("/", directory="static")    │ OpenRouter → Cerebras  │
│  (fallback for all non-API GET routes)    ▼                        │
└───────────────────────────────────────────────────────────────────┘
                             │
                             ▼
                  db/finally.db (SQLite, volume-mounted)
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `app/main.py` (new) | App assembly: creates FastAPI instance, registers `lifespan`, includes all routers, mounts frontend fallback | `FastAPI(lifespan=lifespan)`, `app.include_router(...)` per feature |
| `app/market/*` (existing, frozen) | Owns price generation and the `PriceCache`; exposes `create_market_data_source()` and `create_stream_router()` | Unchanged — new code only *reads* `PriceCache.get()/get_all()`, never re-implements fetching |
| `app/db/` (new) | Connection management, lazy schema init/seed, thin repository functions per table | stdlib `sqlite3`, one `db.py` with `get_connection()`, `init_db()`; queries wrapped in `asyncio.to_thread()` |
| `app/portfolio/service.py` (new) | **The single source of truth for trade execution and portfolio valuation.** Pure functions that take `(db, price_cache, ticker, side, qty)` and return a result or raise a validated error | Plain Python functions, no FastAPI/HTTP concerns — callable from both a route handler and the LLM handler |
| `app/routes/portfolio.py`, `watchlist.py` (new) | Thin HTTP adapters: parse request, call `portfolio/service.py` or `db` repo functions, shape the JSON response, map domain errors → HTTP status codes | FastAPI `APIRouter`, Pydantic request/response models |
| `app/llm/chat.py` (new) | Builds prompt context (portfolio + watchlist + history), calls LiteLLM/OpenRouter with `response_format=<PydanticModel>`, parses the structured result, **calls `portfolio/service.py` and watchlist repo for each action**, persists the chat turn | LiteLLM `completion(..., response_format=ChatResponse, extra_body={"provider": {"order": ["cerebras"]}})` |
| `app.frontend(...)` or catch-all route (new) | Serves the Next.js static export; falls back to `index.html` for client-side routes; never shadows `/api/*` | FastAPI ≥0.138 native `app.frontend()`, or `StaticFiles` mount + catch-all for older versions |

## Recommended Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI() + lifespan + include_router + frontend mount
│   ├── market/                 # EXISTING — do not modify internals
│   ├── db/
│   │   ├── connection.py       # get_connection(), run_in_thread() wrapper
│   │   ├── schema.py           # CREATE TABLE IF NOT EXISTS statements (or schema.sql loader)
│   │   ├── seed.py             # default user/watchlist seeding, idempotent
│   │   └── repository.py       # thin CRUD: get_portfolio(), get_watchlist(), record_trade(), snapshot()
│   ├── portfolio/
│   │   ├── service.py          # execute_trade(), get_portfolio_state(), value_history()
│   │   └── models.py           # Pydantic: TradeRequest, PortfolioResponse, Position
│   ├── watchlist/
│   │   ├── service.py          # add_ticker(), remove_ticker() — talks to db + MarketDataSource
│   │   └── models.py
│   ├── llm/
│   │   ├── chat.py             # handle_message(): context → completion() → execute actions
│   │   ├── prompts.py          # system prompt template
│   │   └── schemas.py          # ChatResponse(message, trades[], watchlist_changes[])
│   └── routes/
│       ├── portfolio.py        # GET/POST wrappers around portfolio/service.py
│       ├── watchlist.py        # GET/POST/DELETE wrappers around watchlist/service.py
│       ├── chat.py             # POST /api/chat wraps llm/chat.py
│       └── health.py           # GET /api/health
├── db/schema.sql                # raw DDL (source of truth, loaded by db/schema.py)
└── static/                      # frontend build output, copied in by Dockerfile
```

### Structure Rationale

- **`portfolio/service.py` is deliberately framework-agnostic.** It is the one place that checks "enough cash to buy" / "enough shares to sell", updates `positions`, appends to `trades`, and writes a `portfolio_snapshots` row. Both `routes/portfolio.py` (manual trade bar) and `llm/chat.py` (AI-initiated trade) call the exact same function — this is the mechanism that satisfies "the LLM calls back into the same trade-execution logic the manual UI uses."
- **`db/` is a thin layer, not an ORM.** Given single-user/no-auth/SQLite-by-design (PLAN.md §3), stdlib `sqlite3` with hand-written repository functions is proportionate — it avoids adding SQLAlchemy as a new dependency and mirrors the project's existing preference for minimal, explicit code (the market-data layer uses no ORM either).
- **`routes/` stays thin.** Each route module only does request parsing, calling into `service.py`/`repository.py`, and HTTP-shaping the response. This keeps trade/portfolio logic unit-testable without spinning up FastAPI's `TestClient`.
- **`llm/` is isolated from `routes/`.** `chat.py` depends on `portfolio/service.py` and `watchlist/service.py`, never the other way around — so LLM integration can be developed and tested with `LLM_MOCK=true` independent of the HTTP layer.

## Architectural Patterns

### Pattern 1: Existing subsystem as a read-only dependency, not a peer to extend

**What:** `app/market/` (PriceCache, MarketDataSource, SSE router) is complete and tested. New code treats it as a library: it imports `PriceCache`, `create_market_data_source`, `create_stream_router` and calls their existing public methods (`get()`, `get_all()`, `add_ticker()`, `remove_ticker()`). No new code should reach into `PriceCache._prices` or re-implement polling/streaming.

**When to use:** Any time a new feature needs live prices — portfolio valuation, trade execution (fill price), watchlist display, LLM context building.

**Trade-offs:** Slight indirection (must go through `PriceCache.get(ticker)` and handle `None` for un-seeded tickers), but guarantees a single source of truth for price state and keeps the market-data subsystem's existing test coverage valid.

**Example:**
```python
# app/portfolio/service.py
def execute_trade(db, price_cache: PriceCache, ticker: str, side: str, qty: float):
    price_update = price_cache.get(ticker)
    if price_update is None:
        raise TradeError(f"No live price available for {ticker}")
    fill_price = price_update.price
    ...  # validate cash/shares, write positions + trades rows
```

### Pattern 2: Lifespan-managed singletons, injected via `Depends`

**What:** FastAPI's `lifespan` async context manager is the place to construct long-lived resources (the `PriceCache`, the market data source, the DB connection/pool) once at startup, store them (e.g., on `app.state`), and tear them down at shutdown. Route handlers obtain them via `Depends()` callables that read `request.app.state`, rather than importing module-level globals. *(Confirmed against official FastAPI docs — `contextlib.asynccontextmanager` lifespan + `Depends` is the documented mechanism for exactly this "share a singleton service across routes" need.)*

**When to use:** Wiring `PriceCache`, the DB connection, and the LLM client config into the app once, then reusing them across every request/SSE connection.

**Trade-offs:** Slightly more boilerplate than a bare module-level global, but avoids the "Global Price Cache Instance" anti-pattern already flagged in the codebase's own `ARCHITECTURE.md` (explicit dependency injection over globals), and matches the constructor-injection pattern the market-data layer already established.

**Example:**
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = PriceCache()
    source = create_market_data_source(cache)
    await source.start(default_tickers())
    db_conn = init_db()          # lazy create tables + seed if empty
    app.state.price_cache = cache
    app.state.db = db_conn
    yield
    await source.stop()
    db_conn.close()

app = FastAPI(lifespan=lifespan)
```

### Pattern 3: LLM as a proposer, backend as the sole executor (no direct tool-execution by the model)

**What:** The LLM is called once per chat turn with `response_format` set to a Pydantic schema (`{message, trades[], watchlist_changes[]}` per PLAN.md §9) — a single structured completion, not an iterative tool-calling loop. The backend then walks the parsed `trades`/`watchlist_changes` arrays and calls `portfolio/service.execute_trade()` / `watchlist/service.add_ticker()` for each one, exactly as a manual API call would. Any validation failure (insufficient cash, unknown ticker) is caught and folded back into the chat response text rather than raised to the user as an HTTP error.

**When to use:** Any LLM integration that must "act" on the app's actual state — this bounds the LLM's effect to well-defined, independently-validated operations and avoids duplicating trade-validation logic in two places.

**Trade-offs:** No multi-step agentic reasoning (single completion per turn) — acceptable here because PLAN.md explicitly wants a fast, complete JSON response rather than token streaming or a ReAct-style loop. If the product later needs multi-turn tool use, this same "service functions as the single write path" boundary still holds; only the orchestration around the LLM call would change.

**Example:**
```python
# app/llm/chat.py
async def handle_message(db, price_cache, user_message: str) -> ChatTurnResult:
    context = build_context(db, price_cache)          # portfolio, watchlist, history
    parsed = await call_llm(context, user_message)     # ChatResponse pydantic model
    executed = []
    for trade in parsed.trades:
        try:
            result = execute_trade(db, price_cache, trade.ticker, trade.side, trade.quantity)
            executed.append(result)
        except TradeError as e:
            parsed.message += f"\n(Could not execute {trade.ticker}: {e})"
    for change in parsed.watchlist_changes:
        apply_watchlist_change(db, price_cache, change)
    save_chat_turn(db, user_message, parsed.message, executed)
    return ChatTurnResult(message=parsed.message, actions=executed)
```

## Data Flow

### Manual trade (REST) vs. AI-initiated trade — same downstream path

```
[Trade bar submit] ──POST /api/portfolio/trade──▶ routes/portfolio.py ─┐
                                                                        │
[Chat "buy 10 AAPL"] ──POST /api/chat──▶ routes/chat.py ──▶ llm/chat.py┤
                                                                        ▼
                                                     portfolio/service.execute_trade()
                                                        │ reads PriceCache.get(ticker)
                                                        │ reads/writes db (positions, trades)
                                                        ▼
                                                  portfolio_snapshots row written
                                                        │
                                        ┌───────────────┴───────────────┐
                                        ▼                               ▼
                          GET /api/portfolio (poll/refetch)   next chat response confirms fill
```

### Live price flow (existing, unchanged)

```
GBMSimulator / MassiveDataSource ──▶ PriceCache.update() ──▶ SSE /api/stream/prices ──▶ browser EventSource
                                              │
                                              └─▶ portfolio/service.py reads latest price on trade/valuation
                                              └─▶ llm/chat.py reads latest prices for chat context
```

### Key Data Flows

1. **Trade execution:** Both the manual trade bar and the LLM funnel into one function (`portfolio/service.execute_trade`), which is the only writer of `positions`/`trades`/`portfolio_snapshots`. This guarantees identical validation and P&L math regardless of trigger.
2. **Chat context assembly:** Before each LLM call, `llm/chat.py` reads current state via the DB repository (cash, positions, recent trades) and `PriceCache.get_all()` (live prices for positions + watchlist) to build the prompt — it never queries the LLM for portfolio state, it always injects ground truth.
3. **Frontend consumption:** The Next.js static export talks only to `/api/*` (REST, same-origin) and `/api/stream/prices` (SSE, same-origin) — no separate frontend server, no CORS configuration needed, matching PLAN.md's single-origin rationale.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single user (this project) | Current design (in-memory `PriceCache`, single SQLite file, one FastAPI process) is correct and final — do not add Redis, Postgres, or multi-process serving. |
| Multiple concurrent demo instances (e.g., classroom, each with own container) | No code changes needed — each container already gets its own volume-mounted `db/finally.db` and independent `PriceCache`. |
| Hypothetical future multi-user | `user_id` columns already exist per PLAN.md §7 for this reason, but PriceCache and the LLM chat loop would need real per-session isolation and a proper DB (Postgres) — explicitly out of scope per PROJECT.md. |

### Scaling Priorities

1. **Not a concern for this milestone.** The one real constraint worth respecting: SQLite is single-writer — trade execution, portfolio snapshots (every 30s), and chat message logging all write to the same file, so keep write transactions short and avoid holding the connection open across an LLM network call (build the DB write for a trade as a fast local step, separate from the slower `completion()` call to OpenRouter).
2. **If any future load test shows event-loop stalls,** the first suspect will be a sync `sqlite3` call made directly on the event loop instead of via `asyncio.to_thread()` — same discipline the codebase already applies to `massive_client.py`.

## Anti-Patterns

### Anti-Pattern 1: Re-deriving prices or portfolio math inside the LLM prompt/response

**What people do:** Ask the LLM to compute P&L, average cost, or "current price" and trust its numbers in the response.
**Why it's wrong:** LLM arithmetic is unreliable and creates a second, divergent source of truth from the DB/PriceCache; a wrong number in a "confident" chat response undermines the whole demo.
**Do this instead:** Compute all numbers (cash, P&L, position values) in `portfolio/service.py` / `db/repository.py` and inject them as already-computed context into the prompt; the LLM only reasons over and narrates numbers it's given, and only *proposes* trade tickets (ticker/side/quantity), never dollar amounts to execute.

### Anti-Pattern 2: Giving the LLM direct DB/trade-execution "tool access" without going through the shared service layer

**What people do:** Wire the LLM's structured trade output directly to a raw `INSERT INTO trades` / `UPDATE positions` SQL call inside `llm/chat.py`, separate from whatever the manual REST route does.
**Why it's wrong:** Validation (sufficient cash, sufficient shares, valid ticker) silently diverges between the two paths over time — a classic source of "the AI let me overdraw but the UI wouldn't" bugs.
**Do this instead:** `llm/chat.py` must call the exact same `portfolio/service.execute_trade()` / `watchlist/service.add_ticker()` functions that `routes/portfolio.py` and `routes/watchlist.py` call. One function, two callers.

### Anti-Pattern 3: Mounting the frontend fallback before API routers, or blocking on sync I/O in async routes

**What people do:** Register the static/frontend catch-all route or `StaticFiles` mount before `include_router()` calls, or perform blocking `sqlite3` calls directly inside an `async def` route handler.
**Why it's wrong:** A catch-all mounted first can shadow `/api/*` paths (order matters for older-style catch-all routes, though `app.frontend()` in FastAPI ≥0.138 explicitly checks path operations first regardless of registration order). Sync blocking calls on the event loop stall SSE and every other concurrent request — the same failure mode already documented as an anti-pattern for the market-data layer.
**Do this instead:** `app.include_router(...)` for every API router first, then `app.frontend("/", directory="static")` last (or, on older FastAPI, register the catch-all route last). Wrap all sync SQLite calls in `asyncio.to_thread()`.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| OpenRouter (Cerebras inference) | `litellm.completion(model="openrouter/openai/gpt-oss-120b", response_format=<PydanticModel>, extra_body={"provider": {"order": ["cerebras"]}})` | Per project's `cerebras-inference` skill and PLAN.md §9; requires adding `litellm` + `pydantic` to `backend/pyproject.toml` (pydantic likely already present transitively via FastAPI, but pin it explicitly). `OPENROUTER_API_KEY` already in `.env`. |
| Massive/Polygon.io | Already implemented in `app/market/massive_client.py` — no new integration needed this milestone. | Read-only consumer via `PriceCache`. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `app/market/*` ↔ everything else | Direct Python calls to `PriceCache.get()/get_all()`; `MarketDataSource.add_ticker()/remove_ticker()` from watchlist changes | Treat as a frozen, already-tested library. Do not modify its internals for this milestone; if a needed method is missing, add it to the interface rather than reaching into private state. |
| `db/` ↔ `portfolio/` and `watchlist/` | Repository functions (`get_portfolio_row`, `insert_trade`, `update_position`, etc.), called via `asyncio.to_thread()` | Keep SQL out of `service.py`; keep business rules (cash/shares validation) out of `repository.py`. |
| `portfolio/service.py` / `watchlist/service.py` ↔ `routes/*` and `llm/chat.py` | Plain async function calls, both callers pass the same `db` handle and `price_cache` | This is the seam that guarantees manual and AI-initiated trades behave identically. |
| Frontend (Next.js static export) ↔ backend | Same-origin `/api/*` fetch + `/api/stream/prices` EventSource | No CORS config; frontend build output copied into `backend/static/` (or wherever `app.frontend()`/`StaticFiles` points) by the multi-stage Dockerfile. |

## Suggested Build Order

Given the market-data layer is already complete, the natural dependency order for the remaining work is:

1. **DB layer** (`app/db/`: connection, lazy schema init + seed, repository functions) — everything else depends on this; can be built and unit-tested (pytest, temp SQLite file) with zero dependency on FastAPI routes or the LLM.
2. **Portfolio + watchlist service layer** (`app/portfolio/service.py`, `app/watchlist/service.py`) — depends on DB layer + existing `PriceCache`; this is where trade execution and validation logic lives, and it's the layer most worth getting right first since both REST and LLM will depend on it.
3. **REST routes** (`app/routes/portfolio.py`, `watchlist.py`, plus wiring `create_stream_router` into `main.py`) — thin adapters over step 2; once these exist the API is fully testable via curl/pytest without a frontend.
4. **LLM integration** (`app/llm/`) — depends on steps 1–3 being stable (it reuses the same service functions and needs real portfolio/watchlist data to build context against); build with `LLM_MOCK=true` support from the start so it's testable without burning API calls.
5. **Frontend** (`frontend/` Next.js app) — build last against a working, already-tested API; this lets frontend work start from real endpoint contracts instead of guesses, and matches the general community pattern of building/verifying backend-first, frontend-last for single-container FastAPI+SPA apps.
6. **Docker/deployment** (multi-stage Dockerfile, `app.frontend()`/StaticFiles wiring, start/stop scripts) — last, once both frontend build output and backend are stable; this is where the "single container, single port" contract gets proven end-to-end.

This order lets each layer be verified in isolation (pytest for DB/service/routes, `LLM_MOCK=true` for chat, then Playwright E2E only once everything is wired) before the next layer depends on it — and keeps the frontend team unblocked as soon as step 3 lands, since they can develop against a real running API before step 4/5 are done.

## Sources

- FastAPI official docs — Lifespan events (`contextlib.asynccontextmanager`, startup/shutdown, `app.state`-style singleton sharing) and `Depends()` dependency injection reference — via Context7 (`/websites/fastapi_tiangolo`). MEDIUM confidence (official source, fetched through a documentation aggregator).
- FastAPI official docs — `tutorial/frontend/` (native `app.frontend()`/`router.frontend()` SPA serving, added in FastAPI 0.138.0 / PR #15800) and the corresponding GitHub release page — fetched directly. MEDIUM confidence (official source and changelog, cross-verified across two independent fetches).
- Project's own `cerebras-inference` skill (`.claude/skills/cerebras`) — canonical, project-curated pattern for `litellm.completion()` with `response_format` and Cerebras routing via `extra_body`. HIGH confidence (project-authoritative, not general web research).
- General web search — LLM tool-calling / agent design (LLM as proposer, deterministic backend as sole executor) and typical FastAPI+SQLite+SPA single-container build order. LOW confidence (unverified blog/community sources, directionally consistent across multiple hits but not independently confirmed against a primary source) — treat as generally-accepted practice, not a hard rule.
- `.planning/codebase/ARCHITECTURE.md` and `STRUCTURE.md` — current, ground-truth state of the existing market-data subsystem and empty scaffolding for routes/llm/db.
- `planning/PLAN.md` §3, §6–§9 — existing architectural decisions (SSE over WebSockets, SQLite over Postgres, single container, LLM structured-output/auto-execution contract) treated as fixed constraints, not re-litigated.

---
*Architecture research for: FastAPI + SQLite + Next.js static export single-container trading workstation*
*Researched: 2026-08-01*
