# Codebase Concerns

**Analysis Date:** 2026-08-01

## Project Completion Status

**Critical:** This project is in very early stages — only the market data subsystem is complete. Major components are not yet implemented, creating significant architectural and integration risks.

**Completion Snapshot:**
- Market data layer: ✅ Complete (73 tests passing)
- FastAPI application: ❌ Not started (no `main.py`, `app.py`, or route handlers)
- Database layer: ❌ Not started (`backend/db/` empty)
- LLM integration: ❌ Not started (`backend/app/llm/` and `backend/app/routes/` empty)
- Frontend: ❌ Not started (`frontend/` directory empty)
- Docker & deployment: ❌ Not started (no Dockerfile, no scripts)

---

## Tech Debt

### Missing Core Backend Infrastructure

**Issue:** The FastAPI application skeleton does not exist. No entry point, no middleware, no route initialization.

**Files:** 
- `backend/app/` - core initialization missing
- No `backend/main.py` or `backend/app/server.py`

**Impact:** 
- Cannot run the backend at all
- No API endpoints available (all routes in `backend/app/routes/` are missing)
- Portfolio, trade, watchlist, and chat endpoints completely unimplemented

**Fix approach:**
- Create `backend/main.py` with FastAPI app initialization
- Set up CORS middleware (needed for frontend integration)
- Inject `PriceCache` and data sources into the app lifecycle
- Mount the market data streaming router
- Add remaining route modules (portfolio, watchlist, chat, health check)

### Missing Database Layer

**Issue:** Database schema, initialization, and ORM integration are completely absent. The PLAN.md specifies a SQLite schema with 6 tables (`users_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages`), but none are implemented.

**Files:** `backend/db/` is empty

**Impact:**
- Portfolio state cannot be persisted
- Trade history cannot be tracked
- Chat conversation history is lost on restart
- Watchlist changes are not saved
- P&L snapshots cannot be recorded

**Fix approach:**
- Create schema initialization SQL in `backend/db/schema.sql`
- Implement database connection and lazy initialization (PLAN.md requirement)
- Choose ORM: consider SQLAlchemy, Tortoise-ORM, or sqlite3 directly with migrations
- Implement database models matching PLAN.md schema
- Add schema versioning and migration strategy
- Test database initialization edge cases (missing file, corrupted file, schema version mismatch)

### Missing Dependencies in pyproject.toml

**Issue:** Critical Python packages required by the PLAN.md are not declared in `backend/pyproject.toml`.

**Files:** `backend/pyproject.toml` lines 7-13

**Current dependencies:**
```
fastapi, uvicorn, numpy, massive, rich
```

**Missing for planned features:**
- `litellm` — LLM API abstraction layer (required for OpenRouter integration via Cerebras)
- `pydantic` — Data validation (recommended for FastAPI, needed for structured outputs)
- `sqlalchemy` or similar ORM — Database abstraction (or `sqlite3` with custom query layer)
- `pydantic-core` or `jsonschema` — Structured output validation for LLM responses
- `python-dotenv` — Environment variable loading from `.env` file
- `aiosqlite` — Async SQLite driver (if using SQLAlchemy with async)

**Impact:**
- LLM chat integration cannot be implemented without `litellm`
- Request validation will fail without pydantic
- Database queries must be written in raw SQL or custom wrapper
- `.env` file loading must be implemented manually

**Fix approach:**
- Add LLM dependencies: `litellm>=1.0.0, pydantic>=2.0.0`
- Add database dependencies: `sqlalchemy>=2.0.0, aiosqlite>=0.19.0` (or choose ORM)
- Add utilities: `python-dotenv>=1.0.0`
- Consider security libraries: `python-jose, passlib, cryptography` (for future multi-user auth)
- Update lockfile with `uv sync`

---

## Known Bugs

### Massive API Error Handling Is Silent

**Bug:** When the Massive API polling fails (401 auth error, 429 rate limit, network timeout), the error is logged but the loop continues silently. Clients receive stale cached prices indefinitely without indication.

**Symptoms:** 
- User's "real" market data freezes if API key is invalid or rate-limited
- No error message or reconnection indicator
- SSE client has no way to detect data staleness

**Files:** `backend/app/market/massive_client.py` lines 118-121

**Code:**
```python
except Exception as e:
    logger.error("Massive poll failed: %s", e)
    # Don't re-raise — the loop will retry on the next interval.
```

**Trigger:** 
1. Set `MASSIVE_API_KEY` to an invalid key
2. Start the app
3. Observe API errors in logs but prices never update

**Workaround:** Currently none — user must restart the app with a valid key

**Fix approach:**
- Implement a circuit breaker: after N consecutive failures, switch to simulator or degrade gracefully
- Add a "data_quality" field to `PriceCache` (e.g., `{ticker: "stale", "error", "fresh"}`)
- Expose data quality in SSE events
- Add frontend indicator when data is stale or missing

---

## Security Considerations

### No Authentication or Authorization

**Risk:** The entire system has no login, no multi-user support, no access control. The PLAN.md specifies single-user ("default" hardcoded user ID), but this is a deployment liability.

**Files:** 
- All database queries hardcode `user_id = "default"`
- `backend/app/market/cache.py` has no user context
- No middleware to validate requests or establish identity

**Current mitigation:** 
- Documented as single-user in PLAN.md
- Expected only for course demo environment

**Recommendations:**
- For production, implement authentication before exposing to networks
- Consider adding a `user_context` middleware that extracts user from JWT token
- Add per-user portfolio isolation in all database queries
- Consider rate limiting per user
- Future: implement multi-tenant data isolation

### LLM Trade Execution Authority

**Risk:** The LLM chat assistant can execute trades automatically without user confirmation. While intentional for the course demo ("agentic AI capabilities"), this is dangerous in any real system.

**Files:** `backend/app/llm/` (not yet implemented, but specified in PLAN.md)

**Current mitigation:**
- Documented in PLAN.md as intentional design choice for educational purposes
- Running against simulated portfolio with fake money

**Recommendations:**
- Add a "dry_run" mode to show trades without executing
- Add configurable trade limits (max order size, max daily losses)
- Log all AI-initiated trades for audit trail
- Consider requiring user confirmation for trades above a threshold
- For production: disable auto-execution entirely, require explicit user approval

### Environment Variables Not Validated

**Risk:** API keys and configuration are loaded from environment variables with no validation. Invalid keys fail silently (see Massive API bug above).

**Files:** `backend/app/market/factory.py` lines 24

**Current state:**
- `MASSIVE_API_KEY` checked for emptiness only
- `OPENROUTER_API_KEY` not yet loaded (LLM integration not started)
- No validation that keys are valid before use

**Recommendations:**
- Add startup validation: attempt a test API call for each key
- Provide clear error messages if keys are missing or invalid
- Consider key rotation strategy for production
- Log all API key usage attempts (without logging the key itself)

### Credentials in .env File

**Risk:** Database credentials, API keys, and secrets stored in `.env` file could be accidentally committed.

**Current mitigation:** `.env` is in `.gitignore` (not in version control)

**Observations:** `.env.example` not found — no template for developers

**Recommendations:**
- Create `.env.example` with all required variables and placeholder values
- Commit `.env.example` to version control (with dummy values)
- Document required environment variables in README
- Consider using `.env.local` for local overrides

---

## Performance Bottlenecks

### SSE Broadcasts All Tickers Every 500ms Regardless of Changes

**Problem:** The SSE streaming endpoint (`backend/app/market/stream.py` lines 75-83) sends all ticker prices to all clients every 500ms, even if prices haven't changed.

**Files:** `backend/app/market/stream.py` lines 75-83

**Code:**
```python
current_version = price_cache.version
if current_version != last_version:
    last_version = current_version
    prices = price_cache.get_all()  # ALL tickers, every update
```

**Impact with 1000s of tickers:**
- Bandwidth: sending 10,000+ JSON bytes per second per client
- CPU: serializing thousands of objects every 500ms
- Network: potential congestion if many clients connected

**Improvement path:**
- Send only changed tickers: `_generate_events` should track per-ticker versions
- Implement ticker-level granularity in `PriceCache`
- For now (single-user): acceptable, but document as limitation for scaling

### Massive API Polling Interval Is Too Coarse

**Problem:** Free tier polls every 15 seconds (PLAN.md), paid tiers every 2-15s. This creates 2-15 second staleness in portfolio valuations and trade opportunities.

**Files:** `backend/app/market/massive_client.py` line 32, default `poll_interval=15.0`

**Current behavior:** Prices are 15 seconds stale on average

**Improvement path:**
- Detect actual tier automatically using API response headers
- Make polling interval configurable at runtime (e.g., via query parameter)
- Document staleness guarantee in API docs
- Consider hybrid: simulator for "known" tickers, Massive for added tickers (reduces API load)

---

## Fragile Areas

### Market Data Source Transition (Simulator → Massive or Vice Versa)

**Files:** `backend/app/market/factory.py`

**Why fragile:** No mechanism to switch data sources at runtime. If `MASSIVE_API_KEY` is set at startup but becomes invalid later, or if the user wants to toggle between simulator and real data, the app must restart.

**Safe modification:**
- Create a "data source manager" that can hot-swap sources
- Add health checks that can detect source failures and fall back to simulator
- Test the transition: ensure price history is preserved, no gaps in `portfolio_snapshots`

**Test coverage gap:**
- No tests for switching sources mid-stream
- No tests for data source failure recovery

### Concurrent Updates to PriceCache from Multiple Sources

**Files:** `backend/app/market/cache.py`

**Why fragile:** The cache uses a simple `Lock()` for thread safety, but the multi-threaded Massive client and async simulator might have race conditions if both run (which shouldn't happen, but the code doesn't prevent it).

**Safe modification:**
- Enforce single-source invariant at the application level (exactly one `start(tickers)` call)
- Add assertions to catch accidental dual-source setup
- Consider replacing `Lock()` with `asyncio.Lock()` if moving to pure async

**Test coverage gap:**
- No stress tests with concurrent updates
- No tests for rapid add/remove ticker operations

### Untested Lazy Database Initialization

**Files:** Database layer not yet implemented, but specified as lazy in PLAN.md

**Why fragile:** The app is supposed to create the SQLite database and schema on first request. Edge cases:
- Race condition: two requests hit at the same time, both try to initialize schema
- Corrupted file: migration fails midway, database left in inconsistent state
- Missing write permissions: app fails to create `db/finally.db` silently
- Disk full: partial schema written, app hangs retrying

**Safe modification:**
- Use a lock file to serialize initialization
- Implement atomic schema creation (all or nothing)
- Test with read-only filesystem, missing `/db` directory, corrupted SQLite files

---

## Scaling Limits

### Single SQLite Database File, No Sharding

**Current capacity:** SQLite handles ~10GB databases easily, reads/writes up to ~1000 req/sec on typical hardware.

**Limit:** Single user, single file. When implemented, hitting this limit would require migrating to PostgreSQL or similar.

**Scaling path:**
- For <100 concurrent users: SQLite is fine, just add connection pooling
- For 100-1000 users: migrate to PostgreSQL
- For 1000+ users: add sharding by portfolio
- Document the scaling assumptions

### Price Cache Stored in Memory, Not Persistent

**Files:** `backend/app/market/cache.py`

**Limit:** All price history is lost on app restart. Portfolio snapshots are in the database, but transient prices are not.

**Impact:** P&L chart gaps on app restart

**Scaling path:**
- Consider Redis for distributed cache (enables multi-instance deployment)
- Or store prices in SQLite (trades off speed for persistence)
- Current design is fine for single-instance deployments

---

## Dependencies at Risk

### `massive` Package Coupling

**Risk:** The `massive` package (Polygon.io REST client) is a hard dependency. If the package breaks or Polygon changes the API, the real market data source fails.

**Mitigation:**
- Written tests for `MassiveDataSource` (13 tests in `backend/tests/market/test_massive.py`)
- Tests mock the `massive` client, so actual API changes won't be caught until production

**Migration plan:** 
- If Polygon.io becomes unavailable or expensive, implement alternative (e.g., `yfinance` for real data, or pure simulator)
- Interface abstraction (MarketDataSource ABC) makes this swap easy

### LiteLLM Version Coupling (When Implemented)

**Risk:** LiteLLM API changes between versions. When implemented, must pin version to avoid breaking changes.

**Current state:** Not yet in `pyproject.toml`

**Recommendation:** When adding LiteLLM, pin to a specific version or narrow range (e.g., `litellm>=1.0.0,<2.0.0`)

---

## Missing Critical Features

### No Trade Execution Logic

**Problem:** Portfolio endpoints not implemented yet. No way to execute buy/sell orders, calculate P&L, or manage cash balance.

**Files:** `backend/app/routes/` is empty, `backend/db/` has no portfolio models

**Blocks:**
- Portfolio visualization (heatmap, P&L chart)
- Watchlist management
- Trade execution from chat

**Implementation plan:**
- Create `backend/db/models.py` with SQLAlchemy models for trades, positions, portfolio snapshots
- Implement `backend/app/routes/portfolio.py` with `/api/portfolio`, `/api/portfolio/trade`, `/api/portfolio/history` endpoints
- Add trade validation logic (sufficient cash for buys, sufficient shares for sells)
- Atomic transaction handling for trade + portfolio snapshot

### No Watchlist Endpoints

**Problem:** Watchlist CRUD endpoints missing.

**Files:** `backend/app/routes/` is empty

**Blocks:**
- User cannot add/remove tickers
- AI cannot modify watchlist

**Implementation plan:**
- Implement `GET /api/watchlist`, `POST /api/watchlist`, `DELETE /api/watchlist/{ticker}`
- Coordinate with market data source (add/remove from cache and simulator/Massive)

### No Chat Integration

**Problem:** LLM integration completely missing. No message storage, no structured output parsing, no trade auto-execution.

**Files:** `backend/app/llm/` is empty, `backend/app/routes/` is empty, `backend/pyproject.toml` missing `litellm`

**Blocks:**
- Core feature of the application
- User cannot interact with AI assistant

**Implementation plan:**
- Add `litellm>=1.0.0` to dependencies
- Implement `backend/app/llm/client.py` with OpenRouter integration
- Implement structured output parsing (use Pydantic models for schema)
- Implement `backend/app/routes/chat.py` with `POST /api/chat` endpoint
- Add message storage to database

---

## Test Coverage Gaps

### No Database Integration Tests

**Status:** Database layer not yet implemented

**Risk:** Once database is built, critical business logic (trade execution, P&L calculation, portfolio valuation) will have no test coverage.

**Priority:** High — implement integration tests before deploying to production

**Test scenarios needed:**
- Trade execution with sufficient/insufficient cash
- Selling more shares than owned (should fail)
- Multiple trades on same ticker (avg_cost calculation)
- Portfolio snapshot recording
- Atomic transaction handling

### No API Endpoint Tests

**Status:** No tests for FastAPI route handlers

**Risk:** Endpoint logic untested until E2E tests run

**Priority:** High — unit tests faster to run and easier to debug

**Test scenarios needed:**
- GET `/api/portfolio` returns correct format
- POST `/api/portfolio/trade` validates inputs and executes
- GET `/api/watchlist` returns current tickers with prices
- POST `/api/chat` parses LLM response and executes trades
- Error cases: invalid inputs, insufficient funds, API failures

### No E2E Tests Yet

**Status:** `test/` directory has infrastructure but no tests

**Risk:** Full user workflows untested until manual testing

**Priority:** High — required before release

**Test scenarios needed:**
- Fresh start: default watchlist appears, streaming prices flow
- Buy shares: cash decreases, position appears, portfolio updates
- Chat: send message, AI responds, trade executes
- Reconnection: disconnect SSE and verify auto-reconnect
- Persistence: restart app, data still there

### No Frontend Component Tests

**Status:** Frontend directory empty

**Risk:** UI untested

**Priority:** Medium (lower than backend)

**When building frontend, add:**
- Component tests for watchlist, portfolio heatmap, P&L chart, chat panel
- Integration tests for price flash animations, loading states
- Accessibility tests for terminal UI

### Market Data Test Coverage Gaps

**Files:** `backend/tests/market/`

**Coverage:** 84% overall, gaps in:
- `MassiveDataSource` at 56% (API methods mocked, not real integration tested)
- Edge cases: what if cache is updated while iterating?
- What if ticker is added then immediately removed?
- Cholesky decomposition numeric stability with many tickers

**Recommendations:**
- Add optional integration tests that hit real (or mocked-at-network-level) Massive API
- Stress tests for rapid ticker churn
- Numeric stability tests for correlation matrix with >100 tickers

---

## Deployment & Infrastructure

### No Docker Container

**Status:** No Dockerfile, no `docker-compose.yml`

**Risk:** 
- Users cannot run the app without manually installing Python, Node, dependencies
- "It works on my machine" problem

**Impact:** Deployment blocked

**Fix approach:**
- Create `Dockerfile` with multi-stage build (Node 20 → Python 3.12)
- Build frontend in stage 1, Python backend in stage 2
- Mount SQLite database volume
- Environment variable injection for keys
- Test Docker build in CI

### No Start/Stop Scripts

**Status:** `scripts/start_mac.sh`, `scripts/start_windows.ps1` etc. not implemented

**Risk:** Users don't know how to run the app

**Fix approach:**
- Implement `scripts/start_mac.sh` with Docker build & run, browser auto-open
- Implement `scripts/stop_mac.sh` with container stop (preserving volume)
- Add PowerShell equivalents for Windows
- Test idempotency: running start twice should not error

### No Database Migration Strategy

**Status:** Lazy initialization assumes schema is always correct

**Risk:** 
- How do you add a column to a table in production?
- Rolling back bad schema changes?
- Multi-instance deployment: race condition on schema creation

**Fix approach:**
- Implement schema versioning (e.g., `schema_version` table)
- Use migration library like Alembic (SQLAlchemy) or Flyway
- Migrations run automatically on app startup
- Test with old database files: app should upgrade schema safely

### Database Volume Mount Path Hardcoded

**Files:** PLAN.md and Dockerfile (not yet written) assume `/app/db` path

**Issue:** If app runs in a different working directory or containerization tool, path breaks

**Recommendations:**
- Make database path configurable via `DB_PATH` environment variable
- Default to `db/finally.db` relative to app root
- Validate that directory is writable at startup
- Create directory if missing

---

## Architectural Concerns

### Incomplete Request Validation Framework

**Status:** No request validation implemented (pydantic not in dependencies)

**Risk:** Malformed inputs cause app crashes instead of returning 400 errors

**Needed validations:**
- Trade requests: ticker format, quantity > 0, side in ["buy", "sell"]
- Watchlist requests: ticker length < 10, no duplicates
- Chat requests: message not empty, length < 5000
- All numeric inputs: must be positive, non-NaN

**Fix approach:**
- Add `pydantic>=2.0.0` to dependencies
- Create request/response models in `backend/app/models.py`
- Use FastAPI route handlers with type hints (automatic validation)
- Add global exception handler for validation errors (return 422)

### No Error Response Standardization

**Status:** API error responses not standardized

**Risk:** Frontend must handle various error formats

**Recommendations:**
- Define error response schema:
  ```json
  {
    "error": "insufficient_funds",
    "message": "Cannot buy: need $1000 but have $500",
    "details": {}
  }
  ```
- Document all error codes in API docs
- Handle all errors uniformly in exception middleware

### No Logging Strategy

**Status:** Market data layer uses Python `logging` module, but configuration is implicit

**Files:** Market modules use `logger = logging.getLogger(__name__)`

**Gaps:**
- No log level configuration
- No structured logging (JSON format) for production
- No log aggregation strategy
- Chat and database logs will need consistent setup

**Recommendations:**
- Configure logging in `backend/app/__init__.py` or `main.py`
- Use `structlog` or similar for structured logging
- Log at appropriate levels: DEBUG for data source events, INFO for user actions, ERROR for failures
- Include request IDs for tracing across logs

---

## Code Quality

### Simulator Hardcodes Event Probability at 0.1%

**Files:** `backend/app/market/simulator.py` line 54, default `event_probability=0.001`

**Issue:** Random "shock" events might be unexpected in testing or production

**Current state:** Made configurable but defaults to always active

**Recommendation:**
- Document in API docs that simulator includes random events
- Consider adding environment variable `MARKET_EVENT_PROBABILITY` for control
- Ensure E2E tests disable events (set to 0) for determinism

### Missing Type Hints in Some Functions

**Files:** `backend/app/market/massive_client.py` line 123

**Code:**
```python
def _fetch_snapshots(self) -> list:
    """Synchronous call to the Massive REST API. Runs in a thread."""
```

**Issue:** Return type is too vague (`list` instead of `list[SnapshotData]`)

**Impact:** Type checker can't verify correctness, IDE autocomplete limited

**Fix approach:**
- Import types from `massive` package
- Annotate as `list[SnapshotMarketType]` or equivalent
- Run `mypy` in CI to catch type errors

---

## Future Work & Recommendations

### Priority 1 (Blocking Release)

1. Implement FastAPI server initialization and route mounting
2. Implement database schema, ORM models, and lazy initialization
3. Implement portfolio endpoints (trade execution, P&L)
4. Implement watchlist endpoints
5. Implement LLM integration via LiteLLM/OpenRouter
6. Implement chat endpoint with structured output parsing
7. Build Docker container
8. Implement E2E test suite

### Priority 2 (Important)

1. Add request validation (Pydantic models)
2. Add database migration strategy (Alembic)
3. Implement circuit breaker for Massive API failures
4. Add structured logging
5. Implement error response standardization
6. Add `.env.example` with template
7. Implement start/stop scripts

### Priority 3 (Polish)

1. Add data quality indicators for stale prices
2. Implement trade limits for AI auto-execution
3. Add per-ticker SSE optimization (send only changes)
4. Implement API rate limiting
5. Add audit logging for all trades
6. Implement Massive API tier detection
7. Add mypy type checking to CI

---

*Concerns audit: 2026-08-01*
