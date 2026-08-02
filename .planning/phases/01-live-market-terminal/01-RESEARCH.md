# Phase 1: Live Market Terminal - Research

**Researched:** 2026-08-02
**Domain:** FastAPI lazy SQLite init + lifespan wiring; first-ever Next.js static-export frontend with SSE-driven watchlist UI
**Confidence:** MEDIUM (backend patterns CITED against official docs and this session's own tool verification; frontend patterns CITED against official docs where available, ASSUMED/LOW for community-only SSE/sparkline glue code)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Schema (locked by PLAN.md §7 — not a grey area, restated for the planner)**
- Six tables, all with `user_id TEXT DEFAULT 'default'`: `users_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages`. All six must exist after lazy init (DB-01) even though this phase only reads/writes `users_profile` (seed only) and `watchlist`.
- IDs: TEXT PRIMARY KEY, UUIDs (except `users_profile.id = "default"`). Timestamps: TEXT ISO 8601.
- Seed: `users_profile` row with `cash_balance=10000.0`; ten `watchlist` rows — AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX (must match `backend/app/market/seed_prices.py`'s ticker list exactly — reuse that list, don't re-declare it).
- WAL mode (`PRAGMA journal_mode=WAL`) + `PRAGMA busy_timeout=5000` on every connection (DB-03) — this phase is the first writer, so it must set this up correctly even though heavy concurrent writes don't start until Phase 2's trade endpoint.
- Lazy init: on backend startup (FastAPI `lifespan`, fastapi>=0.115 already pinned), check for tables; create `backend/db/schema.sql` + `backend/db/seed.sql` if missing. Idempotent — safe to call on every restart, never re-seeds an already-initialized DB. `backend/db/` does not currently exist on disk (must be created); do not trust any codebase-map claim that schema.sql/seed.sql are pre-existing placeholders — verify with `ls` first.
- DB connection pattern: stdlib `sqlite3` (no new dependency, no `aiosqlite`/ORM), wrapped in `asyncio.to_thread()` per call — matches the existing `backend/app/market/massive_client.py` blocking-I/O pattern.

**Known environment issue — MUST be an early task**
- `db/finally.db` is currently **committed to git** with stale, polluted seed data (extra watchlist rows, phantom positions/trades) from an earlier scaffolding step, and `.gitignore` only matches the Django-leftover pattern `db.sqlite3` — it does NOT match `finally.db`. Since lazy-init only seeds when tables are missing, this stale committed file would be silently treated as "already initialized" and never get the correct seed data. The plan MUST: untrack `db/finally.db` from git, delete it (and any `-shm`/`-wal` sidecars) from the working tree, add `db/.gitkeep`, and fix `.gitignore` to match `finally.db`/`finally.db-shm`/`finally.db-wal`/`finally.db-journal`.

**SSE Route (STREAM-01, STREAM-02)**
- `GET /api/stream/prices` — thin FastAPI route wiring; the actual SSE generator already exists and is fully implemented/tested at `backend/app/market/stream.py:create_stream_router()`. This phase's job is to mount that router in the (new, to-be-created) FastAPI app entrypoint, initialize the market data source (`create_market_data_source(cache)` from `backend/app/market/factory.py`) at startup with the seeded watchlist tickers, and ensure watchlist add/remove calls `MarketDataSource.add_ticker()`/`remove_ticker()` so the stream tracks watchlist changes live.
- Frontend: native `EventSource` for the SSE connection (STREAM-02 — reconnection is `EventSource`'s built-in behavior, no custom retry logic needed).

**Frontend (first-ever Next.js code in this repo)**
- `frontend/` is currently empty. This phase scaffolds the whole Next.js TypeScript project: `output: 'export'` static export config (per PLAN.md §3/§11 — single-origin, no CORS, servable as static files by FastAPI later in Phase 5), Tailwind CSS with the locked dark theme (backgrounds `#0d1117`/`#1a1a2e`, no pure black; accent yellow `#ecad0a`, blue primary `#209dd7`, purple secondary `#753991` for submit buttons).
- Watchlist grid: ticker, live price (green/red flash on change fading ~500ms via CSS transition), daily change %, sparkline mini-chart accumulated client-side from the SSE stream since page load (not server-computed history — the frontend builds it up in memory as events arrive).
- Header: connection-status dot (green=connected, yellow=reconnecting, red=disconnected), driven by `EventSource.onopen`/`onerror` state.
- Add/remove ticker UI: simple input + button, calls `POST /api/watchlist` / `DELETE /api/watchlist/{ticker}`.
- No portfolio/trade/chat UI in this phase — those are stubbed absent, not placeholder-rendered (don't build empty panels for future phases).

### Claude's Discretion
- Exact Next.js file/component structure (`frontend/components/`, `frontend/lib/`) — follow standard Next.js App Router conventions since this is a fresh scaffold; no existing frontend convention to match yet.
- Charting approach for the sparkline specifically (inline SVG/canvas vs. a lightweight library) — PLAN.md recommends Lightweight Charts or Recharts for the *main* detail chart (that's Phase 3), but a watchlist-row sparkline is small enough that a hand-rolled inline SVG polyline may be simpler than pulling in a charting dependency this early; planner's call.
- Backend app entrypoint structure (`backend/app/main.py` vs similar) — first phase to create the actual `FastAPI()` app object; follow `backend/app/market/` conventions (factory functions, dependency injection, no global state).

### Deferred Ideas (OUT OF SCOPE)
- Trade execution, positions, trades, portfolio_snapshots writers — Phase 2.
- Portfolio heatmap, P&L chart, ticker detail chart — Phase 3.
- AI chat panel — Phase 4.
- Docker packaging, start/stop scripts — Phase 5.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DB-01 | System persists cash balance, watchlist, positions, trades, snapshots, chat history in SQLite | Schema DDL verbatim from PLAN.md §7 (quoted below); `backend/db/schema.sql` recommended structure and connection-factory pattern in Architecture Patterns |
| DB-02 | Schema and seed data lazily initialized on startup if missing | FastAPI `lifespan` pattern (CITED, official docs) + idempotent init-check function in Code Examples; stale committed `db/finally.db` remediation task documented as a pitfall (VERIFIED this session) |
| DB-03 | WAL mode + `busy_timeout` for safe concurrent writers | Per-connection pragma pattern in Code Examples; verified stdlib `sqlite3`/SQLite version available in this repo's actual `uv` environment (3.49.1 — supports both pragmas) |
| STREAM-01 | Live price updates via SSE at `/api/stream/prices`, sourced from price cache | `create_stream_router()` already implemented (read this session, verbatim in Code Context); mounting pattern in Architecture Patterns |
| STREAM-02 | Frontend auto-reconnects on SSE disconnect via `EventSource` native retry | `retry: 1000` directive already emitted by `stream.py` (verified by reading the file); client-side `EventSource` usage pattern in Code Examples (community sources, LOW confidence) |
| WATCH-01 | Default watchlist of 10 tickers on first launch | Seed data must reuse `app/market/seed_prices.SEED_PRICES` keys, not a literal SQL list — see Architecture Patterns "Seeding without duplicating the ticker list" |
| WATCH-02 | User can add a ticker | Watchlist route pattern + `MarketDataSource.add_ticker()` call-through in Architecture Patterns |
| WATCH-03 | User can remove a ticker | Watchlist route pattern + `MarketDataSource.remove_ticker()` call-through in Architecture Patterns |
| WATCH-04 | Grid shows live price, daily change %, sparkline accumulated from SSE since page load | Client-accumulated sparkline pattern (Code Examples, community sources, LOW confidence) |
| WATCH-05 | Price flash animation fading ~500ms | CSS transition pattern in Code Examples |
| UI-01 | Dark, data-dense layout, no login | Next.js + Tailwind v4 setup pattern (CITED, official docs); dark theme tokens from `01-UI-SPEC.md` |
</phase_requirements>

## Summary

This phase has two nearly independent halves that meet at two HTTP contracts (`GET/POST /api/watchlist`, `DELETE /api/watchlist/{ticker}`, and `GET /api/stream/prices`): a backend half that creates the first-ever FastAPI app object, wires a lazy-init SQLite layer with WAL+busy_timeout, and mounts the already-fully-built `create_stream_router()`; and a frontend half that scaffolds the first-ever Next.js project as a static export with Tailwind CSS v4, an `EventSource`-driven watchlist grid, and a client-accumulated inline-SVG sparkline. Nothing here is architecturally novel — every piece has a well-documented standard pattern — but there are several concrete, session-verified gaps that would bite silently if skipped: `db/finally.db` is genuinely committed to git with polluted seed data (12 watchlist rows, 2 phantom positions, 2 phantom trades — confirmed by direct `sqlite3` query this session) and `.gitignore` genuinely does not match it; `backend/app/routes/`, `backend/app/llm/`, and `backend/db/` do not exist on disk at all (contradicting the codebase map's claim that they're empty-but-present placeholders); and `httpx` — required for FastAPI's `TestClient` — is not in `backend/uv.lock` and genuinely fails to import in the project's actual `uv` environment, verified by running `uv run python -c "import httpx"` this session.

The Tailwind CSS ecosystem has moved to v4 since PLAN.md was written and since most training-data-era Next.js+Tailwind tutorials — the setup flow is materially different (no `tailwind.config.js` by default, `@tailwindcss/postcss` package instead of `tailwindcss`+`autoprefixer` as direct PostCSS plugins, `@import "tailwindcss";` instead of the three `@tailwind` directives). Getting this wrong produces a Next.js app that builds but renders completely unstyled.

**Primary recommendation:** Build a single new `backend/app/main.py` with one `@asynccontextmanager lifespan` that (1) lazy-inits SQLite via a small `backend/app/db/` package, (2) creates and starts the market data source seeded from `app.market.seed_prices.SEED_PRICES`, (3) mounts `create_stream_router(cache)` plus a new `backend/app/routes/watchlist.py` router, and tears the market source down on shutdown. Scaffold `frontend/` with `create-next-app` (App Router, TypeScript, Tailwind), replace the generated v3-style Tailwind config with the actual current v4 flow, and build the watchlist grid as one `'use client'` component owning a single `EventSource` plus an in-memory ring-buffer per ticker for the sparkline.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SQLite schema/seed lazy-init (DB-01/02/03) | API/Backend | Database/Storage | FastAPI lifespan owns the init trigger; SQLite file is the storage tier being initialized |
| WAL mode + busy_timeout config | Database/Storage | — | Pragmas are a property of the SQLite connection/file itself, set from backend code but conceptually owned by the storage layer |
| SSE price streaming (STREAM-01/02) | API/Backend | Browser/Client | `create_stream_router` (backend) produces the event stream; `EventSource` (browser) consumes and reconnects — split responsibility by design (server push, client retry) |
| Watchlist CRUD persistence (WATCH-02/03) | API/Backend | Database/Storage | Route handlers own validation + the DB write + the market-source call-through; DB is the persisted record of truth |
| Watchlist grid rendering, price flash, sparkline (WATCH-01/04/05) | Browser/Client | — | Pure client-side rendering/animation/accumulation from data already pushed by SSE; no new backend surface |
| Dark theme/layout shell (UI-01) | Browser/Client | — | Static Tailwind styling, no server involvement |
| Connection-status dot | Browser/Client | — | Derived entirely from `EventSource` readyState/`onopen`/`onerror`, no backend signal needed |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | >=0.115.0 (already pinned; repo has 0.128.7 installed) | Backend API, lifespan, SSE via `StreamingResponse` | Already the project's chosen framework; `create_stream_router` already built against it |
| stdlib `sqlite3` | bundled with Python 3.13.3 (uv-resolved interpreter in this repo; SQLite 3.49.1) | DB access, WAL + busy_timeout | Locked decision — no ORM/driver dependency; project explicitly rejects `aiosqlite` |
| next | latest 4.x-compatible major at install time (npm registry currently reports 16.2.12 as of this session — see Package Legitimacy Audit) | Frontend framework, static export | PLAN.md §3/§10 mandates Next.js static export |
| react / react-dom | matches whatever `create-next-app` pins for the chosen Next version (npm registry currently reports 19.2.8) | UI rendering | Required peer of Next.js |
| typescript | matches `create-next-app` default (npm registry currently reports 7.0.2) | Type safety per PLAN.md's "TypeScript" frontend requirement | Standard for Next.js projects |
| tailwindcss + @tailwindcss/postcss + postcss | v4.x (npm registry currently reports tailwindcss 4.3.3) | Styling, dark theme tokens | PLAN.md §10 "Tailwind CSS for styling with a custom dark theme"; v4 is the current major, setup flow differs from v3 (see Architecture Patterns) |
| lucide-react | latest (npm registry currently reports 1.28.0) | Icons | Locked by `01-UI-SPEC.md` ("Icon library | lucide-react") |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | 0.28.1 (verified via PyPI JSON API this session) | Required by `fastapi.testclient.TestClient` | Add to `backend/pyproject.toml` `[project.optional-dependencies].dev` — **currently missing from `uv.lock`; genuinely fails to import in this repo's environment, verified this session** |
| eslint + eslint-config-next | matches `create-next-app` default | Lint | Standard Next.js scaffold output, optional but conventional |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled inline SVG sparkline | A micro sparkline lib (e.g. a zero-dep vanilla-JS sparkline package found via WebSearch) | CONTEXT.md explicitly leaves this to planner discretion; a dependency adds install/legitimacy-audit surface for a ~30-line component. Recommend hand-rolled unless the planner wants a battle-tested library — no specific package is recommended here since none was verified this session (would need a fresh legitimacy check if chosen). |
| stdlib `sqlite3` + `asyncio.to_thread` | `aiosqlite` | Locked decision (CONTEXT.md) rules this out explicitly — do not introduce it |
| Tailwind CSS v4 (CSS-first config) | Tailwind CSS v3 (`tailwind.config.js` + `@tailwind` directives) | v3 is what most existing tutorials/training data show, but v4 is npm's actual current major (confirmed via `npm view tailwindcss version` this session) — using v3 syntax with a v4 install will silently fail to apply styles |

**Installation:**
```bash
# Backend — add the missing test dependency
cd backend
uv add --optional dev httpx

# Frontend — scaffold from scratch
npx create-next-app@latest frontend --typescript --tailwind --app --src-dir=false --import-alias "@/*"
cd frontend
npm install lucide-react
```

**Version verification:** Verified live against the npm registry and PyPI JSON API during this research session (see `npm view <pkg> version` outputs and `curl https://pypi.org/pypi/httpx/json` in Sources). Package *names* are still tagged `[ASSUMED]` per the package-name provenance rule below — registry existence and official-docs citation alone do not upgrade a hallucination-risk package name to `[VERIFIED]` under this project's protocol; see Package Legitimacy Audit.

## Package Legitimacy Audit

All ten frontend packages plus `@tailwindcss/postcss` returned verdict `SUS` from the legitimacy-check seam, but for a single, identical, and low-risk reason: `"too-new"` — the *most recently published version* of each package was published within the last ~1-4 weeks of this research session. This is expected behavior for actively-maintained, extremely popular packages that ship frequent patch releases (all ten have official GitHub repos under well-known orgs — `vercel/next.js`, `facebook/react` lineage, `tailwindlabs/tailwindcss`, `microsoft/TypeScript`, `postcss/postcss`, `postcss/autoprefixer`, `lucide-icons/lucide`, `eslint/eslint` — and weekly download counts ranging from ~31M to ~273M). None of these signals resemble a slopsquat (new package, zero downloads, no repo). Per protocol, the verdict is still recorded as `SUS` and the planner must add a lightweight `checkpoint:human-verify` before the frontend scaffold install step — treat this as a fast sanity check (confirm `package.json` after `create-next-app` lists these exact packages, not typosquatted near-neighbors), not a deep investigation.

| Package | Registry | Age (latest publish) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|----------------------|-----------|--------------|---------|--------------|
| next | npm | ~1 week | 54.9M/wk | github.com/vercel/next.js | SUS (too-new) | Keep — checkpoint:human-verify before install |
| react | npm | ~2 weeks | 162.3M/wk | github.com/react/react (mirror) | SUS (too-new) | Keep — checkpoint:human-verify before install |
| react-dom | npm | ~2 weeks | 139.2M/wk | github.com/react/react (mirror) | SUS (too-new) | Keep — checkpoint:human-verify before install |
| typescript | npm | ~3-4 weeks | 257.7M/wk | github.com/microsoft/TypeScript | SUS (too-new) | Keep — checkpoint:human-verify before install |
| tailwindcss | npm | ~2-3 weeks | 117.9M/wk | github.com/tailwindlabs/tailwindcss | SUS (too-new) | Keep — checkpoint:human-verify before install |
| @tailwindcss/postcss | npm | ~2-3 weeks | 31.8M/wk | github.com/tailwindlabs/tailwindcss | SUS (too-new) | Keep — checkpoint:human-verify before install |
| postcss | npm | ~<1 week | 273.2M/wk | github.com/postcss/postcss | SUS (too-new) | Keep — checkpoint:human-verify before install |
| autoprefixer | npm | ~2-3 weeks | 64.2M/wk | github.com/postcss/autoprefixer | SUS (too-new) | Keep, but see note — v4 bundles autoprefixer, so this may not be needed at all (see Architecture Patterns) |
| lucide-react | npm | ~<1 week | 81.7M/wk | github.com/lucide-icons/lucide | SUS (too-new) | Keep — checkpoint:human-verify before install (locked by UI-SPEC) |
| eslint | npm | ~1 week | 154.3M/wk | github.com/eslint/eslint | SUS (too-new) | Keep — checkpoint:human-verify before install (optional, conventional scaffold output) |
| eslint-config-next | npm | ~1 week | 30.8M/wk | github.com/vercel/next.js | SUS (too-new) | Keep — checkpoint:human-verify before install (optional) |
| httpx (PyPI, not npm) | PyPI | n/a (checked via PyPI JSON API, not the npm-ecosystem legitimacy seam) | n/a | github.com/encode/httpx (per official FastAPI testing docs) | Not run through npm seam (wrong ecosystem) | Approved — required by FastAPI's own testing docs, confirmed importable-gap in this repo's env |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** all 11 npm packages above, uniformly due to the `"too-new"` heuristic on latest-publish recency, not on package age/legitimacy. Planner should insert one `checkpoint:human-verify` immediately after `npm install` completes (verify `package.json`/`package-lock.json` contents match this table), rather than one per package.

*Package names in the Standard Stack table were sourced from training data and this agent's general knowledge of the Next.js/Tailwind ecosystem (not discovered fresh via WebSearch or Context7 as novel names) — per the package-name provenance rule, they remain `[ASSUMED]` even though `npm view` and Context7-fetched official docs corroborate them. `httpx` is the one exception verified against official FastAPI documentation (Context7) plus a live PyPI registry check, and is treated as `[CITED: fastapi.tiangolo.com/tutorial/testing]` + `[VERIFIED: pypi.org/pypi/httpx/json]`.*

## Architecture Patterns

### System Architecture Diagram

```
Browser (Next.js static export, served via `next dev` locally this phase)
  │
  ├─ GET  /api/watchlist ─────────────┐
  ├─ POST /api/watchlist ─────────────┤
  ├─ DELETE /api/watchlist/{ticker} ──┤
  │                                   ▼
  │                     FastAPI app (backend/app/main.py)
  │                     ┌─────────────────────────────────────┐
  │                     │ lifespan(app):                       │
  │                     │  1. init_db() — lazy schema+seed      │
  │                     │  2. cache = PriceCache()               │
  │                     │  3. source = create_market_data_source()│
  │                     │  4. await source.start(seed tickers)   │
  │                     │  5. yield                              │
  │                     │  6. await source.stop()  (shutdown)    │
  │                     │                                        │
  │                     │ app.include_router(create_stream_router(cache))
  │                     │ app.include_router(watchlist_router)   │
  │                     └───────────────┬─────────────┬─────────┘
  │                                     │             │
  │                          ┌──────────▼───┐   ┌─────▼──────────┐
  │                          │ SQLite (WAL) │   │ PriceCache /    │
  │                          │ db/finally.db│   │ MarketDataSource│
  │                          │ users_profile│   │ (Simulator or   │
  │                          │ watchlist    │   │  Massive)       │
  │                          │ (+4 unused   │   └────────┬────────┘
  │                          │  tables)     │            │ writes every ~500ms
  │                          └──────────────┘            │
  │                                                       ▼
  └── EventSource("/api/stream/prices") ◄── GET /api/stream/prices (create_stream_router,
        onmessage: append point per ticker      already implemented — reads PriceCache,
        to in-memory ring buffer → sparkline      polls version every 500ms)
        onopen/onerror → connection-status dot
```

Primary use case trace: page load → `GET /api/watchlist` (DB read, joined/merged with current `PriceCache` snapshot for initial prices) → grid renders 10 rows → `EventSource` opens against `/api/stream/prices` → every ~500ms a JSON blob of all tracked tickers arrives → each row's price cell flashes and its sparkline gains one point → user types a ticker and clicks "Add Ticker" → `POST /api/watchlist` writes to SQLite AND calls `source.add_ticker()` → next SSE tick includes the new ticker.

### Recommended Project Structure
```
backend/
├── app/
│   ├── main.py                 # NEW — FastAPI() app object, lifespan, router mounting
│   ├── db/                     # NEW package
│   │   ├── __init__.py
│   │   ├── connection.py       # get_connection() factory: sqlite3.connect + WAL/busy_timeout pragmas
│   │   ├── init.py             # init_db(): idempotent lazy create+seed, reads schema.sql, seeds via SEED_PRICES
│   │   └── schema.sql          # Pure DDL only — no ticker literals (see below)
│   ├── routes/                 # NEW package
│   │   ├── __init__.py
│   │   └── watchlist.py        # GET/POST /api/watchlist, DELETE /api/watchlist/{ticker}
│   └── market/                 # EXISTING — frozen, do not modify
├── db/                          # (unchanged — schema.sql lives under app/db/ per above; this dir is unrelated:
│                                  it's the *runtime* SQLite file location, see db/ at repo root)
└── tests/
    ├── db/                      # NEW — test_connection.py, test_init.py
    └── routes/                  # NEW — test_watchlist.py

frontend/
├── app/
│   ├── layout.tsx               # Root layout — dark theme shell, Inter font
│   ├── page.tsx                 # Home page — renders WatchlistPanel
│   └── globals.css              # `@import "tailwindcss";` + `@theme` block with brand color tokens
├── components/
│   ├── WatchlistPanel.tsx       # Owns the EventSource connection + watchlist state
│   ├── WatchlistRow.tsx         # Single row: price flash, change%, Sparkline
│   ├── Sparkline.tsx            # Inline SVG polyline from an accumulated point array
│   ├── AddTickerForm.tsx
│   └── ConnectionStatusDot.tsx
├── lib/
│   ├── api.ts                   # fetch wrappers for /api/watchlist CRUD
│   └── useSseStream.ts          # custom hook wrapping EventSource lifecycle
├── next.config.js               # output: 'export'
├── postcss.config.mjs           # { plugins: { '@tailwindcss/postcss': {} } }
└── package.json
```

**Note on `backend/db/` vs `backend/app/db/`:** The existing codebase map (`STRUCTURE.md`) places `schema.sql`/`seed.sql` under `backend/db/`, separate from `backend/app/`. That top-level `backend/db/` path does not exist on disk yet (verified this session — `ls` shows nothing there but a cache dir at the project-root `backend/db`, and the actual repo-root `db/` is the *runtime* SQLite volume mount, a different directory entirely). Either location (`backend/db/schema.sql` as a standalone asset directory, or `backend/app/db/schema.sql` as part of the importable package) is workable; recommend `backend/app/db/` so `importlib.resources`/relative-path loading of `schema.sql` from Python code doesn't need to reach outside the package — but this is a naming/location call, not a locked decision; planner should pick one and note it doesn't conflict with the *runtime* `db/finally.db` mount path at the repo root, which is unrelated and must not be confused with it.

### Pattern 1: FastAPI lifespan for lazy DB init + market data source lifecycle
**What:** A single `@asynccontextmanager` function that runs setup before `yield` and teardown after.
**When to use:** Exactly once, at app creation — this is the only place `source.start()`/`source.stop()` should be called.
**Example:**
```python
# Source: https://fastapi.tiangolo.com/advanced/events (Context7, CITED)
# Adapted to this repo's actual modules (backend/app/market/__init__.py, read this session)
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.init import init_db
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.market.seed_prices import SEED_PRICES
from app.routes.watchlist import create_watchlist_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()  # idempotent: creates tables + seeds only if missing

    cache = PriceCache()
    source = create_market_data_source(cache)
    await source.start(list(SEED_PRICES.keys()))

    app.state.price_cache = cache
    app.state.market_source = source

    yield

    await source.stop()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    # Dev-only CORS: harmless once Phase 5's Docker build serves both from one origin.
    # See "CORS in local development" pitfall below.
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


app = create_app()


@app.on_event("startup")
async def _mount_routers() -> None:
    # Routers that need app.state (set inside lifespan) are included here,
    # OR simpler: include_router() calls can happen right after create_app()
    # since router registration doesn't need lifespan to have run yet —
    # only the *handlers* need app.state.price_cache to exist at request time.
    pass


app.include_router(create_stream_router(app.state.price_cache if hasattr(app.state, "price_cache") else None))
```
**Simplification note:** the snippet above shows the naive approach running into an ordering problem — `create_stream_router(cache)` needs a `PriceCache` instance, but that instance is only created inside `lifespan`, which hasn't run yet at import time when `include_router` is normally called. The clean fix (recommended) is to create the `PriceCache` **before** `create_app()`/`lifespan` — at module scope of `main.py`, not as a global singleton passed around implicitly, but as an explicit object constructed once during app assembly and closed over by both `lifespan` and the router factories:
```python
def create_app() -> FastAPI:
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()
        source = create_market_data_source(cache)
        await source.start(list(SEED_PRICES.keys()))
        app.state.market_source = source
        yield
        await source.stop()

    app = FastAPI(lifespan=lifespan)
    app.include_router(create_stream_router(cache))
    app.include_router(create_watchlist_router(cache))
    return app
```
This keeps `cache` an explicit closed-over dependency (no module-level singleton, consistent with `backend/app/market/`'s "no global state" convention, read this session in `ARCHITECTURE.md`/`CONVENTIONS.md`) while resolving the ordering problem.

### Pattern 2: SQLite connection factory with WAL + busy_timeout
**What:** A short-lived-connection-per-call pattern (open, pragma, operate, close) run inside `asyncio.to_thread`.
**When to use:** Every DB read/write in `backend/app/db/` and `backend/app/routes/`.
**Example:**
```python
# Pattern synthesized from Python stdlib sqlite3 documentation knowledge (ASSUMED — not
# fetched fresh this session; cross-checked conceptually, not against a live doc fetch).
# WAL is a per-database-file setting (persists after first set); busy_timeout is
# per-connection and must be reissued every time a connection is opened.
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("db/finally.db")  # repo-root runtime mount; see PLAN.md §11 Docker volume


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=True)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


async def get_watchlist(user_id: str = "default") -> list[sqlite3.Row]:
    import asyncio

    def _query():
        conn = _connect()
        try:
            cur = conn.execute(
                "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at",
                (user_id,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    return await asyncio.to_thread(_query)
```
**Why open-per-call, not a shared connection:** stdlib `sqlite3.Connection` objects are not safe to share across threads unless `check_same_thread=False` is set — and even then, concurrent use from multiple threads needs external locking. Since every call already goes through `asyncio.to_thread` (a fresh worker thread from the default executor pool per call), opening a short-lived connection inside each threaded call sidesteps cross-thread sharing entirely, at the cost of a small per-call connection-open overhead — acceptable at this app's single-user, low-QPS scale.

### Pattern 3: Seeding without duplicating the ticker list
**What:** `schema.sql` contains pure DDL. Seed *logic* (not seed *data*) lives in Python and imports the canonical ticker list.
**When to use:** DB init, to satisfy CONTEXT.md's explicit "single source of truth, no duplicated literal list" instruction.
**Example:**
```python
# backend/app/db/init.py
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.market.seed_prices import SEED_PRICES  # canonical 10-ticker source of truth

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def init_db() -> None:
    def _init():
        conn = _connect()
        try:
            conn.executescript(SCHEMA_PATH.read_text())

            existing = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0]
            if existing == 0:
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
                    ("default", 10000.0, now),
                )
                for ticker in SEED_PRICES:  # dict preserves insertion order (Python 3.7+)
                    conn.execute(
                        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                        (str(uuid.uuid4()), "default", ticker, now),
                    )
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_init)
```
This is why `backend/db/seed.sql` as a *literal* file (per CONTEXT.md's phrasing) is not the right final shape for the watchlist rows specifically — a static `seed.sql` with `INSERT INTO watchlist VALUES ('AAPL', ...)` would re-declare the ticker list CONTEXT.md explicitly says must not be duplicated. Recommend: `schema.sql` = DDL only; seed *logic* = Python, as above. If the planner prefers keeping a literal `seed.sql` for the `users_profile` default row (which has no external source-of-truth conflict), that's fine — just don't put ticker literals in it.

### Pattern 4: Next.js + Tailwind v4 setup (current major, not the v3 flow most tutorials show)
**What:** CSS-first Tailwind config, no default `tailwind.config.js`.
**When to use:** Frontend scaffold step, immediately after `create-next-app`.
**Example:**
```bash
# Source: https://tailwindcss.com/docs/installation/framework-guides/nextjs (Context7, CITED)
npm install tailwindcss @tailwindcss/postcss postcss
```
```javascript
// postcss.config.mjs
// Source: https://tailwindcss.com/docs/installation/framework-guides/nextjs (Context7, CITED)
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
```
```css
/* app/globals.css */
/* Source: https://tailwindcss.com/docs/functions-and-directives (Context7, CITED) */
@import "tailwindcss";

@theme {
  --color-bg-canvas: #0d1117;
  --color-bg-panel: #1a1a2e;
  --color-accent: #ecad0a;
  --color-primary: #209dd7;
  --color-submit: #753991;
  --color-destructive: #ef4444;
  --color-positive: #22c55e;
  --color-border: #30363d;
}
```
`autoprefixer` is not a separate dependency in Tailwind v4 (bundled into `@tailwindcss/postcss`) — do not install it unless a specific need arises; the `create-next-app --tailwind` flag may still scaffold a v3-style setup depending on the exact CLI version pulled at install time, so **verify the generated `postcss.config` / `globals.css` matches the v4 shape above and correct it if `create-next-app` produced the older `tailwind.config.js` + `@tailwind base/components/utilities` flow.**

### Pattern 5: EventSource in a Next.js Client Component
**What:** A `'use client'` component or custom hook that owns exactly one `EventSource` per mount.
**When to use:** The watchlist panel; do not create more than one `EventSource` against the same endpoint per page.
**Example:**
```typescript
// lib/useSseStream.ts
// Source: community pattern, WebSearch, LOW confidence — no single canonical
// Next.js-specific doc; EventSource itself is a standard browser Web API.
'use client';

import { useEffect, useRef, useState } from 'react';

export type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected';

export function usePriceStream(url: string) {
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [prices, setPrices] = useState<Record<string, unknown>>({});

  useEffect(() => {
    const es = new EventSource(url);

    es.onopen = () => setStatus('connected');
    es.onerror = () => setStatus('reconnecting'); // EventSource auto-retries; don't rebuild manually
    es.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setPrices(data);
    };

    return () => es.close(); // cleanup on unmount only — never on every render
  }, [url]);

  return { status, prices };
}
```
**Do not** manually call `es.close()` + `new EventSource()` on error — this fights the browser's native retry (driven by the `retry: 1000` directive `stream.py` already emits, verified by reading the file this session) and can create a reconnect storm.

### Pattern 6: Client-accumulated sparkline
**What:** A capped in-memory array per ticker, rendered as an inline SVG `<polyline>`.
**When to use:** Inside each `WatchlistRow`, fed by the shared `usePriceStream` state.
**Example:**
```typescript
// components/Sparkline.tsx
// Source: community pattern, WebSearch, LOW confidence
'use client';

const MAX_POINTS = 60;

export function Sparkline({ points }: { points: number[] }) {
  const capped = points.slice(-MAX_POINTS);
  if (capped.length < 2) {
    return <svg width="60" height="20" className="opacity-40">
      <line x1="0" y1="10" x2="60" y2="10" stroke="currentColor" strokeWidth="1" />
    </svg>;
  }

  const min = Math.min(...capped);
  const max = Math.max(...capped);
  const range = max - min || 1; // epsilon-guard flat lines

  const coords = capped
    .map((p, i) => {
      const x = (i / (capped.length - 1)) * 60;
      const y = 20 - ((p - min) / range) * 20;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg width="60" height="20">
      <polyline points={coords} fill="none" stroke="#209dd7" strokeWidth="1.5" />
    </svg>
  );
}
```
Maintain the underlying `points: number[]` array in the parent (`WatchlistRow` or a ticker→points map in `WatchlistPanel`), appending one value per SSE tick for that ticker — **never reset it on re-render**, only on unmount/ticker-removal, per WATCH-04 and the UI-SPEC's "populated" sparkline row ("never resets on component re-render").

### Anti-Patterns to Avoid
- **Sharing one `sqlite3.Connection` across requests/threads:** Not thread-safe without `check_same_thread=False` + external locking; open-per-call inside `asyncio.to_thread` instead (Pattern 2).
- **Rebuilding `EventSource` manually on error:** Fights the browser's native retry; only ever call `.close()` on component unmount (Pattern 5).
- **Duplicating the ticker list in a literal `seed.sql`:** Violates CONTEXT.md's single-source-of-truth instruction; import `SEED_PRICES` in Python seed logic instead (Pattern 3).
- **Building placeholder trade/chat/portfolio panels "for later phases":** CONTEXT.md explicitly says stub these absent, not placeholder-rendered.
- **Global `PriceCache` singleton:** `ARCHITECTURE.md`'s documented anti-pattern (read this session) — always pass `PriceCache` as an explicit constructed value closed over by `lifespan` and router factories, never a module-level global.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE event framing/reconnect signaling | A custom `text/event-stream` writer | Already built: `backend/app/market/stream.py:create_stream_router()` | Fully implemented, includes retry directive and disconnect detection — this phase only mounts it |
| SSE client reconnect logic | Custom exponential backoff / manual reconnect loop | Native browser `EventSource` retry | STREAM-02 explicitly relies on this; hand-rolled retry logic is extra surface area for a solved problem |
| Market data source selection/lifecycle | A new simulator/poller | `create_market_data_source(cache)` + `MarketDataSource` interface | Already implemented and tested; this phase only calls `start()`/`add_ticker()`/`remove_ticker()`/`stop()` |
| Tailwind autoprefixing | A manual vendor-prefix step or standalone `autoprefixer` config | `@tailwindcss/postcss` (v4 bundles it) | Avoids an unnecessary dependency and a stale v3-era config shape |

**Key insight:** This phase's actual net-new backend logic is small — a DB init/seed function, a WAL-aware connection factory, and one watchlist router. The temptation is to over-build around the already-solid `market/` subsystem; resist it and treat it as a frozen dependency.

## Common Pitfalls

### Pitfall 1: Stale, git-tracked `db/finally.db` silently blocks re-seeding
**What goes wrong:** Lazy-init logic checks "do tables exist?" — if yes, it skips seeding. The currently-committed `db/finally.db` already has all six tables (confirmed this session: `users_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages` all present) but with polluted data: 12 watchlist rows (not the canonical 10), 2 phantom `positions` rows, 2 phantom `trades` rows.
**Why it happens:** An earlier scaffolding step committed the runtime SQLite file, and `.gitignore` only excludes the Django-leftover pattern `db.sqlite3` (confirmed this session by reading `.gitignore` in full) — it does not match `finally.db`, so every future `git status`/`git add` would keep tracking it.
**How to avoid:** Early task: `git rm --cached db/finally.db` (and any `-shm`/`-wal`/`-journal` sidecars if tracked), delete the working-tree file, add `db/.gitkeep`, and add `finally.db`, `finally.db-shm`, `finally.db-wal`, `finally.db-journal` patterns to `.gitignore`.
**Warning signs:** Fresh `git clone` + first backend run shows 12 watchlist tickers instead of 10, or shows phantom positions/trades that no Phase-1-or-later code created.

### Pitfall 2: `httpx` missing breaks `TestClient`-based route tests
**What goes wrong:** Any test importing `fastapi.testclient.TestClient` raises `RuntimeError`/`ModuleNotFoundError` at collection time, failing the whole test file (or, depending on pytest config, the whole run).
**Why it happens:** `httpx` was never added as a dependency for this backend — confirmed this session: `grep '^name = ' backend/uv.lock` lists 37 packages and `httpx` is not among them; `uv run python -c "import httpx"` raises `ModuleNotFoundError` in the actual project environment. FastAPI's own testing docs (Context7-fetched this session) confirm `TestClient` requires `httpx` to be installed separately.
**How to avoid:** Add `httpx` to `backend/pyproject.toml`'s `[project.optional-dependencies].dev` list before writing any route tests; run `uv sync --extra dev` (or `uv add --optional dev httpx`) as an early task.
**Warning signs:** `pytest` errors mentioning `starlette.testclient` requiring `httpx`, or a bare `ModuleNotFoundError: No module named 'httpx'`.

### Pitfall 3: `backend/app/routes/`, `backend/app/llm/`, and `backend/db/` don't actually exist yet
**What goes wrong:** Planner or executor assumes these are pre-existing empty package directories (as `STRUCTURE.md`'s codebase map states) and writes `import` statements or file-edit instructions against paths that don't exist, causing `ModuleNotFoundError` or file-not-found errors.
**Why it happens:** The codebase map (`.planning/codebase/STRUCTURE.md`) was generated before these directories were scaffolded and describes an intended future structure, not the current one.
**How to avoid:** Verified this session via `find backend/app -type d` — only `backend/app/market/` exists alongside `backend/app/__init__.py`. Plans must include explicit "create directory + `__init__.py`" steps for `backend/app/routes/` and `backend/app/db/` (and, when Phase 4 arrives, `backend/app/llm/`).
**Warning signs:** `ImportError` on `from app.routes.watchlist import ...` before the file/package has been created.

### Pitfall 4: CORS in local development (frontend on :3000, backend on :8000, static export forbids `rewrites`)
**What goes wrong:** `next dev` serves the frontend on `localhost:3000` while FastAPI runs on `localhost:8000` during this phase (Docker packaging with a single origin is Phase 5). Fetching `/api/watchlist` from the browser without CORS configured will fail with a browser CORS error. `next.config.js` `rewrites`-based proxying is documented (Context7-verified this session, `output: 'export'` config validation) to not reliably work once `output: 'export'` is set, since rewrites require a Node.js server at request time.
**Why it happens:** Static export and cross-origin dev serving are in tension — the production shape (single origin, no CORS) is not the shape this phase runs in during development.
**How to avoid:** Add `CORSMiddleware` to the FastAPI app allowing `http://localhost:3000` (Context7-verified pattern, `fastapi.tiangolo.com/tutorial/cors`) for local development. Point the frontend's fetch calls at an env-driven base URL (`process.env.NEXT_PUBLIC_API_URL ?? ''`) so it defaults to same-origin relative paths once Phase 5 serves both from one origin, and to `http://localhost:8000` during local dev.
**Warning signs:** Browser console CORS errors on every `/api/*` fetch during `npm run dev`.

### Pitfall 5: Assuming `create-next-app --tailwind` produces the v4 CSS-first config
**What goes wrong:** Depending on the exact `create-next-app` version resolved at install time, the `--tailwind` flag may scaffold either the v4 flow (verified current via `npm view tailwindcss version` → `4.3.3`, and Context7-fetched official install docs) or an older v3-style `tailwind.config.js` + three `@tailwind` directives. Copy-pasting v3-era instructions (common in training data and older tutorials) against an actually-installed v4 package silently produces zero styling (directives that don't exist in v4 are simply ignored, not errored).
**Why it happens:** Tailwind's v3→v4 migration changed the install/config shape significantly; a lot of existing tutorial content (and prior model training data) still shows the v3 flow.
**How to avoid:** After scaffolding, inspect `frontend/package.json` for the installed `tailwindcss` major version and `postcss.config.*` for whether it references `@tailwindcss/postcss` (v4) or bare `tailwindcss`+`autoprefixer` (v3); align `globals.css` accordingly (Pattern 4 above).
**Warning signs:** Tailwind utility classes present in JSX but producing no visual effect in the browser.

## Code Examples

Verified patterns from official sources are inlined above in Architecture Patterns 1-6 (each individually source-tagged). No additional standalone examples beyond those.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Tailwind CSS v3: `tailwind.config.js` (JS-based content/theme config) + `npx tailwindcss init -p` + three `@tailwind` directives + separate `autoprefixer` dependency | Tailwind CSS v4: CSS-first config via `@import "tailwindcss";` + `@theme {}` blocks, `@tailwindcss/postcss` single PostCSS plugin, no config file by default | Confirmed current via `npm view tailwindcss version` (4.3.3) and Context7-fetched official install docs, this session | Following v3-era tutorials/training data against an actually-installed v4 package produces an unstyled app with no error |
| Next.js `next export` as a separate CLI step after `next build` | `output: 'export'` in `next.config.js`/`.mjs`, `next build` alone produces the `out/` directory | Since Next.js 13.3 (predates this project; confirmed still current in both v15.1.8 and v16.2.9 docs, Context7-fetched this session) | No separate export command needed; a plan instructing a two-step `build && export` is following stale docs |

**Deprecated/outdated:**
- Tailwind v3's `tailwind.config.js` + `@tailwind` directive trio: still functions under a v3 install but is the wrong shape for the v4 package this project will actually install.
- `next export` as a standalone command: removed as a separate step since Next 13.3; `next build` with `output: 'export'` set is sufficient.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Package names `next`, `react`, `react-dom`, `typescript`, `tailwindcss`, `@tailwindcss/postcss`, `postcss`, `autoprefixer`, `lucide-react`, `eslint`, `eslint-config-next` are the correct, non-hallucinated names for their respective purposes | Standard Stack, Package Legitimacy Audit | Low — these are extremely well-known packages (verified to exist on npm with 30M-270M weekly downloads and official GitHub repos this session), but per protocol the *name* itself came from training knowledge, not a fresh authoritative discovery |
| A2 | stdlib `sqlite3`'s WAL + `busy_timeout` pragma behavior (WAL persists at the file level once set; `busy_timeout` must be reissued per connection) | Architecture Patterns, Pattern 2 | Low-medium — this is standard, long-stable SQLite behavior, but was not re-verified against a freshly fetched doc this session (only cross-checked conceptually); if wrong, DB-03's concurrency guarantee could be weaker than assumed once Phase 2 adds concurrent writers |
| A3 | `EventSource` `onerror` reliably indicates a "reconnecting" (not necessarily "disconnected") state, and the browser auto-retries per the server's `retry:` directive without further JS intervention | Architecture Patterns, Pattern 5; Common Pitfalls | Low-medium — this is standard Web API behavior, but the specific claim about `onerror` firing distinctly from a terminal `CLOSED` state came from WebSearch/community sources (LOW confidence), not a fetched MDN page this session; if the connection-status dot's yellow/red distinction doesn't match observed browser behavior, UI-SPEC's three-state dot may need adjustment |
| A4 | `create-next-app --tailwind` will scaffold *some* Tailwind version, but which major (v3 vs v4 config shape) depends on the CLI's resolved version at install time, not something this research could pin exactly | Common Pitfalls, Pitfall 5 | Medium — if the planner assumes v4 output without the executor verifying, the app may build looking completely unstyled with no build error to signal the problem |
| A5 | Recommending `backend/app/db/` (package-internal) over `backend/db/` (STRUCTURE.md's stated location) for `schema.sql` | Architecture Patterns, Recommended Project Structure | Low — purely organizational; either works, but plans/executors must agree on one location, not split between assumptions |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **Should `backend/db/` (per `STRUCTURE.md`) or `backend/app/db/` (this research's recommendation) house `schema.sql`?**
   - What we know: Neither currently exists on disk (verified this session). CONTEXT.md's phrasing ("create `backend/db/schema.sql`") suggests the top-level location; this research recommends the package-internal location for cleaner resource loading.
   - What's unclear: Whether the planner should follow CONTEXT.md's literal path or this research's suggested refinement.
   - Recommendation: Either is fine functionally; the planner should pick one explicitly in PLAN.md so the executor doesn't have to guess, and should note it does not collide with the repo-root `db/` runtime volume-mount directory (a third, unrelated path).

2. **Does the SQLite-backed `GET /api/watchlist` response need to merge in current `PriceCache` prices, or is it watchlist metadata only (tickers), leaving initial prices to arrive via the first SSE tick?**
   - What we know: WATCH-04/UI-SPEC's "partial" state row explicitly says a newly-added ticker shows `--` until its first SSE tick arrives — implying the REST endpoint does *not* need to embed live prices.
   - What's unclear: Whether the initial page-load grid should show `--`/skeleton until the first SSE payload arrives for *all* rows (simpler, consistent with the "partial" UI-consideration row) or whether `GET /api/watchlist` should read `PriceCache.get_all()` server-side to pre-populate prices before the first SSE tick (faster perceived load).
   - Recommendation: Prefer the simpler option (`GET /api/watchlist` returns tickers only; all price cells start as skeleton/`--` and populate from the first SSE message) — it matches the UI-SPEC's documented loading-state treatment exactly and avoids a second code path for "price at request time."

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Next.js frontend build/dev | ✓ | v24.18.0 (verified: `node --version`) | — |
| npm | Frontend package installs | ✓ | 11.16.0 (verified: `npm --version`) | — |
| Python (via `uv`) | Backend | ✓ | 3.13.3, resolved by `uv run python --version` (satisfies `requires-python = ">=3.12"`) | — |
| `uv` | Backend package/venv management | ✓ | 0.11.32 (verified: `uv --version`) | — |
| stdlib `sqlite3` | DB-01/02/03 | ✓ | SQLite 3.49.1, verified via `uv run python -c "import sqlite3; print(sqlite3.sqlite_version)"` — supports WAL and busy_timeout | — |
| `sqlite3` CLI (for manual inspection during development, not required by the app itself) | Debugging only | ✓ | 3.51.0 (verified: `sqlite3 --version`) | — |
| `httpx` | Route tests via `TestClient` | ✗ | — (confirmed missing from `uv.lock`, confirmed `ModuleNotFoundError` in the live environment) | Add via `uv add --optional dev httpx` — no viable fallback for `TestClient`-based tests without it |
| Docker | Not required this phase (Phase 5 scope) | n/a | — | — |

**Missing dependencies with no fallback:**
- `httpx` — must be added as a dev dependency; there is no way to use FastAPI's `TestClient` without it. (Alternative: use `httpx.AsyncClient` + `ASGITransport` directly for async tests, per FastAPI's own async-testing docs — still requires installing `httpx`, so this isn't really a fallback, just a different API surface once installed.)

**Missing dependencies with fallback:**
- None — the one missing dependency (`httpx`) has no viable fallback; it must simply be installed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.0+ with pytest-asyncio 0.24.0+ (`asyncio_mode = "auto"`), verified in `backend/pyproject.toml`, read this session |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `cd backend && uv run --extra dev pytest -v` |
| Full suite command | `cd backend && uv run --extra dev pytest --cov=app` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DB-01 | All six tables exist after `init_db()` runs against a fresh temp DB path | unit | `uv run --extra dev pytest tests/db/test_init.py::test_all_tables_created -x` | ❌ Wave 0 |
| DB-02 | Calling `init_db()` twice does not duplicate seed rows (idempotent) | unit | `uv run --extra dev pytest tests/db/test_init.py::test_init_is_idempotent -x` | ❌ Wave 0 |
| DB-03 | A connection opened via the factory reports `journal_mode=wal` and the configured `busy_timeout` | unit | `uv run --extra dev pytest tests/db/test_connection.py::test_wal_and_busy_timeout -x` | ❌ Wave 0 |
| STREAM-01 | `GET /api/stream/prices`, mounted on the real app, returns `text/event-stream` and at least one `data:` frame containing seeded tickers | integration (`TestClient`) | `uv run --extra dev pytest tests/routes/test_stream_mount.py::test_stream_endpoint_mounted -x` | ❌ Wave 0 (requires `httpx` — see Pitfall 2) |
| STREAM-02 | Not independently backend-testable (browser `EventSource` retry is a client behavior) | manual/E2E-only | — (covered by Phase 5's Playwright SSE-reconnect scenario per `PLAN.md` §12; this phase can only assert the server emits the `retry:` directive, already true in existing `stream.py`) | n/a |
| WATCH-01 | `init_db()` seeds exactly the 10 tickers from `SEED_PRICES`, in its key order | unit | `uv run --extra dev pytest tests/db/test_init.py::test_seeds_ten_default_tickers -x` | ❌ Wave 0 |
| WATCH-02 | `POST /api/watchlist` with a new ticker persists a row AND calls `source.add_ticker()` | integration | `uv run --extra dev pytest tests/routes/test_watchlist.py::test_add_ticker_persists_and_calls_source -x` | ❌ Wave 0 |
| WATCH-03 | `DELETE /api/watchlist/{ticker}` removes the row AND calls `source.remove_ticker()` | integration | `uv run --extra dev pytest tests/routes/test_watchlist.py::test_remove_ticker_persists_and_calls_source -x` | ❌ Wave 0 |
| WATCH-04 | Frontend sparkline/price-flash rendering — no backend requirement id maps to server-testable behavior | manual/UAT | Frontend automated component tests (TEST-03) are explicitly scoped to Phase 5 per `REQUIREMENTS.md` traceability; this phase relies on `/gsd-verify-work` conversational UAT | n/a this phase |
| WATCH-05 | Same as WATCH-04 | manual/UAT | Same as above | n/a this phase |
| UI-01 | Same as WATCH-04/05 — visual/layout requirement | manual/UAT | Same as above | n/a this phase |

### Sampling Rate
- **Per task commit:** `cd backend && uv run --extra dev pytest -v` (backend tasks); no automated frontend test command exists yet this phase — rely on `npm run build` succeeding + manual browser check for frontend tasks
- **Per wave merge:** `cd backend && uv run --extra dev pytest --cov=app`
- **Phase gate:** Full backend suite green before `/gsd-verify-work`; frontend acceptance is UAT-driven this phase (formal frontend test framework arrives with TEST-03 in Phase 5, per `REQUIREMENTS.md` traceability — confirmed by reading that file this session)

### Wave 0 Gaps
- [ ] `backend/tests/db/__init__.py`, `test_init.py`, `test_connection.py` — new package, covers DB-01/02/03
- [ ] `backend/tests/routes/__init__.py`, `test_watchlist.py`, `test_stream_mount.py` — new package, covers STREAM-01/WATCH-02/WATCH-03
- [ ] `backend/tests/conftest.py` — needs a new fixture providing a temp SQLite path per test (so tests don't touch the real `db/finally.db`) and possibly a fixture building the FastAPI `TestClient` with a lifespan override
- [ ] Dependency install: `cd backend && uv add --optional dev httpx` — required before any `TestClient`-based test can even be collected (see Pitfall 2)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | App has no login/auth by design (single hardcoded `user_id="default"`, per `PLAN.md`/`REQUIREMENTS.md` Out of Scope) |
| V3 Session Management | No | No sessions/cookies introduced this phase |
| V4 Access Control | No | Single-user, no authorization boundaries to enforce |
| V5 Input Validation | Yes | Ticker symbols must be validated server-side before DB write or market-source call — regex-constrain to plausible ticker shape (e.g. 1-10 uppercase alphanumeric characters, matching the UI-SPEC's client-side cap/uppercase behavior) before it ever reaches SQL or `add_ticker()` |
| V6 Cryptography | No | No secrets/crypto operations introduced this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SQL injection via ticker/user_id string interpolation | Tampering | Always use parameterized queries (`?` placeholders) with stdlib `sqlite3` — never f-string/format SQL, even for a values that "look like" a ticker symbol |
| Path/route-parameter injection via `DELETE /api/watchlist/{ticker}` | Tampering | Validate the `{ticker}` path parameter against the same ticker-shape regex before using it in a query, rejecting anything else with a 4xx |
| CORS misconfiguration allowing arbitrary origins in production | Spoofing/Information Disclosure | The dev-mode `CORSMiddleware` allowlist (Pitfall 4) should only ever include `http://localhost:3000`; do not widen to `allow_origins=["*"]` — and remove/tighten it once Phase 5's single-origin Docker packaging lands |
| Malformed/oversized `POST /api/watchlist` payloads | Denial of Service (minor) | FastAPI/Pydantic request models already reject malformed JSON bodies by default; keep the ticker field a plain `str` with a max-length constraint (Pydantic `Field(max_length=10)`) matching the UI-SPEC's client-side cap |

## Sources

### Primary (HIGH confidence)
- None this session — see Metadata note below on why HIGH is unreached under this project's classify-confidence seam (context7 fetches classify as MEDIUM here, not HIGH).

### Secondary (MEDIUM confidence)
- Context7 `/websites/fastapi_tiangolo` — `fastapi.tiangolo.com/advanced/events` (lifespan pattern), `fastapi.tiangolo.com/tutorial/cors` (CORSMiddleware), `fastapi.tiangolo.com/tutorial/testing` + `fastapi.tiangolo.com/advanced/async-tests` (httpx requirement for TestClient)
- Context7 `/vercel/next.js/v15.1.8` and `/vercel/next.js/v16.2.9` — static-exports.mdx (`output: 'export'` config, confirmed identical across both versions)
- Context7 `/websites/tailwindcss` — `tailwindcss.com/docs/installation/framework-guides/nextjs` (v4 install flow: `@tailwindcss/postcss`, `postcss.config.mjs`), `tailwindcss.com/docs/functions-and-directives` (`@import "tailwindcss";`)
- Live registry checks this session: `npm view <pkg> version` for next, react, react-dom, typescript, tailwindcss, postcss, autoprefixer, lucide-react, eslint, eslint-config-next, @tailwindcss/postcss; `curl https://pypi.org/pypi/httpx/json` for httpx 0.28.1
- Direct tool verification this session: `git ls-files db/`, `.gitignore` full read, `sqlite3`-via-Python row counts on the committed `db/finally.db`, `find backend/app -type d`/`-type f`, `uv run python -c "import httpx"` (fails), `uv run python --version` / `sqlite3.sqlite_version`

### Tertiary (LOW confidence)
- WebSearch: "EventSource SSE client Next.js client component useEffect live updating" (community blog posts, no single canonical Next.js-specific source) — informs Pattern 5
- WebSearch: "accumulating sparkline SVG polyline live streaming data points client side" (community libraries/blog posts) — informs Pattern 6

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — package versions and setup flows confirmed against official docs (Context7) and live registries this session, but package *names themselves* remain training-data-sourced (ASSUMED) per the provenance rule; all flagged SUS by the legitimacy gate on a uniform, low-risk "too-new" signal
- Architecture: MEDIUM-HIGH for the backend half (FastAPI lifespan/CORS patterns CITED against official docs; existing `market/` module behavior VERIFIED by reading the actual source files this session), MEDIUM for the Tailwind v4 setup (CITED, official docs, but genuinely different from most training data), LOW for the two frontend glue patterns with no official doc (EventSource-in-Next.js, sparkline) — both are standard, low-risk, well-understood web patterns despite the low citation-confidence tag
- Pitfalls: HIGH for the two directly-verified environmental gaps (stale `db/finally.db`, missing `httpx`) — confirmed via direct command execution this session, not inference

**Research date:** 2026-08-02
**Valid until:** ~14 days for the frontend package versions (fast-moving — Next.js/Tailwind/React release cadence is frequent per the "too-new" signal observed on every package this session); ~30 days for the backend/FastAPI/SQLite patterns (stable)
