# Backend — Developer Guide

## Project Setup

```bash
cd backend
uv sync --extra dev   # Install all dependencies including test/lint tools
```

## Market Data API

The market data subsystem lives in `app/market/`. Use these imports:

```python
from app.market import PriceCache, PriceUpdate, MarketDataSource, create_market_data_source
```

### Core Types

- **`PriceUpdate`** — Immutable dataclass: `ticker`, `price`, `previous_price`, `timestamp`, plus properties `change`, `change_percent`, `direction` ("up"/"down"/"flat"), and `to_dict()` for JSON serialization.

- **`PriceCache`** — Thread-safe in-memory store. Key methods:
  - `update(ticker, price, timestamp=None) -> PriceUpdate`
  - `get(ticker) -> PriceUpdate | None`
  - `get_price(ticker) -> float | None`
  - `get_all() -> dict[str, PriceUpdate]`
  - `remove(ticker)`
  - `version` property — monotonic counter, increments on every update (for SSE change detection)

- **`MarketDataSource`** — Abstract interface implemented by `SimulatorDataSource` and `MassiveDataSource`. Lifecycle: `start(tickers)` -> `add_ticker()` / `remove_ticker()` -> `stop()`.

- **`create_market_data_source(cache)`** — Factory. Returns `MassiveDataSource` if `MASSIVE_API_KEY` is set, otherwise `SimulatorDataSource`.

### SSE Streaming

```python
from app.market import create_stream_router

router = create_stream_router(price_cache)  # Returns FastAPI APIRouter
# Endpoint: GET /api/stream/prices (text/event-stream)
```

### Seed Data

Default tickers: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX. Seed prices and per-ticker volatility/drift params are in `app/market/seed_prices.py`.

## Running Tests

```bash
uv run --extra dev pytest -v                 # All tests
uv run --extra dev pytest --cov=app --cov=db # With coverage
uv run --extra dev ruff check app/ db/ tests/ # Lint
```

## Demo

```bash
uv run market_data_demo.py   # Live terminal dashboard with simulated prices
```

## Database API

The persistence layer lives in `backend/db/` — a top-level package, sibling to `app/`.
It is **pure CRUD: no business rules.** Nothing here checks for sufficient cash or
shares, recomputes average cost, or rejects a negative balance — that validation
belongs in the API/LLM layers.

```python
import db
from db import get_profile, list_positions, insert_trade, transaction
```

### Lifecycle

The database file is created and seeded **lazily** on the first repository call —
no startup hook required. The path resolves two levels above the `db` package, i.e.
`<repo root>/db/finally.db` locally and `/app/db/finally.db` in the container (which
copies `backend/` to `/app/backend/`) — the volume mount target either way. Override
with the `FINALLY_DB_PATH` environment variable if that layout ever changes.

- `init_db(path=None) -> Path` — create missing tables, seed if empty. Idempotent:
  never drops tables, never re-seeds once a profile row exists.
- `ensure_initialized(path=None) -> Path` — `init_db` memoized per path per process.
- `reset_initialization_cache()` — forget memoized paths (tests only).
- `get_db_path() -> Path`, `connect(path=None) -> sqlite3.Connection` (raw, WAL + FK on).

### Connections and transactions

Every repository function accepts an optional keyword-only `conn`. Pass nothing and
it opens/commits its own short-lived connection. Pass one from `transaction()` to
make several writes atomic (all-or-nothing, rolls back on exception):

```python
with transaction() as conn:
    adjust_cash_balance(-cost, conn=conn)
    upsert_position("AAPL", new_qty, new_avg_cost, conn=conn)
    insert_trade("AAPL", "buy", qty, price, conn=conn)
```

Functions are **synchronous**. Connections are short-lived, WAL-mode, and local, so
calling them directly from `async def` FastAPI handlers is fine; wrap in
`asyncio.to_thread(...)` if you prefer strictness.

- `get_connection()` — context manager, connection without auto-commit.
- `transaction()` — context manager, commits on success / rolls back on error.
- `use_connection(conn)` — internal helper implementing the optional-`conn` pattern.

### Models

Frozen dataclasses, each with `from_row(sqlite3.Row)` and `to_dict()`:
`UserProfile`, `WatchlistEntry`, `Position`, `Trade`, `PortfolioSnapshot`, `ChatMessage`.
Helpers: `utc_now_iso()`, `new_id()` (UUID4), `normalize_ticker()` (strip + uppercase),
`DEFAULT_USER_ID` (`"default"`), `DEFAULT_CASH_BALANCE` (10000.0), `DEFAULT_TICKERS`.

All functions below take `user_id: str = DEFAULT_USER_ID` and `*, conn=None`
(omitted from the signatures for brevity).

### Profile — `db/profile_repo.py`

| Function | Returns |
|---|---|
| `get_profile()` | `UserProfile \| None` |
| `create_profile(user_id, cash_balance=10000.0)` | `UserProfile` — idempotent |
| `set_cash_balance(cash_balance)` | `UserProfile \| None` — overwrite |
| `adjust_cash_balance(delta)` | `UserProfile \| None` — `cash_balance += delta` in one statement; **allows going negative** |

### Watchlist — `db/watchlist_repo.py`

| Function | Returns |
|---|---|
| `list_watchlist()` | `list[WatchlistEntry]`, oldest first |
| `list_watchlist_tickers()` | `list[str]` |
| `is_watching(ticker)` | `bool` |
| `add_watchlist_ticker(ticker)` | `WatchlistEntry` — idempotent; returns the existing row on duplicate (call `is_watching` first if you need to return 409) |
| `remove_watchlist_ticker(ticker)` | `bool` — True if a row was deleted |

### Positions — `db/positions_repo.py`

| Function | Returns |
|---|---|
| `list_positions()` | `list[Position]`, alphabetical by ticker |
| `get_position(ticker)` | `Position \| None` |
| `upsert_position(ticker, quantity, avg_cost)` | `Position` — writes **absolute** values; you compute the new qty/avg_cost |
| `delete_position(ticker)` | `bool` — use when a position is fully sold |

### Trades — `db/trades_repo.py`

| Function | Returns |
|---|---|
| `insert_trade(ticker, side, quantity, price, *, executed_at=None)` | `Trade` — `side` must be `"buy"` or `"sell"` (CHECK constraint) |
| `list_trades(*, ticker=None, limit=None)` | `list[Trade]`, most recent first |
| `count_trades()` | `int` |

### Portfolio snapshots — `db/snapshots_repo.py`

| Function | Returns |
|---|---|
| `insert_snapshot(total_value, *, recorded_at=None)` | `PortfolioSnapshot` |
| `list_snapshots(*, since=None, limit=None)` | `list[PortfolioSnapshot]` chronological (`limit` keeps the most recent N, still oldest-first — chart-ready) |
| `latest_snapshot()` | `PortfolioSnapshot \| None` |

### Chat — `db/chat_repo.py`

| Function | Returns |
|---|---|
| `insert_chat_message(role, content, actions=None, *, created_at=None)` | `ChatMessage` — `role` is `"user"` or `"assistant"`; `actions` is any JSON-serializable Python object, serialized for you |
| `list_chat_messages(*, limit=None)` | `list[ChatMessage]` oldest-first (`limit` keeps the most recent N — use for prompt history) |
| `clear_chat_messages()` | `int` rows deleted |

`ChatMessage.actions` comes back already parsed (list/dict/None) — do not `json.loads` it.

## LLM Chat API

The chat assistant lives in `app/llm/`. Wiring it up is one line:

```python
from app.llm import chat_router

app.include_router(chat_router)   # serves POST /api/chat, prefix included
```

`POST /api/chat` takes `{"message": "..."}` and returns
`{"message": str, "trades": [ActionResult], "watchlist_changes": [ActionResult]}`.
Any action in those lists has **already been executed** by the time the response
returns. `ActionResult` carries `success` and, on failure, a human-readable
`error`; failures are also appended to `message` as a `Note: ...` sentence so the
user sees them and the next turn's history carries them back to the model.

### Modules

| File | Role |
|---|---|
| `schema.py` | Pydantic models — `AssistantResponse` (structured output), `ActionResult`, `ChatRequest`/`ChatResponse` |
| `prompt.py` | `SYSTEM_PROMPT`, `format_context()`, `build_messages()` |
| `client.py` | LiteLLM -> OpenRouter -> Cerebras call; `parse_response()` never raises |
| `mock.py` | Deterministic canned replies for `LLM_MOCK=true` |
| `service.py` | `handle_chat()` — context, call, auto-execution, persistence |
| `router.py` | The FastAPI router |

### Behavior

- Model `openrouter/openai/gpt-oss-120b`, Cerebras provider, structured output via
  `response_format=AssistantResponse`. The blocking call runs in `asyncio.to_thread`
  so it never stalls the SSE stream.
- Nothing in this package raises for bad model output, transport errors, a missing
  `OPENROUTER_API_KEY`, or a rejected trade — every path returns a `ChatResponse`.
- Auto-execution reuses `app.portfolio.execute_trade` and `app.watchlist_service`;
  there is no second implementation of trade validation here. **Watchlist changes
  are applied before trades** so "add SNOW and buy 5" works in one turn.
- Prompt history is the last `HISTORY_LIMIT` (20) messages, oldest-first.

### LLM_MOCK

`LLM_MOCK=true` skips the API entirely. Triggers, first match wins, case-insensitive:

| Message contains | Result |
|---|---|
| `watchlist` | watchlist change — `remove`/`drop` means remove, otherwise add |
| `buy` or `sell` | a trade on that side |
| anything else | plain portfolio summary, no actions |

Ticker = first ALL-CAPS 1-5 letter token (pronouns like `I`/`A` ignored), defaulting
to `AAPL` for trades and `PYPL` for watchlist changes. Quantity = first number in
the message, default `1`. So `"Buy 5 shares of AAPL"` buys 5 AAPL and
`"Add PYPL to my watchlist"` watches PYPL.

## REST API and app assembly

`app/main.py` builds the FastAPI app (`uvicorn app.main:app`). `create_app()` mounts,
in order: the REST routers, the SSE stream router, the chat router, and finally the
static frontend at `/` — last so it never shadows `/api/*`.

The lifespan starts the market data source with the watchlist tickers, registers it in
`app/state.py` (and on `app.state` for convenience), seeds one portfolio snapshot so the
P&L chart is never empty, and runs a 30-second snapshot loop. `TestClient(create_app())` without a `with`
block skips the lifespan, so tests never start a simulator.

`load_dotenv(<repo root>/.env)` runs at import. Real environment variables win, so
Docker's `--env-file` is unaffected.

### Shared runtime — `app/state.py`

`price_cache` is a module-level `PriceCache` singleton; every consumer reads the same
prices without injection. The `MarketDataSource` is registered by the lifespan and is
absent (None) in tests and scripts.

| Function | Purpose |
|---|---|
| `get_price_cache()` | The shared cache |
| `get_market_source()` | Running source, or None when the app is not started |
| `set_market_source(source)` | Lifespan registration (tests use it to inject a fake) |
| `reset_prices()` | Empty the cache — tests only |

### Business logic — `app/portfolio.py`

**Routes and the LLM chat flow both call these**, so "buy N shares of X" has one
implementation. Plain functions, no FastAPI types. All take `user_id` positionally
plus keyword-only `price_cache=None` (defaults to the shared cache; for tests).

| Function | Returns |
|---|---|
| `compute_portfolio(user_id, *, price_cache, conn)` | `PortfolioValuation` — cash, positions marked to market, totals, unrealized P&L |
| `total_portfolio_value(...)` | `float` |
| `execute_trade(ticker, side, quantity, user_id, *, price_cache)` | `TradeResult` |
| `record_snapshot(...)` | `PortfolioSnapshot` — appends to the P&L series |
| `list_watchlist(...)` | `list[WatchlistItem]` — entries joined with cached prices |

Every dataclass has `to_dict()`. Notes:

- **`execute_trade` never raises on validation failure** — it returns
  `TradeResult(success=False, reason=..., error_code=...)`. `reason` is a finished
  sentence written for the user; the chat flow relays it verbatim. `error_code` is one
  of `invalid_ticker`, `invalid_side`, `invalid_quantity`, `no_price`,
  `insufficient_cash`, `insufficient_shares` (constants on `TradeError`).
- **The fill price comes from the PriceCache, not the caller.** A ticker with no cached
  price cannot be traded (`no_price`) — it must be on the watchlist first.
- Cash, position, trade log and snapshot are written in one `db.transaction()`.
- Buy averages the cost `(old_qty*old_avg + qty*price) / new_qty`; sell leaves `avg_cost`
  alone and deletes the position once the quantity reaches zero.
- A position whose ticker has no cached price is valued at its average cost, so it shows
  its cost basis and zero P&L rather than disappearing.

### Watchlist mutations — `app/watchlist_service.py`

Writing to the database is not enough: a ticker the running `MarketDataSource` does not
track never produces a price. Always go through these.

| Function | Returns |
|---|---|
| `await add_ticker(ticker, user_id, *, price_cache)` | `(WatchlistItem, newly_added: bool)` |
| `await remove_ticker(ticker, user_id)` | `bool` — False if it was not watched |
| `validate_ticker(ticker)` | Normalized symbol; raises `ValueError` if malformed |

### Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | Touches the database (which lazily creates and seeds it); 503 if unreachable |
| GET | `/api/portfolio` | Positions, cash, total value, unrealized P&L |
| POST | `/api/portfolio/trade` | `{ticker, quantity, side}`; 400 with `detail.reason` + `detail.error_code` on validation failure, 422 on a malformed body |
| GET | `/api/portfolio/history` | Snapshots oldest-first; optional `?limit=N` keeps the most recent N |
| GET | `/api/watchlist` | Tickers joined with live prices |
| POST | `/api/watchlist` | `{ticker}`; **201** when added, **200** when already watched, 400 if malformed |
| DELETE | `/api/watchlist/{ticker}` | 404 if not watched |

See "API errata" at the end of this file for the exact wire shapes (SSE frame layout,
`_percent` spelling, epoch-float vs ISO timestamps, `side` vs `action`).

### Static frontend

`FINALLY_STATIC_DIR` (set to `/app/backend/static` in the container) wins; otherwise
`backend/static/` then `frontend/out/`. A missing directory is logged and skipped, so the
API runs before the frontend is built.

## API errata — actual wire shapes vs PLAN.md section 8

PLAN.md describes the endpoints at a level that leaves several shapes ambiguous, and
the live API resolves them as follows. **These are the authoritative shapes** — all
verified against a running server, not inferred. `frontend/src/lib/normalize.ts` already
adapts to them.

**1. SSE frames are a ticker-keyed map, one frame per tick cycle — not one event per
ticker.** `GET /api/stream/prices` emits every tracked ticker in a single `data:` line
roughly every 500ms:

```
retry: 1000

data: {"AAPL": {"ticker":"AAPL","price":189.98,"previous_price":190.0,
                "timestamp":1785514403.67,"change":-0.02,"change_percent":-0.0105,
                "direction":"down"}, "GOOGL": {...}, ...}
```

Consumers should iterate the object's values, not treat the frame as a single tick.

**2. Percent fields are spelled `_percent`, never `_pct`:** `change_percent` (price
ticks, watchlist items) and `unrealized_pnl_percent` (positions, portfolio totals).

**3. Two different time formats, deliberately, because they come from different layers:**

| Field | Format | Source |
|---|---|---|
| `timestamp` (price ticks, watchlist items) | float, epoch **seconds** | market layer, `time.time()` |
| `recorded_at` (portfolio history), `added_at`, `executed_at`, `created_at` | ISO-8601 string | database layer, `utc_now_iso()` |

Anything originating in `app/market/` is an epoch float; anything read out of SQLite is
an ISO string. Convert accordingly.

**4. `side` vs `action` is a deliberate envelope difference, not naming drift.** Anywhere
a trade is *specified*, the field is `side` ("buy"/"sell") — `POST /api/portfolio/trade`,
`TradeResult`, and the LLM's `TradeInstruction`. `action` appears only in
`ActionResult`, the single envelope `POST /api/chat` uses to echo back **both** kinds of
executed action; there `kind` is "trade" or "watchlist" and `action` is the verb for that
kind ("buy"/"sell" or "add"/"remove"). One result type covering both is why the field
can't just be called `side`.

**5. Trade validation errors put an object in `detail`, not a string.** `POST
/api/portfolio/trade` returns 400 with the full `TradeResult` under `detail` — render
`detail.reason` (a finished sentence) and branch on `detail.error_code`. A malformed body
is still a normal FastAPI 422 with a string-ish `detail`.

**5b. A trade the LLM asked for never produces a 400 — `POST /api/chat` is always 200.**
The two paths report the same failure differently, so don't branch on status code for
chat. The identical `TradeResult.reason` string arrives as `trades[i].error` alongside
`trades[i].success === false`, and is also appended to the top-level `message` as a
`Note: ...` sentence (`app/llm/service.py`). A rejected LLM trade is therefore fully
renderable from the 200 body alone.

**6. `change_percent` is tick-over-tick, not daily.** There is no session-open reference
price anywhere in the market layer, so a true "daily change %" cannot be served. The
frontend computes change-since-page-load from its own SSE buffer instead. Adding a real
daily figure means storing a session-open price in `app/market/`.

### Do not add GZipMiddleware without excluding the SSE route

Compression middleware buffers the response body, so applying it to
`/api/stream/prices` stops ticks from ever reaching the browser — the stream appears to
connect and then hang. If compression is ever added, exclude that path explicitly.

### Importing litellm calls `load_dotenv()`

`import litellm` loads the repo-root `.env` into `os.environ` as a side effect, and
`app/llm/client.py` imports it **lazily inside `complete()`**. So a test that does
`monkeypatch.delenv("LLM_MOCK")` can have that value silently restored mid-test, the
moment the code under test first reaches the import — a test asking for the real LLM
path would quietly get mock replies instead.

The root `tests/conftest.py` defuses this with a session-scoped autouse fixture that
imports litellm before any fixture runs, so the side effect happens once, up front, and
the cached import can't re-trigger it. Keep that fixture. This is invisible until a
`.env` actually exists, which is why it appeared only after one was created.

`app/main.py` also calls `load_dotenv()` deliberately at import; that one is intentional
and harmless (real environment variables always win, so Docker's `--env-file` is
unaffected).

**The lazy import is deliberate, and it moves a cost rather than removing it.** Keeping
it inside `complete()` means startup and `LLM_MOCK=true` runs never pay litellm's
multi-second import. The bill instead lands on the **first real (non-mock) chat request
of each process**, which will feel slow exactly once. It runs inside `asyncio.to_thread`,
so it does not stall the SSE stream. If a smoke test sees a slow first chat, that is this
import warming up — not a hung request. Moving the import to module scope would trade it
for slower startup on every run, including mock-mode ones, which is the worse deal while
mock is the default.
