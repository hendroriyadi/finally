# Technology Stack

**Project:** FinAlly — AI Trading Workstation
**Researched:** 2026-08-01

## Recommended Stack

The market-data subsystem (simulator, Massive/Polygon.io client, price cache, FastAPI/uv scaffold) is already built and frozen — this stack covers everything still to build: the SQLite persistence layer, the REST + SSE API surface, the LLM chat integration, and the Next.js frontend.

### Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastAPI | `>=0.136.0` (currently installed `>=0.115.0` / 0.128.7) | REST API, SSE streaming, static file serving | **Upgrade recommended.** FastAPI `0.135.0+` shipped native SSE support (`fastapi.sse.EventSourceResponse` / `ServerSentEvent`) — Pydantic-model streaming with Rust-side serialization, automatic 15s keep-alive pings, and automatic `Cache-Control: no-cache` / `X-Accel-Buffering: no` headers. This removes the need for the third-party `sse-starlette` package for `/api/stream/prices` and is now the officially documented pattern. Confidence: MEDIUM (recent release, verify `fastapi.sse` import exists in the installed version before committing to it; see "Stack Patterns by Variant" below for the fallback). |
| Next.js | `16.2.x` (App Router, static export) | Frontend SPA, built as static HTML/JS/CSS served by FastAPI | Locked in by PLAN.md. `output: 'export'` in `next.config.ts`/`.js` produces a self-contained `out/` directory — no Node server needed at runtime, single origin, no CORS. Requires Node 20.9+ (already the project's pinned Node 20). Confidence: MEDIUM. |
| React | `19.x` (bundled with Next.js 16) | UI library | Ships as Next.js's peer dependency; no separate decision needed. |
| TypeScript | `5.x` | Frontend language | Already decided by PLAN.md; Next.js 16 requires TS `5.1+`. |

### Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SQLite (stdlib file format) | N/A (file-based) | Single-user persistence: profile, watchlist, positions, trades, snapshots, chat history | Locked in by PLAN.md — no auth/multi-user means no need for a DB server. |
| `aiosqlite` | `>=0.20.0` | Async driver wrapping `sqlite3` for use inside FastAPI's event loop | Runs each connection on one dedicated background thread that serializes all operations onto asyncio — this *is* SQLite's single-writer model, expressed naturally as async code. Prevents blocking the event loop (which a bare `sqlite3` call inside an `async def` route would do) without pulling in a full ORM. Use `async with aiosqlite.connect(path) as db:` context managers throughout. Confidence: LOW (no official aiosqlite version-pinning guidance found; version number is a reasonable current pin, not independently verified). |
| `aiosqlite` in WAL mode | — | Concurrent read/write safety | Set `PRAGMA journal_mode=WAL` on the same connection used for lazy init. WAL lets the SSE-driven read paths (portfolio value reads) and the write paths (trade execution, snapshot inserts) coexist without `database is locked` errors, which is the most common SQLite+FastAPI failure mode under concurrent access from multiple route handlers + background tasks. |
| Raw SQL (no ORM) | — | Schema + queries | The schema in PLAN.md §7 is small (6 tables) and stable. A hand-written `CREATE TABLE IF NOT EXISTS` lazy-init block plus small parameterized query functions is simpler than introducing SQLAlchemy/SQLModel for a project this size, and matches "lazy initialization, no migration step" from PLAN.md. Do not add SQLAlchemy unless the schema is expected to grow significantly. |

### AI / LLM Integration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `litellm` | `>=1.90.0` (latest stable `1.94.0`, Jul 2026) | Unified `completion()` call to OpenRouter | Mandated by PLAN.md §9 and the project's `cerebras` skill. **Security note:** litellm `1.82.8` was a confirmed PyPI supply-chain compromise (published and yanked March 2026) — pin well clear of that version; `1.90.0+` / current `1.94.0` postdates the incident and the yank. Confidence: MEDIUM. |
| `pydantic` | `>=2.0` (already a FastAPI dependency) | Structured-output schema definitions (`ChatResponse`, trade/watchlist action models) | Passed directly as the `response_format` argument to `litellm.completion()`; litellm converts the model via `model_json_schema()`/`to_strict_json_schema()` into the OpenAI-style `json_schema` payload. No extra JSON-schema library needed. |
| OpenRouter + Cerebras routing | model `openrouter/openai/gpt-oss-120b` | Fast structured-output inference | Exact call pattern is already validated for this project via the `cerebras` skill — use it verbatim, do not re-derive: `extra_body={"provider": {"order": ["cerebras"]}}`, `reasoning_effort="low"`, `response_format=<PydanticModel>`, then `PydanticModel.model_validate_json(response.choices[0].message.content)`. Note: litellm does not list OpenRouter in its `supports_response_schema()` allowlist, so structured-output support isn't auto-detected for OpenRouter models in general — but the skill's explicit `response_format` + `extra_body` combination is confirmed working for this exact model/provider pairing and is the authoritative pattern for this project. Confidence: HIGH for the call shape (project-validated skill), MEDIUM for the surrounding litellm/OpenRouter compatibility context. |

### Infrastructure

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker (multi-stage) | — | Single container, single port 8000 | Locked in by PLAN.md §11 — Node 20 slim build stage → Python 3.12 slim runtime stage. |
| `uv` | `0.45+` (already in use) | Python dependency/lockfile management | Already the backend's package manager; add `litellm`, `pydantic` (already present via FastAPI), and `aiosqlite` via `uv add`. |

### Supporting Libraries (Frontend)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lightweight-charts` (TradingView) | `5.2.x` | Main detail chart for the selected ticker | Purpose-built canvas financial charting library, ~35KB base bundle, handles high-frequency price-series updates efficiently (designed for exactly this: live-updating OHLC/line series). Use its `LineSeries`/`update()` API to append each SSE tick without re-rendering the whole chart. This is the one place a dedicated financial-chart library earns its weight over a general-purpose one. |
| `recharts` | `2.15.x` | Portfolio heatmap (Treemap), P&L history line chart, watchlist sparklines | Recharts ships a built-in `<Treemap>` component (size = portfolio weight, custom `content` renderer for P&L-based fill color) — there is no need for a separate treemap library. Reuse the same dependency for the P&L line chart and for sparklines (a tiny axis-less `<LineChart>`), rather than adding a third micro-charting package just for sparklines — one charting dependency for all "regular" (non-financial-tick) charts keeps the bundle and API surface smaller. **Caveat:** Recharts' `Treemap` does not support Recharts' `ResponsiveContainer` reliably — give it a fixed `width`/`height` (recalculated on a debounced resize listener if the layout is fluid) rather than relying on responsive auto-sizing. |
| Tailwind CSS | `4.x` | Styling, dark theme | Specified by PLAN.md §10; use CSS custom properties for the three brand colors (`#ecad0a`, `#209dd7`, `#753991`) plus the two dark backgrounds, wired into `tailwind.config` theme extension. |
| native `EventSource` (Web API) | — | SSE client for `/api/stream/prices` | No library needed — `EventSource` has automatic reconnection built in. Must be instantiated only inside a `'use client'` component (it is a browser-only Web API; Next.js static export still pre-renders client components to static HTML on the server side of the build, so guard access with a `useEffect`/mount check, not a top-level call). |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| SSE server implementation | Native FastAPI `fastapi.sse.EventSourceResponse` (≥0.135) | `sse-starlette` | Still a perfectly good, widely-used option and the safer choice if the installed FastAPI version can't be bumped to 0.135+ for any reason (e.g. a transitive dependency pin conflicts). Functionally equivalent for this project's needs (one-way ticker price push); native support is preferred only because it removes a dependency and is now the FastAPI-documented path. |
| Main chart library | `lightweight-charts` | `recharts` for everything (PLAN.md lists both as acceptable) | Recharts is SVG-based and re-renders the DOM on each data point by default; for a chart receiving ticks every ~500ms this is more CPU/DOM-churn than a canvas-based, purpose-built financial library. Recharts remains the better choice for the *other* charts (treemap, P&L, sparklines) where update frequency is much lower (snapshots every 30s) or dataset size is tiny (sparklines). |
| Async SQLite driver | `aiosqlite` | Synchronous `sqlite3` called directly inside `async def` routes | Blocks FastAPI's single event loop thread on every disk I/O — fine at toy load, but wrong pattern to teach/ship in a course capstone. `aiosqlite` costs nothing extra (stdlib-only dependency) and is the standard async-SQLite approach for FastAPI. |
| Async SQLite driver | `aiosqlite` | SQLAlchemy (async) + SQLite | Six small tables, no relational query complexity (no joins beyond simple lookups), and PLAN.md explicitly wants "lazy initialization, no migration step." An ORM is unnecessary ceremony here; add it only if the schema grows materially. |
| LLM structured output | `litellm.completion(response_format=<PydanticModel>)` | Instructor / raw `httpx` calls to OpenRouter | PLAN.md and the project's `cerebras` skill already mandate LiteLLM; no reason to introduce another structured-output layer on top. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `litellm==1.82.8` (or any version from that release window) | Confirmed PyPI supply-chain compromise, published and yanked March 2026 | Pin `litellm>=1.90.0` (current stable `1.94.0`) |
| WebSockets for price streaming | PLAN.md explicitly rejects this — one-way push doesn't need bidirectional complexity | Server-Sent Events via native `EventSource` + FastAPI's SSE response |
| SQLAlchemy/SQLModel for this schema | Unneeded ORM ceremony for 6 small tables and a "no migrations" requirement | Raw parameterized SQL via `aiosqlite` |
| A separate sparkline micro-library (e.g. `microcharts`, `react-sparklines`) | Adds a second charting dependency and a second API surface to learn/maintain for a feature that Recharts' `<LineChart>` already covers with axes/tooltip hidden | Recharts `<LineChart>` (already needed for treemap + P&L chart) |
| Trade confirmation modals / order books / limit orders | Explicitly out of scope per PLAN.md — market orders only, zero-stakes simulated cash | Direct instant-fill execution at current cached price |
| Postgres or any external DB server | No multi-user requirement; adds an operational dependency (service orchestration) the single-container design is meant to avoid | SQLite file, volume-mounted |
| Blindly trusting LLM-issued trades without server-side validation | Auto-execution is a deliberate PLAN.md feature, but the *validation* (sufficient cash/shares) must still happen server-side in the same trade-execution function used by the manual trade-bar endpoint — never execute an LLM-proposed trade via a separate, less-validated code path | Route both manual trades and LLM-issued trades through one shared, validated `execute_trade()` function |

## Stack Patterns by Variant

**If the installed FastAPI version cannot be bumped to `>=0.135.0`:**
- Use `sse-starlette`'s `EventSourceResponse` instead of `fastapi.sse.EventSourceResponse`
- Because the response contract (one `data:` frame per price tick, `EventSource`-compatible) is identical either way — the fallback is a drop-in swap of the response class construction, not an architecture change

**If Recharts' `Treemap` proves awkward with dynamic portfolio sizes (rectangles too thin to read at >12 positions):**
- Cap heatmap cells or group small positions into an "Other" bucket, or switch to a dedicated treemap-only library (`@visx/hierarchy` / `d3-hierarchy` driven manually)
- Because Recharts' Treemap aspect-ratio algorithm degrades visually well before a general D3-based layout does, but this project ships with a 10-ticker default watchlist, so it is unlikely to be needed at MVP

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| Next.js 16.2.x | Node.js 20.9+ | Already satisfied — Docker build stage 1 already targets Node 20 slim per PLAN.md §11 |
| Next.js 16.2.x + `output: 'export'` | `next/image` | Requires a custom or `unoptimized: true` image loader — static export has no server-side image optimization endpoint. Not a blocker here (no user-uploaded images), but note if ticker logos are added later. |
| FastAPI `>=0.136.0` | Python 3.10+ | Already satisfied — backend is on Python 3.12 |
| `litellm>=1.90.0` | `pydantic>=2.0` | Already satisfied — FastAPI already pulls in Pydantic 2.x |
| `aiosqlite` | stdlib `sqlite3` (bundled with Python) | No separate native SQLite binary needed; works with the same `db/finally.db` file path FastAPI's sync `sqlite3` calls would use |

## Sources

- `/vercel/next.js` (Context7) — `output: 'export'` configuration, static export SPA behavior, Node/TS version requirements. Confidence: MEDIUM
- `/berriai/litellm` (Context7) — `response_format` → OpenAI `json_schema` payload construction, Pydantic model conversion internals. Confidence: MEDIUM
- `fastapi.tiangolo.com/tutorial/server-sent-events/` (WebFetch, official docs) + cross-checked via web search — native `fastapi.sse.EventSourceResponse`, version `0.135.0+`, keep-alive/header behavior. Confidence: MEDIUM (verified against official docs)
- Web search (general, uncurated) — Next.js 16.2.x current stable version/Node requirement, `lightweight-charts` 5.2.0, `litellm` 1.94.0 current stable + the 1.82.8 supply-chain-compromise incident, `aiosqlite` async single-writer pattern, Recharts `Treemap` API and its non-responsive-container caveat. Confidence: LOW–MEDIUM per claim (see individual rows above)
- `.claude/skills/cerebras/` (project-local skill, already validated for this codebase) — the exact LiteLLM/OpenRouter/Cerebras call pattern (`extra_body`, `reasoning_effort`, `response_format`). Confidence: HIGH (project-authoritative, not externally sourced)

---
*Stack research for: FinAlly — AI Trading Workstation (SQLite persistence, REST/SSE API, LLM chat, Next.js frontend)*
*Researched: 2026-08-01*
