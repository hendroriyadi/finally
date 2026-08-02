# Walking Skeleton — FinAlly (AI Trading Workstation)

**Phase:** 1
**Generated:** 2026-08-02

## Capability Proven End-to-End

A user opens `http://localhost:3000` with no login and sees the ten seeded watchlist tickers — read from SQLite, served by FastAPI, rendered in a dark terminal grid — with prices ticking live over SSE, and can add or remove a ticker that survives a page refresh and a backend restart.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backend framework | FastAPI (`backend/app/main.py`, `create_app()` factory + `lifespan`) | Already pinned in `backend/pyproject.toml` (`fastapi>=0.115.0`); the frozen `app/market/` subsystem is already written against it. `lifespan` is the single place DB init and market-source start/stop happen. |
| App assembly pattern | Explicit `create_app()` factory closing over one `PriceCache` instance; per-request access via `request.app.state` | `.planning/codebase/ARCHITECTURE.md` documents a module-level `PriceCache` singleton as an anti-pattern. `create_stream_router(cache)` needs the cache at import time, `lifespan` needs it at startup — a factory closure resolves the ordering without a global. |
| Data layer | stdlib `sqlite3`, one short-lived connection per call, every call wrapped in `asyncio.to_thread()` via `app.db.connection.run_db()` | Locked by `01-CONTEXT.md` (no `aiosqlite`, no ORM). Short-lived connections sidestep `sqlite3`'s cross-thread sharing rules entirely at this app's single-user QPS. |
| Durability config | `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=5000` set on every connection open | DB-03. WAL persists at file level; `busy_timeout` is per-connection and must be reissued. Phase 1 is the first writer, so it establishes this from the first commit rather than retroactively. |
| Schema location | `backend/app/db/schema.sql` (inside the importable package) | Loaded by relative path from `app/db/init.py` without reaching outside the package. Deliberately NOT `backend/db/` and deliberately NOT the repo-root `db/` — the repo-root `db/` is the runtime SQLite volume mount (`db/finally.db`) and is a different, unrelated path. |
| Runtime DB path | `FINALLY_DB_PATH` env var; default = repo-root `db/finally.db` resolved from `Path(__file__).resolve().parents[3]` | Same file the Phase 5 Docker volume mounts at `/app/db`. Env override is what lets tests point at a tmp path instead of the developer's real DB. |
| Seed source of truth | `app.market.seed_prices.SEED_PRICES` keys, imported by `app/db/init.py` | `01-CONTEXT.md`: single source of truth, no duplicated ticker literal. `schema.sql` is pure DDL — zero ticker literals. |
| Frontend framework | Next.js App Router + TypeScript, `output: 'export'` static export | PLAN.md §3/§11 — the export is served by FastAPI as static files in Phase 5, giving a single origin and no CORS in production. |
| Styling | Tailwind CSS **v4** (CSS-first `@theme` config, `@tailwindcss/postcss`) — not v3 | v4 is npm's current major. A v3-shaped config against a v4 install produces an app that builds cleanly and renders completely unstyled, with no error. |
| Component library | None — hand-written Tailwind components; `lucide-react` for icons | `01-UI-SPEC.md`: shadcn deliberately not initialized this phase; the only interactive surfaces are one add form and per-row remove buttons. |
| Real-time transport | Server-Sent Events; browser-native `EventSource`, no custom retry | STREAM-01/02. `backend/app/market/stream.py` already emits `retry: 1000`; hand-rolled reconnect logic would fight the browser. |
| Sparkline rendering | Hand-written inline SVG `<polyline>` (`components/Sparkline.tsx`), points accumulated client-side | Planner's discretion per `01-CONTEXT.md`. A ~30-line component beats a new dependency and its legitimacy-audit surface. |
| Dev deployment | Two processes: FastAPI on `:8000`, `next dev` on `:3000`, bridged by a `CORSMiddleware` allowlist of exactly `http://localhost:3000` | `output: 'export'` disables `next.config` rewrites-based proxying, so cross-origin dev is unavoidable until Phase 5's single-origin container. `NEXT_PUBLIC_API_URL` defaults to `''` (same-origin) so no frontend code changes when Phase 5 lands. |
| Directory layout | `backend/app/{market,db,routes}/` + `backend/tests/` mirroring it; `frontend/{app,components,lib}/` | Extends the existing `backend/app/market/` + `backend/tests/market/` mirror convention. Frontend follows stock App Router conventions (no `src/`). |

## Stack Touched in Phase 1

- [ ] **Project scaffold** — `backend/app/main.py` (first-ever FastAPI app object), `frontend/` Next.js + TypeScript + Tailwind v4 + ESLint (first-ever frontend code in this repo)
- [ ] **Routing** — `GET /api/health`, `GET /api/watchlist`, `POST /api/watchlist`, `DELETE /api/watchlist/{ticker}`, `GET /api/stream/prices` (mounted from the frozen `create_stream_router`)
- [ ] **Database** — real read (`list_watchlist()` behind `GET /api/watchlist`) AND real write (`add_watchlist_ticker()` / `remove_watchlist_ticker()` behind POST/DELETE), against a lazily-initialized, WAL-mode SQLite file
- [ ] **UI** — dark terminal shell rendering the live watchlist grid; interactive add-ticker form and per-row remove control wired to the API; live price flash, change %, sparkline, connection-status dot
- [ ] **Deployment** — documented local full-stack run (below); containerization is Phase 5

### Documented local full-stack run

```bash
# Terminal 1 — backend on :8000
cd backend
uv sync --extra dev
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend on :3000
cd frontend
npm install
npm run dev        # reads NEXT_PUBLIC_API_URL from .env.local

# Browse to http://localhost:3000
```

`frontend/.env.local` (copy from `.env.local.example`):

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Operative Definitions Recorded Here (not re-litigated in later phases)

- **"Daily change %" (WATCH-04)** is computed client-side as `(price − session_baseline) / session_baseline × 100`, where `session_baseline` is the first price the browser observes for that ticker since page load. The frozen market layer exposes no market-open reference price (`PriceUpdate.change_percent` is tick-to-tick, and the simulator's session begins at backend start), so a session baseline is the only honest reference available without modifying frozen code. Column header is `CHG%` per `01-UI-SPEC.md`.
- **Watchlist size cap** is 50 tickers, enforced server-side. This is the resource-exhaustion mitigation for `POST /api/watchlist` (threat `T-01-03`), not a product limit.
- **Ticker shape** is `^[A-Z0-9.\-]{1,10}$` after `.strip().upper()`, validated server-side on every write path and on the DELETE path parameter.

## Out of Scope (Deferred to Later Slices)

- Trade execution, `execute_trade()`, positions/trades/portfolio_snapshots writers — Phase 2. The tables exist after Phase 1's init (DB-01 requires the full schema) but stay empty.
- Portfolio heatmap, P&L-over-time chart, per-ticker main detail chart, `chat_messages` writers — Phases 3 and 4.
- AI chat panel, `backend/app/llm/`, LiteLLM/OpenRouter integration — Phase 4.
- Docker packaging, `scripts/start_*`/`stop_*`, static-export serving from FastAPI, removal of the dev CORS allowlist — Phase 5.
- Frontend component test framework (TEST-03) and Playwright E2E (TEST-04) — Phase 5. Phase 1 frontend acceptance is `npm run build` + `tsc --noEmit` + conversational UAT.
- Placeholder panels for future phases. `01-CONTEXT.md` is explicit: absent, not stubbed-and-rendered.

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- **Phase 2 — Manual Trading:** adds `app/services/trade.py` (`execute_trade()`), `POST /api/portfolio/trade`, `GET /api/portfolio`, the trade bar and positions table. Reuses `run_db()`, the WAL connection factory, and the `PriceCache` already on `app.state`.
- **Phase 3 — Portfolio Visualization:** adds the snapshot background task, `GET /api/portfolio/history`, treemap/P&L/detail charts. Reuses the same `lifespan` for the 30-second task.
- **Phase 4 — AI Copilot:** adds `app/llm/`, `POST /api/chat`, the chat panel. Calls Phase 2's `execute_trade()` and Phase 1's watchlist service functions — never a parallel path.
- **Phase 5 — One-Command Ship:** multi-stage Dockerfile, FastAPI serves `frontend/out/` as static files on port 8000, the dev CORS allowlist is removed, start/stop scripts, full test suite.
