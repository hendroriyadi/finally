<!-- refreshed: 2026-08-01 -->
# Architecture

**Analysis Date:** 2026-08-01

## System Overview

FinAlly's current architecture is centered on a real-time market data streaming subsystem. The backend is structured as a layered FastAPI application with a pluggable market data provider, thread-safe price cache, and SSE streaming for live updates. The frontend and LLM integration layers are under development.

```text
┌─────────────────────────────────────────────────────────┐
│  Frontend Layer (Next.js)                               │
│  `frontend/` — To be implemented                         │
│  Connects via /api/* REST endpoints & /api/stream/prices│
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  API Layer (FastAPI Routes)                             │
│  `backend/app/routes/` — Portfolio, Watchlist, Chat     │
│  Health check endpoint (/api/health)                    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  Business Logic Layer                                   │
│  - LLM Chat Integration: `backend/app/llm/`             │
│  - Portfolio Management (trade execution, P&L)          │
│  - Watchlist Management                                 │
│  - Database Access                                      │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  Real-Time Data Layer (SSE Streaming)                   │
│  `backend/app/market/stream.py` — EventSource endpoint  │
│  Polls price cache every ~500ms, pushes to browser      │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  Price Cache (Thread-Safe In-Memory)                    │
│  `backend/app/market/cache.py` — PriceCache             │
│  Holds latest price, previous price, timestamp per ticker
│  Readers: SSE, Portfolio valuation, Trade execution    │
│  Writers: SimulatorDataSource or MassiveDataSource     │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  Market Data Sources (Pluggable)                        │
│  ┌──────────────────┬──────────────────┐                │
│  │ GBM Simulator    │  Massive REST API│                │
│  │ (default)        │  (real data)     │                │
│  │ Correlated moves │  Polygon.io      │                │
│  │ Events + noise   │  Free tier: 15s  │                │
│  └──────────────────┴──────────────────┘                │
│  `backend/app/market/simulator.py`                      │
│  `backend/app/market/massive_client.py`                │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  Persistence Layer (SQLite)                             │
│  `backend/db/` — Schema, seed data, migrations          │
│  Tables: users_profile, watchlist, positions, trades,   │
│  portfolio_snapshots, chat_messages                     │
└─────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **PriceUpdate** | Immutable dataclass representing a single ticker's price snapshot with computed properties (direction, change %) | `backend/app/market/models.py` |
| **PriceCache** | Thread-safe in-memory store of latest prices; central state for all real-time data | `backend/app/market/cache.py` |
| **MarketDataSource** | Abstract interface for pluggable data providers (Simulator or Massive API) | `backend/app/market/interface.py` |
| **GBMSimulator** | Geometric Brownian Motion price generator with correlated moves across sectors and random events | `backend/app/market/simulator.py` |
| **SimulatorDataSource** | Wraps GBMSimulator as a MarketDataSource; runs background update loop every ~500ms | `backend/app/market/simulator.py` |
| **MassiveDataSource** | Wraps Massive (Polygon.io) REST API as a MarketDataSource; polls on configurable interval (default 15s) | `backend/app/market/massive_client.py` |
| **SSE Router** | FastAPI router factory that creates `/api/stream/prices` endpoint for live price streaming | `backend/app/market/stream.py` |
| **Factory** | Selects between Simulator and Massive based on `MASSIVE_API_KEY` environment variable | `backend/app/market/factory.py` |

## Pattern Overview

**Overall:** Pluggable data source pattern with a thread-safe shared cache and async event streaming.

**Key Characteristics:**
- **Abstraction**: MarketDataSource interface allows switching between simulator and real data without changing downstream code
- **Separation of concerns**: Data generation (simulator/API), caching (PriceCache), and streaming (SSE) are distinct modules
- **Thread safety**: PriceCache uses locks; Massive client runs sync API calls in thread pool
- **Async I/O**: All background tasks are async; event loop-safe throughout
- **Immutability**: PriceUpdate is frozen dataclass for safe concurrent reads

## Layers

**Market Data Source Layer:**
- Purpose: Generate or fetch price updates from external sources (simulator or Massive API)
- Location: `backend/app/market/simulator.py`, `backend/app/market/massive_client.py`
- Contains: GBMSimulator class, SimulatorDataSource class, MassiveDataSource class
- Depends on: PriceCache (writes to it), numpy (simulator only)
- Used by: FastAPI app initialization; receives tick rate from configuration

**Price Cache Layer:**
- Purpose: Single source of truth for latest prices; supports concurrent reads from multiple threads
- Location: `backend/app/market/cache.py`
- Contains: PriceCache class with thread locks
- Depends on: PriceUpdate model, threading.Lock
- Used by: SSE streaming endpoint, portfolio calculations, trade execution logic

**Streaming Layer:**
- Purpose: Push price updates to connected browsers via Server-Sent Events; handles client reconnection
- Location: `backend/app/market/stream.py`
- Contains: SSE endpoint generator (`create_stream_router`)
- Depends on: PriceCache (reads from it), FastAPI/Starlette
- Used by: Frontend browser clients via EventSource

## Data Flow

### Primary Market Data Path

1. **Initialization** (`backend/app/market/factory.py:create_market_data_source`)
   - Factory reads `MASSIVE_API_KEY` environment variable
   - Creates either `SimulatorDataSource` or `MassiveDataSource`
   - Both receive reference to shared `PriceCache`

2. **Simulator Flow** (if MASSIVE_API_KEY not set)
   - `SimulatorDataSource.start(tickers)` initializes `GBMSimulator` with seed prices
   - Simulator seeded with default 10 tickers from `seed_prices.py`
   - Background task (`SimulatorDataSource._run_loop`) calls `GBMSimulator.step()` every 500ms
   - `step()` applies Cholesky-transformed correlated normal draws to each ticker's price
   - ~0.1% chance per ticker per tick of random event (2-5% move)
   - Prices written to `PriceCache.update()` thread-safely

3. **Massive API Flow** (if MASSIVE_API_KEY set)
   - `MassiveDataSource.start(tickers)` sets up Massive REST client
   - Immediate first poll via `_poll_once()`
   - Background task (`MassiveDataSource._poll_loop`) polls every 15s (free tier) or configurable interval
   - Polls `/v2/snapshot/locale/us/markets/stocks/tickers` for all tickers in one call
   - Parses snapshots, extracts `last_trade.price` and `timestamp`
   - Prices written to `PriceCache.update()` thread-safely

4. **SSE Streaming** (`backend/app/market/stream.py`)
   - Browser connects to `GET /api/stream/prices`
   - Stream generator `_generate_events()` sends retry directive (1s)
   - Every 500ms, checks if cache version has incremented
   - If changed, serializes all prices to JSON and yields as SSE event
   - Client receives via EventSource API; `data:` events parsed as JSON

5. **Watchlist + Portfolio Updates**
   - When user adds/removes ticker from watchlist, API calls `MarketDataSource.add_ticker()` / `remove_ticker()`
   - Simulator updates Cholesky decomposition (rebuilds correlation matrix)
   - Massive client adds/removes ticker from polling list
   - Cache is updated immediately with new ticker's seed price

### State Management

- **Price State**: Held in `PriceCache._prices: dict[str, PriceUpdate]`. Thread-safe via Lock.
- **Version Counter**: `PriceCache._version` increments atomically on every update; used by SSE to detect changes.
- **Simulator State**: `GBMSimulator` holds current prices and per-ticker GBM parameters; rebuilt on ticker add/remove.
- **Massive Client State**: `MassiveDataSource` holds active ticker list; updated on add/remove.
- **No global state**: Both sources pass PriceCache reference to avoid globals; factory creates single instance.

## Key Abstractions

**PriceUpdate Dataclass:**
- Purpose: Immutable snapshot of a ticker's price with computed properties
- Frozen (immutable), slotted for efficiency
- Properties: `change`, `change_percent`, `direction` (computed from price/previous_price)
- `to_dict()` method for JSON serialization over SSE
- Located: `backend/app/market/models.py`

**MarketDataSource Interface:**
- Purpose: Contract for pluggable data providers
- Methods: `start(tickers)`, `stop()`, `add_ticker(ticker)`, `remove_ticker(ticker)`, `get_tickers()`
- Allows switching between Simulator and Massive without client code changes
- Located: `backend/app/market/interface.py`

**PriceCache:**
- Purpose: Thread-safe repository of latest prices
- Public API: `update()`, `get()`, `get_all()`, `get_price()`, `remove()`, `version` property
- Readers can safely call `get_all()` and `get_price()` concurrently with writers
- Located: `backend/app/market/cache.py`

## Entry Points

**Market Data Initialization:**
- Location: Backend app startup (to be integrated into main FastAPI app)
- Triggers: Server startup; calls `create_market_data_source(cache)` then `await source.start(default_tickers)`
- Responsibilities: Creates appropriate data source, seeds cache, starts background tasks

**SSE Streaming Endpoint:**
- Location: `backend/app/market/stream.py:create_stream_router()`
- Triggers: Browser connects to `/api/stream/prices`
- Responsibilities: Yields SSE events with all current prices every ~500ms

**GBM Simulator Demo:**
- Location: `backend/market_data_demo.py`
- Triggers: `uv run market_data_demo.py`
- Responsibilities: Runs simulator with live terminal dashboard; demonstrates market data layer in isolation

## Architectural Constraints

- **Threading**: Price updates are asyncio coroutines; PriceCache uses threading.Lock for safety. Simulator runs in single event loop thread; Massive client uses `asyncio.to_thread()` for sync API calls.
- **Global state**: Avoided. PriceCache instance passed to all components that need it. No module-level singletons.
- **Circular imports**: None detected. Imports are unidirectional: models ← cache ← interface ← implementations.
- **Configuration**: Data source selection via environment variables only (`MASSIVE_API_KEY`). All parameters (poll intervals, event probability, volatility) are hardcoded or passed to constructors.
- **Scalability**: Single-user only; SQLite will hold one user profile. Price cache is in-memory; supports concurrent SSE clients without degradation.

## Anti-Patterns

### Global Price Cache Instance

**What happens:** Future code might create PriceCache in module scope or FastAPI Depends instead of explicit dependency injection.

**Why it's wrong:** Makes testing harder (can't isolate cache), and makes circular dependencies more likely.

**Do this instead:** Always pass PriceCache as constructor argument or factory parameter. See `backend/app/market/factory.py:create_market_data_source()` and `backend/app/market/stream.py:create_stream_router()` for correct patterns.

### Mixing Sync and Async in Data Source

**What happens:** Massive client calls sync REST API via `asyncio.to_thread()` which is correct, but if new code adds blocking I/O directly to the event loop without `to_thread()`, it will freeze the entire server.

**Why it's wrong:** Blocks event loop; all other clients (SSE, API requests) hang.

**Do this instead:** Always wrap blocking calls in `asyncio.to_thread()`. See `backend/app/market/massive_client.py:_poll_once()` line 97 for example.

### Assuming Cache Always Has Data

**What happens:** If calling `PriceCache.get(ticker)` without checking for None, code crashes if ticker was never seeded.

**Why it's wrong:** On startup, cache is empty until first market data update. During watchlist changes, new tickers may not have prices immediately.

**Do this instead:** Always check for None. See `backend/app/market/cache.py:get()` return type annotation. Handle missing prices gracefully in downstream code (portfolio calculations, SSE).

## Error Handling

**Strategy:** Graceful degradation with logging.

**Patterns:**

- **Simulator step failure**: Catches all exceptions in `SimulatorDataSource._run_loop()`, logs, and continues to next iteration. SSE clients continue receiving last known prices.

- **Massive API failure**: Logs error in `MassiveDataSource._poll_once()`, does not re-raise, continues polling on next interval. Cache retains last known prices. Common failures (401, 429, network) are expected and handled.

- **SSE client disconnect**: Detected via `request.is_disconnected()` check; stream exits cleanly. No error logged (normal behavior). Browser EventSource API auto-reconnects.

- **Cache update race condition**: Prevented by `threading.Lock` in PriceCache. All updates are atomic; readers never see partial state.

## Cross-Cutting Concerns

**Logging:** Uses Python standard `logging` module. Each module creates logger via `logging.getLogger(__name__)`. Key events logged: data source creation/startup/stop, simulator events, Massive API calls, SSE client connections/disconnections.

**Validation:** Minimal in current implementation. Future portfolio/trade logic will validate: sufficient cash for buys, sufficient shares for sells, valid ticker symbols. Price updates are assumed valid from data sources.

**Configuration:** Environment variables only (`MASSIVE_API_KEY`, potentially `DEBUG` for log level). No config files. Hardcoded defaults for intervals, volatility, event probability.

---

*Architecture analysis: 2026-08-01*
