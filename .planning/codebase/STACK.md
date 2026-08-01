# Technology Stack

**Analysis Date:** 2026-08-01

## Languages

**Primary:**
- Python 3.12+ - Backend API, market data, database, and LLM integration
- TypeScript - Frontend (Next.js static export, not yet initialized)
- SQL - SQLite schema and queries

**Secondary:**
- Shell (bash/powershell) - Docker start/stop scripts

## Runtime

**Environment:**
- Python 3.12 (backend)
- Node.js 20 (frontend, for Next.js build)

**Package Managers:**
- uv 0.45+ - Python package and project manager (`backend/pyproject.toml`)
- npm - JavaScript/TypeScript dependencies (frontend)

**Lockfiles:**
- `backend/uv.lock` - Python dependencies locked
- Frontend `package-lock.json` - will exist after frontend initialization

## Frameworks

**Core:**
- FastAPI 0.128.7 - REST API server, SSE streaming, static file serving
- uvicorn 0.40.0 (with `[standard]` extras) - ASGI application server
- Next.js (TBD version) - Frontend SPA with static export (`output: 'export'`)

**Market Data:**
- numpy 2.4.2 - Geometric Brownian Motion simulation calculations
- massive 2.2.0 - Polygon.io REST API client (optional, for real market data)

**CLI & Display:**
- rich 13.0.0+ - Terminal UI formatting and live dashboards (demo tool)
- click 8.3.1 - Command-line argument parsing (dependencies of rich/uvicorn)

**Testing:**
- pytest 8.3.0+ - Unit and integration test runner
- pytest-asyncio 0.24.0+ - Async test support for FastAPI
- pytest-cov 5.0.0+ - Code coverage reporting

**Build & Dev:**
- Hatchling - Python package build backend
- ruff 0.7.0+ - Fast Python linter and formatter
- coverage 7.13+ - Code coverage tools

## Key Dependencies

**Critical:**
- `fastapi>=0.115.0` - Core server framework
- `uvicorn[standard]>=0.32.0` - ASGI server (includes uvloop, httptools for performance)
- `numpy>=2.0.0` - GBM price simulation math
- `massive>=1.0.0` - Polygon.io market data client (optional runtime dependency)

**Infrastructure:**
- `pydantic>=2.0` - Data validation and serialization (FastAPI dependency)
- `httpx` - HTTP client (transitive, via FastAPI/uvicorn)
- `certifi>=2026.1.4` - SSL certificates (transitive, via massive/requests)
- `urllib3` - HTTP pooling (transitive, via massive)

**Dev & Quality:**
- `pytest>=8.3.0` - Test framework
- `pytest-asyncio>=0.24.0` - Async test support
- `pytest-cov>=5.0.0` - Coverage measurement
- `ruff>=0.7.0` - Linting and formatting (replaces flake8, black, isort)

## Configuration

**Environment:**
All configuration is environment-variable driven. See `.env` file structure:
- `.env` at project root (gitignored, contains secrets)
- No `.env.example` committed yet (should be added for onboarding)

**Required Variables:**
- `OPENROUTER_API_KEY` - LLM integration via OpenRouter (not yet consumed by code)
- `MASSIVE_API_KEY` (optional) - Real market data from Polygon.io; empty/missing → uses simulator

**Optional Variables:**
- `LLM_MOCK=false` (default) - Set to `true` for deterministic mock LLM responses in E2E tests

**Build Configuration:**
- `backend/pyproject.toml` - Python project metadata, dependencies, test config, tool settings:
  - pytest: `testpaths=["tests"]`, `asyncio_mode="auto"`
  - ruff: `line-length=100`, `target-version="py312"`, linters E/F/I/N/W
  - coverage: reporting for `app/` with exclusions for common patterns

**Formatting & Linting:**
- Ruff handles all formatting/linting (no separate black, flake8, isort)
- ESLint/Prettier config for frontend: TBD (not yet configured)

## Platform Requirements

**Development:**
- Python 3.12+
- Node.js 20+ (for frontend builds)
- Docker (for running the containerized app locally)
- macOS/Linux/Windows with bash/powershell support

**Production:**
- Docker container runtime (one image, single port 8000)
- SQLite database (single file, volume-mounted for persistence)
- Memory: ~200-500 MB baseline
- Disk: ~1-2 GB for Docker image, plus SQLite data

## Database

**SQLite:**
- Single file: `db/finally.db` (created at runtime if missing)
- Location: volume-mounted at `/app/db` in container, mapped to `db/` in project root
- Lazy initialization: tables and seed data created on first startup if not present
- Schema includes user profiles, watchlist, positions, trades, portfolio snapshots, and chat history
- All tables include `user_id` column (hardcoded to `"default"` for single-user, future-proofed for multi-user)

## Deployment

**Docker:**
- Multi-stage Dockerfile (Node stage → Python stage)
- Stage 1: Node 20 slim - Build Next.js static export
- Stage 2: Python 3.12 slim - Run FastAPI server
- Exposes port 8000
- Entry point: `uvicorn app:create_app() --host 0.0.0.0 --port 8000`

**Start Scripts:**
- `scripts/start_mac.sh` - Builds Docker image, runs container with volume mount, optional browser launch
- `scripts/start_windows.ps1` - PowerShell equivalent
- `scripts/stop_mac.sh` / `scripts/stop_windows.ps1` - Stop and remove container (preserves volume)

---

*Stack analysis: 2026-08-01*
