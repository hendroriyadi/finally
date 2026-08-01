# External Integrations

**Analysis Date:** 2026-08-01

## APIs & External Services

**Large Language Model (LLM):**
- OpenRouter (via LiteLLM)
  - What it's used for: AI trading assistant, trade suggestions, portfolio analysis, watchlist management
  - Model: `openrouter/openai/gpt-oss-120b` with Cerebras inference provider
  - SDK/Client: LiteLLM (not yet added to `pyproject.toml`)
  - Auth: Environment variable `OPENROUTER_API_KEY`
  - Status: Design documented, implementation pending
  - Structured outputs: LLM responds with JSON schema containing message, trades array, watchlist_changes array
  - Auto-execution: Trades and watchlist changes auto-execute; errors reported back to LLM for user messaging

**Market Data - Primary:**
- Polygon.io via Massive SDK (optional, conditional)
  - What it's used for: Real stock price data, live market feeds
  - SDK/Client: `massive>=1.0.0` (Polygon.io Python SDK)
  - Auth: Environment variable `MASSIVE_API_KEY`
  - API endpoint: REST polling to `GET /v2/snapshot/locale/us/markets/stocks/tickers`
  - Rate limits: Free tier 5 req/min (default poll every 15s), paid tiers 2-15s
  - Activation: Only loaded if `MASSIVE_API_KEY` is set and non-empty
  - Location: `backend/app/market/massive_client.py` (MassiveDataSource class)

**Market Data - Fallback (Default):**
- Built-in simulator (no external API)
  - What it's used for: Generates realistic correlated price movements when `MASSIVE_API_KEY` is absent
  - Algorithm: Geometric Brownian Motion (GBM) with per-ticker drift and volatility
  - Correlation: Tech stocks (AAPL, GOOGL, MSFT, AMZN, META, NVDA, NFLX) move together at 60%, finance stocks (JPM, V) at 50%, cross-sector at 30%, TSLA at 30%
  - Location: `backend/app/market/simulator.py` (SimulatorDataSource + GBMSimulator classes)
  - Seed prices: Realistic starting prices in `backend/app/market/seed_prices.py`

## Data Storage

**Databases:**
- SQLite (primary)
  - Connection: Single file at `db/finally.db`
  - Client: Python standard library `sqlite3` (used directly or via abstraction layer)
  - Lazy initialization: Tables and seed data auto-created on first startup
  - Persistence: Volume-mounted in Docker; survives container restarts
  - No ORM: Direct SQL or minimal wrapper (TBD per backend implementation phase)

**File Storage:**
- Local filesystem only
  - Static frontend assets: Served from `static/` directory (populated by Next.js static export during Docker build)
  - Database file: `db/finally.db`
  - No cloud storage (S3, GCS, etc.) planned

**Caching:**
- In-memory price cache (PriceCache class)
  - Location: `backend/app/market/cache.py`
  - Persisted by: Background task (simulator or Massive poller writes updates)
  - Data: Latest price, previous price, timestamp, computed change/change_percent/direction
  - Consumed by: SSE streaming, API endpoints, LLM chat context
  - Thread-safe: Uses synchronization primitives for concurrent access

## Authentication & Identity

**Auth Provider:**
- None (custom, hardcoded)
  - Implementation: Single hardcoded user ID `"default"` in all database operations
  - No login/signup: Opens directly to app
  - No session management: Stateless API
  - Future-proofing: Schema includes `user_id` column for multi-user support (not yet implemented)
  - Security: Intended for demo/course environment only (fake money, no sensitive data)

## Monitoring & Observability

**Error Tracking:**
- None (not configured)
- Planned: Could add Sentry, Datadog, or similar in future phases

**Logs:**
- Console-based (standard Python logging)
  - Logger config: No rotation or persistence yet
  - Levels: Info, warning, error for market data polling, API requests, database operations
  - Output: Goes to stdout (captured by Docker container)
  - Example: GBM simulator logs startup info, Massive poller logs rate limits and poll timing

**Database Queries:**
- No query logging/monitoring configured
- Ad-hoc tracing: Can enable via `SQLITE_DEBUG` or custom logging wrapper if needed

## CI/CD & Deployment

**Hosting:**
- Docker container (single port 8000)
- Multi-stage build: Node.js (frontend) → Python (backend)
- Platform: Supports AWS App Runner, Render, any container-capable platform
- Local development: Docker via start scripts

**CI Pipeline:**
- Not yet configured
- Planned: GitHub Actions for:
  - Lint (ruff)
  - Test (pytest with coverage)
  - Build Docker image
  - Push to registry (if deploying to cloud)

**Environment Provisioning:**
- Docker volume for SQLite persistence
- Environment variables passed via `--env-file .env` or runtime env
- Port mapping: Container 8000 → Host 8000 (or custom via script)

## Environment Configuration

**Required env vars:**
- `OPENROUTER_API_KEY` - API key for LLM calls (string, no default)

**Optional env vars:**
- `MASSIVE_API_KEY` - API key for real market data; empty/missing → uses simulator (default)
- `LLM_MOCK` - Set to `"true"` for deterministic test responses (default `"false"`)

**Secrets location:**
- `.env` file at project root (gitignored)
- Never committed to git
- `.env.example` should be created (template with dummy values) for onboarding

**Variable Discovery:**
- Backend reads at startup via Python `os.environ.get()`
- Locations in code:
  - `backend/app/market/factory.py` - reads `MASSIVE_API_KEY` to select data source
  - LLM integration (pending) - will read `OPENROUTER_API_KEY`
  - Test suite - reads `LLM_MOCK` for deterministic behavior

## Webhooks & Callbacks

**Incoming:**
- None currently
- Possible future: Webhook from Polygon.io if switching to WebSocket tiers

**Outgoing:**
- None currently
- Possible future: Webhook to external systems when trades execute (e.g., Discord notifications)

## External Dependencies at Runtime

| Service | Required | Optional | Env Var | Used By |
|---------|----------|----------|---------|---------|
| Polygon.io (Massive) | No | Yes | `MASSIVE_API_KEY` | `backend/app/market/massive_client.py` |
| OpenRouter (LiteLLM) | No | Yes | `OPENROUTER_API_KEY` | LLM integration (pending) |
| SQLite | Yes | No | N/A | All data persistence |
| Docker | Yes (prod) | N/A | N/A | Container runtime |

---

*Integration audit: 2026-08-01*
