# Phase 5: One-Command Ship - Research

**Researched:** 2026-08-04
**Domain:** Docker packaging (multi-stage build, FastAPI static serving, volume persistence), frontend unit testing (Vitest + React Testing Library on Next.js 16 / React 19), containerized Playwright E2E testing
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Current state (verified this session, not assumed)**
- No `Dockerfile`, no `docker-compose.yml`, no `scripts/` directory exist. All are net-new.
- `backend/app/main.py` does not serve static files at all — it mounts four API routers and a
  health endpoint, nothing else. DEPLOY-01's "one port serves both" requires adding a `StaticFiles`
  mount, and that is the single most consequential code change in this phase.
- `frontend` already produces a static export: `next.config.ts` sets `output: 'export'` and
  `images.unoptimized`, and `npm run build` writes `frontend/out/` (verified — `out/404.html` etc.
  exist). No frontend build-config change is needed.
- `NEXT_PUBLIC_API_URL` already defaults to `""` (`frontend/lib/api.ts`'s `API_BASE`), which
  resolves to same-origin relative paths. That default is exactly what the single-container
  deployment needs, so the container must simply not set that variable. No code change.
- `db/` exists with a tracked `.gitkeep`, and `finally.db`/`-shm`/`-wal`/`-journal` are gitignored.
  It is already shaped as the volume mount target.
- `test/` contains only `test/artifacts/{report,results}` — stale Playwright output from some
  earlier run, with no config, no spec files, and no `package.json`. The E2E suite is net-new; those
  two leftover artifact files should be removed and the directory gitignored as part of this phase.
- No frontend test framework is installed anywhere (`frontend/package.json` has no Vitest/Jest/RTL).
  TEST-03 requires adding one — the first new frontend dev dependency since Phase 3's `recharts`.
- Docker 29.6.2 is available in this environment.

**DEPLOY-01: single container, single port**
- Multi-stage `Dockerfile` per PLAN.md §11: a Node stage running `npm ci && npm run build`, then a
  Python stage installing `uv`, running `uv sync`, and copying the Node stage's `frontend/out` in.
- Node base image is Claude's discretion, and PLAN.md's "Node 20 slim" should be treated as
  indicative rather than binding: this project runs Next.js 16 (which requires Node ≥20.9) and was
  developed on Node 24. Pin a version that is definitely new enough — Node 22 or 24 slim — rather than
  copying `20` literally and risking an engine-mismatch failure at image-build time.
- Static mount ordering is the trap to avoid: FastAPI matches routes in declaration order, so a
  catch-all `StaticFiles(html=True)` mounted at `/` must be added *after* all four API routers, or it
  will shadow `/api/*`. The mount must also not break the SSE stream endpoint. Whatever ordering is
  chosen needs a test that hits an API route and a static route through the same app instance.
- Serving path must be environment-tolerant: the static directory exists in the container but not
  in a local `uv run uvicorn` dev session. Mount it conditionally on the directory existing, so a
  developer running the backend alone doesn't get a startup crash — and log which mode was chosen.
- CORS: `main.py`'s existing dev-only middleware carries a comment saying "Phase 5's single-origin
  Docker container removes this." Claude's discretion on whether to actually remove it —
  recommendation is to keep it: it is an exact-origin allowlist to `http://localhost:3000` (never a
  wildcard), it costs nothing in the container where the frontend is same-origin, and removing it
  breaks the `npm run dev` workflow every future contributor uses. If it is kept, update that stale
  comment.

**DEPLOY-02: persistence across restarts**
- `docker run -v finally-data:/app/db ...` per PLAN.md §11, with the backend writing `finally.db` into
  that directory. `FINALLY_DB_PATH` already exists as the override (`app/db/connection.py`), so the
  container sets it to the mounted path rather than relying on the default's path arithmetic
  (`parents[3]` from `connection.py` resolves differently inside the image than in the repo).
- The requirement says "verified against a restart-with-existing-volume scenario" — so this needs an
  actual stop/start/assert cycle, not just a volume flag in a run command.

**DEPLOY-03: start/stop scripts**
- `scripts/start_mac.sh`, `scripts/stop_mac.sh`, `scripts/start_windows.ps1`, `scripts/stop_windows.ps1`
  per PLAN.md §4. All four must be idempotent (PLAN.md §11: "safe to run multiple times").
- Start: build the image if absent or if `--build` is passed, run with the volume, port mapping, and
  `--env-file .env`, print the URL, optionally open a browser. Stop: stop and remove the container but
  never the volume.
- `.env` handling is a real edge case: `--env-file .env` fails hard if the file is missing, and
  `.env` is gitignored so a fresh clone won't have one. The scripts should either create it from an
  example or degrade gracefully — a fresh cloner hitting a cryptic Docker error on their first command
  would defeat the entire point of this phase. There is currently no `.env.example` at the repo
  root (PLAN.md §4 says one should be committed); adding it is in scope.

**TEST-03: frontend component tests**
- Framework choice is Claude's discretion; Vitest + React Testing Library is the recommendation
  (Vitest is the standard pairing for a Vite/Next TS project and needs no Babel config), but any
  framework that runs in CI without a browser is acceptable.
- Required coverage per the requirement text: price flash animation, watchlist CRUD, portfolio display
  calculations, and chat message rendering.
- `ChatPanel` deserves priority: Phase 4's code review found a critical bug in it (a sticky
  `historyError` that permanently masked the transcript) and explicitly noted the component had zero
  test coverage. A regression test for that specific bug — error state, then a successful send, then
  assert the message is visible — is the single highest-value frontend test in this phase.

**TEST-04: Playwright E2E**
- Per PLAN.md §12, a `test/docker-compose.test.yml` spinning up the app container plus a Playwright
  container, keeping browser dependencies out of the production image.
- Runs with `LLM_MOCK=true` — which Phase 4 verified end-to-end, and which is the reason the AI chat
  scenario is testable at all without an API key. `OPENROUTER_API_KEY` resolves empty in this sandbox,
  so no E2E test may depend on a real LLM call.
- Scenarios required by the requirement: fresh start, watchlist add/remove, buy/sell, portfolio
  visualizations, AI chat with trade execution, SSE reconnection.
- The mock's trigger phrases are the contract for the chat E2E scenario: `app/llm/mock.py` matches
  `buy N TICKER`, `sell N TICKER`, `add TICKER to my watchlist`, `remove TICKER from my watchlist`.
  E2E messages must use those exact shapes or the mock returns its no-action response.

### Claude's Discretion
- Node base image tag; Python base image tag (3.12 slim per PLAN.md, or newer).
- Exact `StaticFiles` mounting strategy and how the "directory missing" case is handled.
- Whether to keep or remove the dev CORS middleware (recommendation above: keep, update the comment).
- Frontend test framework and the exact set of component tests beyond the four named areas.
- Playwright project/config layout, and whether E2E runs via `docker-compose.test.yml` only or also
  supports a local run against an already-running container.
- Whether `docker-compose.yml` at the repo root is included (PLAN.md §4 calls it an "optional
  convenience wrapper").
- Whether to add a CI workflow — `.github/` already exists in the repo; wiring the suites into it is a
  reasonable extension but is not named by any requirement.

### Deferred Ideas (OUT OF SCOPE)
- AWS App Runner / Terraform `deploy/` directory — PLAN.md §11 explicitly marks it a stretch goal
  outside the core build.
- Closing out Phases 1-4's deferred live-browser verifications (`/gsd-verify-work 1` through `4`).
  Phase 5's Playwright suite covers much of the same ground automatically, so those may become
  largely redundant once TEST-04 passes — worth re-assessing after this phase rather than before.
- A live-API-key LLM round trip (Phase 4's one genuinely unexercised dependency). Still needs a human
  with a real `OPENROUTER_API_KEY`; nothing in this phase changes that.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEPLOY-01 | Application runs as a single Docker container on port 8000, serving both the API and the static frontend | Multi-stage Dockerfile pattern (Standard Stack, Code Examples), conditional `StaticFiles(html=True)` mount ordering verified against Starlette's own route-priority docs (Architecture Patterns, Pitfall 1), curl-based shell verification (Validation Architecture) |
| DEPLOY-02 | SQLite database persists across container restarts via a volume-mounted `db/` directory, verified against a restart-with-existing-volume scenario | `FINALLY_DB_PATH` override pattern already in `backend/app/db/connection.py` (verified this session), explicit stop/start/assert shell cycle (Code Examples, Validation Architecture) |
| DEPLOY-03 | Start/stop scripts exist for macOS/Linux and Windows to build and run the container idempotently | Idempotent start/stop script pattern with `.env.example` fallback and `docker compose` v2 vs `docker-compose` v1 CLI detection (Architecture Patterns, Common Pitfalls) |
| TEST-03 | Frontend component tests cover price flash animation, watchlist CRUD, portfolio display calculations, and chat message rendering | Vitest + RTL setup verified against the exact bundled Next.js 16.2.12 doc in this repo's `node_modules` (Standard Stack, Code Examples), per-component test targets mapped to `WatchlistRow.tsx`, `AddTickerForm.tsx`/`WatchlistPanel.tsx`, `PositionsTable.tsx`, `ChatPanel.tsx` |
| TEST-04 | Playwright E2E suite (run with `LLM_MOCK=true`) covers: fresh start, watchlist add/remove, buy/sell flow, portfolio visualization, AI chat with trade execution, and SSE reconnection | `docker-compose.test.yml` layout with official Playwright Docker image pinned to the installed `@playwright/test` version, exact mock trigger-phrase contract read from `app/llm/mock.py` (Code Examples, Common Pitfall 8) |
</phase_requirements>

## Summary

Phase 5 adds no product feature — it packages Phases 1-4 into a single container and proves it with
tests. Two decisions dominate the risk surface: how `backend/app/main.py` serves the frontend, and how
the persistence claim gets verified without a browser. Both have concrete, verified answers.

For static serving, the codebase's Next.js export is a **single page** (`frontend/app/page.tsx` is the
only route; `frontend/out/` contains exactly `index.html`, `404.html`, and static assets — verified by
listing the existing `out/` directory this session). That rules out any need for SPA client-side-routing
fallback logic. The correct, minimal tool is Starlette's `StaticFiles(directory=..., html=True)` mounted
at `/` **after** all four `include_router()` calls — Starlette's own docs confirm routes and mounts are
matched in declaration order, and that `html=True` mode automatically serves `index.html` for directory
requests and a custom `404.html` on a miss. FastAPI does ship a newer, purpose-built `app.frontend()` API
(added in FastAPI 0.138.0, refined as recently as 0.141.1 — both within the last ~6 weeks of this research
date), but the installed/locked version is 0.128.7, thirteen minor versions behind. This research
recommends **not** bumping FastAPI mid-final-phase to adopt a ~6-week-old API when the manual
`StaticFiles(html=True)` approach is simple, well-documented, and sufficient for a single-page app — see
State of the Art for the full reasoning and the future-upgrade note.

For persistence, `backend/app/db/connection.py` already has the exact seam this phase needs:
`FINALLY_DB_PATH` (read this session, `get_db_path()`, lines 37-46) overrides the default repo-relative
path. The container should set `FINALLY_DB_PATH=/app/db/finally.db` explicitly rather than depend on the
default's `parents[3]` arithmetic, which resolves differently once the repo layout changes shape inside
the image. DEPLOY-02's claim is only proved by an actual two-container-lifecycle test (start → trade →
stop → start on the same named volume → assert), which is scripted out fully in this document rather than
left to the planner to improvise.

For testing, this repo already ships the exact answer for Vitest setup: `frontend/node_modules/next/dist/
docs/01-app/02-guides/testing/vitest.md`, Next's own bundled guide matching the installed 16.2.12 build,
which was read directly this session. For Playwright, the current official Docker image tag convention is
`mcr.microsoft.com/playwright:v<version>-noble` (Ubuntu 24.04 "Noble", the default since Playwright
v1.47.0) and must be pinned to the exact same version as the `@playwright/test` npm package (currently
`1.62.1`) to avoid a browser/runner version mismatch.

**Primary recommendation:** Ship a multi-stage `Dockerfile` (Node 24 slim builder → `ghcr.io/astral-sh/
uv:python3.13-trixie-slim` runtime) that copies `frontend/out` into `backend/static/`, add a
directory-existence-gated `StaticFiles(html=True)` mount as the *last* line added to `create_app()`,
explicitly set `FINALLY_DB_PATH` in the container, add idempotent shell/PowerShell start-stop scripts with
an `.env.example` fallback, install Vitest + React Testing Library per Next's own bundled guide, and run
Playwright 1.62.1 against the built image via `test/docker-compose.test.yml` using the matching
`-noble` Docker image tag.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Single-port static+API serving (DEPLOY-01) | API/Backend (FastAPI process) | CDN/Static (collapsed into backend) | There is no CDN/edge tier in this single-container deployment; the FastAPI process itself is also the static file server via `StaticFiles`, so "CDN/Static" responsibility folds into the backend tier rather than existing separately |
| SQLite persistence across restarts (DEPLOY-02) | Database/Storage | — | Volume-mounted `db/finally.db`; there is no separate database-server tier in this architecture (SQLite is embedded in the same process) |
| Start/stop scripts and image build (DEPLOY-03) | Infrastructure/Ops (outside the 5 web tiers) | — | Shell/PowerShell scripts orchestrating the Docker CLI on the host — not part of the running application. A common misassignment would be exposing build/restart control through an in-app admin endpoint; that is explicitly out of scope here |
| Frontend component tests (TEST-03) | Browser/Client | — | Tests render React components in `jsdom`; nothing under test talks to a real server (fetches are mocked) |
| E2E browser tests (TEST-04) | Browser/Client (Playwright drives a real browser) | API/Backend (assertions verify server-persisted state) | Playwright automates the browser, but several scenarios (buy/sell, watchlist CRUD, chat trade execution) are only meaningfully verified by confirming the backend actually persisted the effect, not just that the DOM updated |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `vitest` | 4.1.10 | Frontend unit test runner | Vite-native, zero Babel config, explicitly documented as the recommended unit-test runner for Next.js App Router projects in this repo's own bundled Next.js docs `[VERIFIED: frontend/node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md]` |
| `@testing-library/react` | 16.3.2 | Component rendering/query API | Named alongside Vitest in the same bundled Next.js doc as the pairing to use `[VERIFIED: frontend/node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md]` |
| `@testing-library/dom` | 10.4.1 | Peer dependency of RTL (query engine) | Explicitly listed in the bundled doc's install command `[VERIFIED: frontend/node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md]` |
| `jsdom` | 30.0.1 | DOM environment for Vitest | The bundled doc's example config sets `environment: 'jsdom'`; jsdom is the dependency that provides it `[VERIFIED: frontend/node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md]` |
| `@vitejs/plugin-react` | 6.0.5 | JSX/Fast Refresh transform for Vite/Vitest | Listed in the bundled doc's install command and example config `[VERIFIED: frontend/node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md]` |
| `vite-tsconfig-paths` | 6.1.1 | Resolves `@/` path aliases inside tests to match `tsconfig.json` | Listed in the bundled doc's TypeScript install command `[VERIFIED: frontend/node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md]` — this repo's components import via `@/components/...` and `@/lib/...`, so this is required, not optional |
| `@testing-library/jest-dom` | 7.0.0 | Custom matchers (`toBeInTheDocument`, `toHaveTextContent`, etc.) | Not in the bundled Next.js doc's minimal example, but is the standard companion for readable assertions `[CITED: context7 /testing-library/testing-library-docs]` — package-legitimacy checked (see audit table) |
| `@testing-library/user-event` | 14.6.3 | Realistic user interaction simulation (typing, clicking) for the `AddTickerForm`/`ChatPanel` tests | Used in the official RTL example test suite fetched this session `[CITED: context7 /testing-library/testing-library-docs]` |
| `@playwright/test` | 1.62.1 | E2E test runner (`test/` directory) | Official Playwright test framework `[CITED: context7 /microsoft/playwright]`; version pinned to exactly match the Docker image tag (see below) |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@vitest/coverage-v8` | 4.1.10 | Coverage reporting for the full-suite gate | Add if the phase gate wants a coverage number; not required to pass TEST-03 itself |

### Base Images (not npm/pip packages, but load-bearing pins)

| Image | Tag | Purpose | Source |
|-------|-----|---------|--------|
| Node (Dockerfile builder stage) | `node:24-slim` | Runs `npm ci && npm run build` to produce `frontend/out/` | Node 24 is Active LTS as of this research date (Node 22 moved to Maintenance LTS in March 2026) and matches this project's local dev Node version (`v24.18.0`, verified this session) `[CITED: WebSearch — Node.js release schedule, cross-checked across multiple sources]` |
| `ghcr.io/astral-sh/uv` | `python3.13-trixie-slim` | Final runtime stage: Python 3.13 + `uv` preinstalled in one image | Astral's official combined uv+Python image family; naming convention confirmed directly from Astral's own docs this session (training data said `-bookworm`, current docs say `-trixie` — a real staleness trap the phase description warned about) `[CITED: docs.astral.sh/uv/guides/integration/docker/]` |
| `mcr.microsoft.com/playwright` | `v1.62.1-noble` | E2E test-runner container (`test/docker-compose.test.yml` only, never the production image) | Official Playwright Docker image; the `-noble` (Ubuntu 24.04) tag has been the default naming template since Playwright v1.47.0, and the version segment must match the installed `@playwright/test` npm version exactly or the browser/runner versions mismatch at runtime `[VERIFIED: context7 /microsoft/playwright — docs/src/docker.md and utils/docker/Dockerfile.noble read directly]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual `StaticFiles(html=True)` mount | FastAPI's native `app.frontend(path, directory=..., fallback="auto")` | Cleaner API, built-in SPA-fallback semantics — but requires bumping FastAPI from the locked 0.128.7 to ≥0.138.0 (ideally ≥0.141.1 for its same-day bugfix), a feature that is roughly 6 weeks old at research time with a same-day post-release bug fix already shipped. Not worth the version-bump risk in the project's final phase for a single-page app that doesn't need SPA fallback routing at all. Documented as the future upgrade path (State of the Art) |
| `vitest` + RTL | Jest + RTL | Jest needs Babel/ts-jest config for this TS/ESM/Next stack that Vitest gets for free via Vite; CONTEXT.md's own recommendation already rules this out unless the planner overrides it |
| `@playwright/test` official Docker image | Installing Playwright + browsers directly in the production `Dockerfile` | Keeps browser binaries and their large OS dependency footprint out of the shipped image — PLAN.md §12 explicitly calls for this separation |
| `ghcr.io/astral-sh/uv:python3.13-trixie-slim` combined image | Plain `python:3.13-slim` + `COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/` | Both are officially documented by Astral; the combined image is one fewer `COPY` line and guarantees the `uv`/Python version pairing was tested together upstream |

**Installation:**
```bash
# Frontend test tooling (run from frontend/)
npm install -D vitest @vitejs/plugin-react jsdom @testing-library/react \
  @testing-library/dom @testing-library/jest-dom @testing-library/user-event \
  vite-tsconfig-paths @vitest/coverage-v8

# E2E tooling (run from test/, a new package.json)
npm install -D @playwright/test@1.62.1
```

No new backend Python dependency is required — `fastapi`, `uvicorn[standard]`, and the rest of
`backend/pyproject.toml` (verified this session) already cover everything this phase needs.

**Version verification:** All frontend package versions above were confirmed via `npm view <package>
version` against the live npm registry this session (2026-08-04). Base image tags were confirmed via
direct `WebFetch`/Context7 reads of the vendors' own current documentation, not training memory — see the
per-row citations above and the FastAPI version discrepancy called out in State of the Art as a concrete
example of why this mattered.

## Package Legitimacy Audit

| Package | Registry | Age (latest publish) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----------------------|-----------|--------------|---------|-------------|
| `vitest` | npm | 2026-07-06 | 88.3M/wk | github.com/vitest-dev/vitest | SUS (`too-new`) | **Kept** — false-positive class: the "too-new" signal fires on the *latest version's* publish date for an actively-maintained package, not package inception; 88M weekly downloads and an official GitHub repo are strong legitimacy signals. Planner should still add a `checkpoint:human-verify` before install per protocol |
| `@vitejs/plugin-react` | npm | 2026-07-30 | 78.1M/wk | github.com/vitejs/vite-plugin-react | SUS (`too-new`) | Kept — same false-positive class as above |
| `jsdom` | npm | 2026-07-29 | 90.6M/wk | github.com/jsdom/jsdom | SUS (`too-new`) | Kept — same false-positive class |
| `@testing-library/react` | npm | 2026-01-19 | 51.6M/wk | github.com/testing-library/react-testing-library | OK | Approved |
| `@testing-library/dom` | npm | 2025-07-27 | 63.7M/wk | github.com/testing-library/dom-testing-library | OK | Approved |
| `@testing-library/jest-dom` | npm | 2026-07-20 | 58.3M/wk | github.com/testing-library/jest-dom | SUS (`too-new`) | Kept — same false-positive class |
| `@testing-library/user-event` | npm | 2026-08-03 | 45.4M/wk | github.com/testing-library/user-event | SUS (`too-new`) | Kept — published the day before this research; still the official Testing Library repo with tens of millions of weekly downloads. Planner should add a `checkpoint:human-verify` before this specific install given the very recent publish date |
| `vite-tsconfig-paths` | npm | 2026-02-11 | 31.0M/wk | github.com/aleclarson/vite-tsconfig-paths | OK | Approved |
| `@vitest/coverage-v8` | npm | 2026-07-06 | 34.0M/wk | github.com/vitest-dev/vitest | SUS (`too-new`) | Kept — same false-positive class (same repo as `vitest`) |
| `@playwright/test` | npm | 2026-07-30 | 52.1M/wk | github.com/microsoft/playwright | SUS (`too-new`) | Kept — same false-positive class; official Microsoft repo |

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `vitest`, `@vitejs/plugin-react`, `jsdom`,
`@testing-library/jest-dom`, `@testing-library/user-event`, `@vitest/coverage-v8`, `@playwright/test` —
all flagged solely by the legitimacy tool's `too-new` heuristic reacting to a *routine recent release* of
an established, extremely high-download package, not by any download-count, missing-repo, or postinstall
signal (all had `postinstall: null`, confirmed via `npm view <pkg> scripts.postinstall` this session, and
`@testing-library/react`/`@testing-library/dom`/`vite-tsconfig-paths` — the only three with older last-
publish dates — cleared as `OK`). The planner must still add a `checkpoint:human-verify` task before each
flagged install per protocol, even though this research assesses the actual risk as low.

## Architecture Patterns

### System Architecture Diagram

```
Developer / student
    │ runs one command
    ▼
scripts/start_mac.sh  (or start_windows.ps1)
    │ 1. ensure .env exists (copy from .env.example if missing)
    │ 2. docker build (if image absent or --build passed)
    │ 3. docker run -d --name finally \
    │      -v finally-data:/app/db -p 8000:8000 --env-file .env finally:latest
    │ 4. print http://localhost:8000, optionally open browser
    ▼
┌───────────────────────────────────────────────────────────────────┐
│ Docker container (single process, port 8000)                      │
│                                                                    │
│  Browser request                                                  │
│    │                                                               │
│    ▼                                                               │
│  uvicorn → FastAPI app (backend/app/main.py::create_app())        │
│    ├─ GET  /api/stream/prices   → SSE router (frozen, Phase 1)    │
│    ├─ /api/watchlist/*          → watchlist router                │
│    ├─ /api/portfolio/*          → portfolio router                │
│    ├─ POST /api/chat            → chat router (LLM_MOCK gate)     │
│    ├─ GET  /api/health          → health endpoint                 │
│    └─ (no /api/* match)         → StaticFiles(html=True) mount    │
│                                    at "/", added LAST so it never  │
│                                    shadows the routes above        │
│                                        │                            │
│                                        ▼                            │
│                                serves backend/static/*             │
│                                (= copied frontend/out/ at build)   │
│                                index.html / 404.html / _next/*     │
│                                                                    │
│  SQLite: FINALLY_DB_PATH=/app/db/finally.db  ◄── volume mount ────┼──► host db/ directory
│  (WAL mode, busy_timeout=5000 — unchanged from Phase 1)           │
└───────────────────────────────────────────────────────────────────┘
```

E2E test flow (separate from the production image):

```
test/docker-compose.test.yml
    │
    ├─ service "app": builds the SAME root Dockerfile
    │    environment: LLM_MOCK=true, FINALLY_DB_PATH=/app/db/finally.db
    │    healthcheck: CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/health')"
    │
    └─ service "playwright": image mcr.microsoft.com/playwright:v1.62.1-noble
         depends_on: app: condition: service_healthy
         environment: BASE_URL=http://app:8000
         command: sh -c "npm ci && npx playwright test"
         volumes: ../test:/work  (working_dir: /work)
              │
              ▼
         test/e2e/*.spec.ts — fresh start, watchlist CRUD, buy/sell,
         portfolio visualizations, AI chat trade (mock phrases), SSE reconnect
```

### Recommended Project Structure

```
finally/
├── Dockerfile                     # NEW — multi-stage: node:24-slim builder → uv/python runtime
├── .dockerignore                  # NEW — excludes node_modules, .venv, frontend/out, .git, db/finally.db*
├── docker-compose.yml             # NEW (discretion) — thin convenience wrapper around `docker run`
├── .env.example                   # NEW — OPENROUTER_API_KEY=, MASSIVE_API_KEY=, LLM_MOCK=false
├── scripts/
│   ├── start_mac.sh                # NEW
│   ├── stop_mac.sh                 # NEW
│   ├── start_windows.ps1           # NEW
│   └── stop_windows.ps1            # NEW
├── backend/
│   ├── static/                     # NEW at build time only (Dockerfile COPY target); .gitignore'd
│   └── app/main.py                 # MODIFIED — + conditional StaticFiles mount, comment fix
├── frontend/
│   ├── vitest.config.ts            # NEW
│   ├── vitest.setup.ts             # NEW — imports @testing-library/jest-dom matchers
│   └── components/*.test.tsx       # NEW — colocated with the component under test
└── test/
    ├── docker-compose.test.yml     # NEW
    ├── package.json                 # NEW — @playwright/test devDependency only
    ├── playwright.config.ts         # NEW — baseURL from process.env.BASE_URL ?? "http://localhost:8000"
    └── e2e/
        ├── fresh-start.spec.ts
        ├── watchlist.spec.ts
        ├── trading.spec.ts
        ├── portfolio-viz.spec.ts
        ├── chat.spec.ts
        └── sse-reconnect.spec.ts
```

### Pattern 1: Directory-gated StaticFiles mount, added last

**What:** Guard the `StaticFiles` mount behind an existence check on the static directory, and add it as
the final line in `create_app()`, after every `include_router()` call.
**When to use:** Always for DEPLOY-01 — this is the one code change to `backend/app/main.py`.
**Why it's safe:** Starlette (which FastAPI is built on) matches routes and mounts in the order they were
added; the docs read directly this session state plainly: *"When matching incoming paths, routes are
tested in the order they appear... more specific routes should be listed before general ones"*
`[VERIFIED: context7 /kludex/starlette — docs/routing.md]`. A mount at `/` is about as general as a match
gets, so it must be the last thing added.
**Example:**
```python
# Source: pattern synthesized from Starlette's StaticFiles + routing docs
# [CITED: context7 /kludex/starlette — docs/staticfiles.md, docs/routing.md]
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# backend/static is the Dockerfile's COPY target for frontend/out/ (see Pattern 2).
# Resolved relative to this file so it works regardless of the container's WORKDIR.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app.include_router(create_stream_router(cache))
app.include_router(create_watchlist_router())
app.include_router(create_portfolio_router())
app.include_router(create_chat_router())

@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

# Mounted LAST and only when the directory exists — a bare backend dev session
# (`uv run uvicorn app.main:app`) never gets frontend/out/ copied in, and must not crash.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    logger.info("Serving static frontend from %s", STATIC_DIR)
else:
    logger.info("Static directory %s not found — running API-only (local dev mode)", STATIC_DIR)
```
Starlette's `StaticFiles(html=True)` mode "automatically loads `index.html` for directories" and "in HTML
mode, the application will serve a custom `404.html` file if it is present in the directory"
`[VERIFIED: context7 /kludex/starlette — docs/staticfiles.md]` — both already exist in `frontend/out/`
(verified this session by listing the directory), so no extra fallback-routing code is needed.

### Pattern 2: uv multi-stage Dockerfile

**What:** Node builder stage feeds a `uv`-based Python runtime stage; dependencies are synced before
source is copied in, for Docker layer caching.
**When to use:** The single project `Dockerfile` for DEPLOY-01.
**Example:**
```dockerfile
# Source: pattern from Astral's official uv Docker integration guide
# [CITED: docs.astral.sh/uv/guides/integration/docker/]

# ---- Stage 1: build the static frontend export ----
FROM node:24-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # output: 'export' in next.config.ts writes ./out

# ---- Stage 2: Python runtime with uv preinstalled ----
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS runtime
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# Dependencies first (cacheable layer) — matches Astral's documented two-sync pattern
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Then project source (changes far more often than dependencies)
COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Frontend static export lands where backend/app/main.py's STATIC_DIR expects it
COPY --from=frontend-builder /app/frontend/out ./static

ENV PATH="/app/.venv/bin:$PATH"
ENV FINALLY_DB_PATH=/app/db/finally.db

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
The two-sync split — `--no-install-project` first, then a full sync after `COPY backend/ ./` — is
Astral's own documented pattern: *"The first `uv sync --frozen --no-install-project` installs
dependencies without the project itself... The second `uv sync --frozen` installs the project after
copying source code. When only source code changes... Docker reuses the cached dependency layer"*
`[CITED: docs.astral.sh/uv/guides/integration/docker/]`.

### Pattern 3: Vitest config matching this exact Next.js version

**What:** `vitest.config.ts` using the `jsdom` environment, the React plugin, and `vite-tsconfig-paths` so
`@/components/...` imports resolve inside tests exactly as they do in the app.
**When to use:** TEST-03's framework setup, Wave 0.
**Example:**
```ts
// Source: this repo's own bundled Next.js 16 doc, read directly this session
// [VERIFIED: frontend/node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md]
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths'

export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
  },
})
```
```ts
// frontend/vitest.setup.ts
import '@testing-library/jest-dom/vitest'
```
```json
// frontend/package.json — add alongside existing scripts (verified this session, lines 5-10)
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```
> **Good to know**, quoted directly from the same bundled doc: *"Since `async` Server Components are new
> to the React ecosystem, Vitest currently does not support them... we recommend using E2E tests for
> `async` components."* `[VERIFIED: frontend/node_modules/next/dist/docs/01-app/02-guides/testing/
> vitest.md]` — not a concern here since every component under test (`WatchlistRow`, `PositionsTable`,
> `ChatPanel`, `AddTickerForm`) is a `"use client"` component (verified by reading each file this
> session), not an async Server Component.

### Pattern 4: A regression test for the ChatPanel bug Phase 4's review found

**What:** `ChatPanel` renders messages whenever `messages !== null && messages.length > 0`, checking that
condition *before* `historyError` — reading the component this session (lines 194-200) confirms the
comment explaining why: *"Messages win over `historyError` whenever any exist... The error is only the
right thing to show when there is genuinely nothing else."* This is exactly the bug Phase 4's code review
caught (a sticky `historyError` permanently masking the transcript) and the fix that landed. A test should
lock this in.
**When to use:** TEST-03's highest-priority test per CONTEXT.md.
**Example:**
```tsx
// Source: pattern from React Testing Library's own async-query guidance
// [CITED: context7 /testing-library/testing-library-docs — react-testing-library/faq.mdx]
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi, test, expect, beforeEach } from 'vitest'
import { ChatPanel } from '@/components/ChatPanel'
import * as api from '@/lib/api'

test('a successful send still shows the transcript after a failed history load (CR-01 regression)', async () => {
  vi.spyOn(api, 'fetchChatHistory').mockRejectedValueOnce(new Error('network'))
  vi.spyOn(api, 'sendChatMessage').mockResolvedValueOnce({
    message: 'Done.',
    actions: [],
  })

  render(<ChatPanel />)

  // historyError renders first (mount fetch rejected)
  expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't load your conversation/i)

  const user = userEvent.setup()
  await user.type(screen.getByPlaceholderText(/ask finally/i), 'hello{enter}')

  // The reply must become visible — NOT stuck behind the stale history error
  expect(await screen.findByText('Done.')).toBeInTheDocument()
  expect(screen.queryByText(/couldn't load your conversation/i)).not.toBeInTheDocument()
})
```
Note the use of `findByRole`/`findByText` (async, auto-waiting) rather than `getBy...` — this repo's
`ChatPanel` fetches history in a `useEffect` on mount (verified this session, lines 45-68), and RTL's own
FAQ warns that asserting before that promise resolves produces "not wrapped in `act`" warnings; the fix is
exactly this async-query pattern `[CITED: context7 /testing-library/testing-library-docs — react-testing-
library/faq.mdx]`.

### Pattern 5: DEPLOY-02's persistence proof — a real two-lifecycle shell script

**What:** Not a unit test — a shell script that starts a container, writes state through the real trade
API, stops and removes the container (keeping the named volume), starts a fresh container on the same
volume, and asserts the state survived.
**When to use:** DEPLOY-02 verification; also usable as the Validation Architecture's automated check.
**Example:**
```bash
#!/usr/bin/env bash
# test/verify-persistence.sh — proves DEPLOY-02, not just that `-v` was passed.
# Request/response shapes verified this session:
#   POST /api/portfolio/trade body {ticker, side, quantity} -> TradeResponse
#   (backend/app/routes/portfolio.py:37 TradeRequest, :106 POST "/trade")
#   GET  /api/portfolio -> PortfolioResponse with a "positions" list
set -euo pipefail

VOLUME=finally-verify-data
IMAGE=finally:verify

docker volume rm -f "$VOLUME" >/dev/null 2>&1 || true
docker rm -f finally-verify-1 finally-verify-2 >/dev/null 2>&1 || true

docker build -t "$IMAGE" .

docker run -d --name finally-verify-1 -v "$VOLUME:/app/db" -p 8000:8000 \
  -e LLM_MOCK=true "$IMAGE"
until curl -sf http://localhost:8000/api/health >/dev/null; do sleep 0.5; done

curl -sf -X POST http://localhost:8000/api/portfolio/trade \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","side":"buy","quantity":1}' >/dev/null

BEFORE=$(curl -sf http://localhost:8000/api/portfolio | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["positions"])')

docker stop finally-verify-1 >/dev/null
docker rm finally-verify-1 >/dev/null

docker run -d --name finally-verify-2 -v "$VOLUME:/app/db" -p 8000:8000 \
  -e LLM_MOCK=true "$IMAGE"
until curl -sf http://localhost:8000/api/health >/dev/null; do sleep 0.5; done

AFTER=$(curl -sf http://localhost:8000/api/portfolio | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["positions"])')

docker stop finally-verify-2 >/dev/null
docker rm finally-verify-2 >/dev/null
docker volume rm "$VOLUME" >/dev/null

if [ "$BEFORE" != "$AFTER" ]; then
  echo "FAIL: positions did not survive a stop/start cycle"
  echo "before: $BEFORE"
  echo "after:  $AFTER"
  exit 1
fi
echo "PASS: positions survived a full container stop/start on the same volume"
```
This was **not executed during this research session** (per the task's guidance to prefer static
reasoning and reserve an actual Docker build/run for a claim that genuinely requires it — persistence
requires the phase's own Dockerfile to exist first, which is Wave 1's job, not research's). It is provided
here fully written so the planner/executor does not have to improvise the two-lifecycle shape from a
one-line description.

### Anti-Patterns to Avoid

- **Mounting `StaticFiles` before the API routers:** Shadows every `/api/*` route with a 404 from the
  static handler instead of the real endpoint. Always add it last.
- **Baking `.env` or `db/finally.db` into the image:** Without a `.dockerignore`, the build context
  includes a developer's live database and secrets. `.dockerignore` must exclude `db/*.db*`, `.env`,
  `.venv`, `node_modules`, `frontend/out` (rebuilt fresh in the image), and `.git`.
- **Relying on `FINALLY_DB_PATH`'s default `parents[3]` arithmetic inside the container:** That
  arithmetic assumes the exact repo-relative depth of `backend/app/db/connection.py` from the repo root
  (verified this session, lines 29-32) — a different `WORKDIR`/`COPY` layout inside the image silently
  resolves to the wrong path. Always set `FINALLY_DB_PATH` explicitly as a container `ENV`.
- **Running Playwright browsers inside the production `Dockerfile`:** Bloats the shipped image with
  browser binaries and their OS-level dependencies for zero runtime benefit; PLAN.md §12 already calls
  for keeping this in a separate `test/docker-compose.test.yml`.
- **Pinning `@playwright/test` and the Playwright Docker image to different version numbers:** Produces a
  "browser binary version mismatch" failure at test-run time that looks like a flaky test, not a config
  bug. Keep both pinned to `1.62.1` and bump them together.
- **Using `docker-compose` (hyphenated, standalone v1 binary) unconditionally in the start/stop scripts:**
  The `version:` key and the standalone binary are obsolete; Compose V2 (the `docker compose` plugin,
  confirmed present in this environment: `Docker Compose version v5.3.1`) is what `scripts/start_mac.sh`
  should call, while still tolerating an environment where only the legacy binary exists.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Serving `index.html`/`404.html` for a static export | A custom catch-all FastAPI route with manual `FileResponse` logic | `StaticFiles(directory=..., html=True)` | Starlette's `html=True` mode already does exactly this — auto-serves `index.html` for directory hits and a custom `404.html` on a miss `[VERIFIED: context7 /kludex/starlette]`; a hand-rolled version would have to reimplement path-traversal protection and MIME-type detection that `StaticFiles` already handles |
| Waiting for the app container to be ready before running E2E tests | A hand-written bash polling loop wrapping `docker compose up` | Docker's `HEALTHCHECK` + Compose's `depends_on: condition: service_healthy` | This is exactly what Compose's healthcheck-gated dependency ordering exists for; a custom sleep-loop duplicates it and is easy to get wrong (fixed sleep vs. actual readiness) |
| Installing and managing browser binaries for E2E | Running `npx playwright install --with-deps` inside a custom Dockerfile layer | The official `mcr.microsoft.com/playwright:v<version>-noble` image | Microsoft maintains OS-dependency compatibility and browser-binary pairing for this image as a first-class artifact; hand-rolling it means tracking OS package changes yourself |
| Dependency installation caching in Docker | A hand-rolled `pip freeze > requirements.txt` export step, or copying the whole repo before installing deps | `uv sync --frozen --no-install-project` (deps layer) then `uv sync --frozen` (project layer) | This is Astral's own documented pattern specifically for Docker layer caching `[CITED: docs.astral.sh]`; reinventing it loses the caching benefit or risks a lockfile/requirements drift |
| Waiting for async effects to settle in component tests | `setTimeout`-based sleeps or manually flushing microtasks in test code | RTL's `findBy*`/`waitFor` async queries | Purpose-built for exactly this; a hand-rolled sleep is either too short (flaky) or wastes test time, and RTL's own FAQ names this as the fix for "not wrapped in `act`" warnings `[CITED: context7 /testing-library/testing-library-docs]` |

**Key insight:** Every "don't hand-roll" item in this phase already has an off-the-shelf, officially
documented answer — the risk in Phase 5 isn't a hard algorithmic problem, it's using the *current*
(not remembered) version of each tool's documented pattern, which is why this research leaned on
Context7/WebFetch/in-repo bundled docs for nearly every claim above rather than training memory.

## Common Pitfalls

### Pitfall 1: Static mount shadowing `/api/*`
**What goes wrong:** A `StaticFiles(html=True)` mount at `/` added before (or interleaved with) the API
`include_router()` calls intercepts every request, including `/api/*`, and returns 404s from the static
handler instead of routing to the real endpoints.
**Why it happens:** Starlette matches routes/mounts in declaration order, and a mount at `/` matches
everything (routing docs read this session: *"routes are tested in the order they appear... more specific
routes should be listed before general ones"* `[VERIFIED: context7 /kludex/starlette]`).
**How to avoid:** Add the mount as the literal last statement inside `create_app()`, after all four
`include_router()` calls and the inline `/api/health` route.
**Warning signs:** `/api/health` returns an HTML 404 page (the SPA's `404.html`) instead of a JSON 404 or
a healthy JSON response. A backend test hitting both an API route and `/` through the same `TestClient`
instance (see Validation Architecture) catches this immediately.

### Pitfall 2: `StaticFiles`'s `check_dir=True` default crashing a bare backend dev session
**What goes wrong:** `StaticFiles(directory=...)` defaults to `check_dir=True`, which raises at
construction time if the directory doesn't exist `[VERIFIED: context7 /kludex/starlette — StaticFiles
constructor signature]`. A developer running `uv run uvicorn app.main:app` without ever building the
frontend would crash the app at import time.
**Why it happens:** The container always has `backend/static/` (Dockerfile copies it in); a bare local
`uv run` session never does.
**How to avoid:** Only ever call `StaticFiles(...)` inside an `if STATIC_DIR.is_dir():` guard — this means
`check_dir`'s own raise never triggers, because the constructor is never called on a missing path.
**Warning signs:** `uv run uvicorn app.main:app` fails immediately with `RuntimeError: Directory ... does
not exist` instead of starting the API-only dev server.

### Pitfall 3: Docker build context bloat and secret/data leakage without `.dockerignore`
**What goes wrong:** Without a `.dockerignore`, `docker build .`'s context includes `node_modules/`,
`.venv/`, `frontend/out/` (rebuilt fresh anyway), `.git/`, and — critically — `db/finally.db*`, baking a
developer's live simulated-trading database into the image layer history.
**Why it happens:** Docker's default build context is the entire directory passed to `docker build`.
**How to avoid:** Add a `.dockerignore` at the repo root excluding all of the above plus `.env`.
**Warning signs:** `docker build` takes noticeably longer than expected, or `docker history <image>` shows
a layer with a suspiciously large size attributable to `node_modules`/`.venv`.

### Pitfall 4: `FINALLY_DB_PATH`'s default path arithmetic silently resolving wrong inside the container
**What goes wrong:** If the container relies on `get_db_path()`'s default (`Path(__file__).resolve().
parents[3] / "db" / "finally.db"`, verified this session — quoted below), a different `WORKDIR`/`COPY`
layout inside the image changes what `parents[3]` resolves to, and the app either writes the database
somewhere unexpected inside the container's ephemeral filesystem (data loss on restart, silently) or
raises trying to create a directory it can't.
> `# parents[3] from backend/app/db/connection.py is the repository root, whose`
> `# db/ directory is the runtime volume mount — deliberately distinct from this`
> `# package directory (backend/app/db/), which only holds the schema DDL.`
> `DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "db" / "finally.db"`
> `[VERIFIED: backend/app/db/connection.py:29-32]`
**Why it happens:** The comment itself says this path arithmetic assumes the *repo's* directory depth;
nothing enforces that the container reproduces that same depth.
**How to avoid:** Set `ENV FINALLY_DB_PATH=/app/db/finally.db` explicitly in the Dockerfile — the override
already exists and is read at connection time (verified this session, lines 43-44: `raw = os.environ.get
("FINALLY_DB_PATH", "").strip(); path = Path(raw) if raw else DEFAULT_DB_PATH`).
**Warning signs:** DEPLOY-02's persistence script (Pattern 5) fails — `AFTER` positions don't match
`BEFORE`, or the second container starts with an empty (freshly-seeded) database instead of the prior
state.

### Pitfall 5: `.env` missing on a fresh clone breaks `--env-file .env` hard
**What goes wrong:** `docker run --env-file .env ...` exits with a hard error if `.env` doesn't exist.
`.env` is gitignored (verified this session — `.gitignore` line block "Environments" includes `.env`), so
every fresh clone starts without one, and a first-run script failure defeats the entire point of
"one-command ship."
**Why it happens:** No `.env.example` currently exists at the repo root (verified this session — absent
from `ls -la` of the repo root) despite PLAN.md §4 describing one as committed.
**How to avoid:** `scripts/start_mac.sh`/`start_windows.ps1` should check for `.env` and, if missing, copy
`.env.example` to `.env` (with a printed message that the user should add their `OPENROUTER_API_KEY`)
before invoking `docker run`.
**Warning signs:** A fresh clone's first `./scripts/start_mac.sh` run prints a Docker CLI error about a
missing env file instead of starting the app.

### Pitfall 6: SSE/live-updating UI assertions in Playwright using fixed sleeps
**What goes wrong:** Watchlist prices and portfolio values update from a background SSE stream on their
own cadence; a test using `page.waitForTimeout(2000)` before asserting a price changed is both slow and
flaky (the update might land at 2001ms, or might land twice before the assertion runs).
**Why it happens:** SSE pushes are asynchronous and not driven by any user action the test controls.
**How to avoid:** Use Playwright's auto-retrying `expect(locator).not.toHaveText(initialText)` /
`toBeVisible()` assertions, which poll until the condition is true or a timeout elapses, rather than a
fixed sleep.
**Warning signs:** The SSE-reconnection scenario passes locally but is flaky in the Docker Compose E2E
run, where container-to-container network timing differs from a local dev loop.

### Pitfall 7: React 19 `act()` warnings from unresolved effects in Vitest
**What goes wrong:** `ChatPanel` (and `WatchlistPanel`) fetch on mount inside a `useEffect` (verified this
session — `ChatPanel.tsx` lines 45-68 use a `.then()`-chain fetch effect, not an awaited async call, to
satisfy `eslint-config-next` 16's `react-hooks/set-state-in-effect` rule per this repo's established
pattern). A test that asserts synchronously right after `render()` runs before that promise resolves,
producing a `not wrapped in act(...)` warning and asserting against stale (pre-fetch) UI state.
**Why it happens:** `render()` from RTL is synchronous; the mount effect's fetch is not.
**How to avoid:** Always assert post-fetch UI state with `findBy*` (async, auto-waiting) queries, never
`getBy*`, when a component fetches on mount — matching the pattern already used in Pattern 4 above.
**Warning signs:** Test output includes `Warning: An update to ChatPanel inside a test was not wrapped in
act(...)`.

### Pitfall 8: LLM_MOCK's exact trigger-phrase contract
**What goes wrong:** The Playwright chat E2E scenario sends a message like "Can you buy some AAPL for
me?" expecting a trade to execute — but `app/llm/mock.py`'s regex requires the exact shape `buy N TICKER`
(verified this session, lines 26-29: `_BUY_RE = re.compile(r"\bbuy\s+(\d+(?:\.\d+)?)\s+(?:shares?\s+of\s+)
?([a-z.]{1,10})\b", re.I)`). A looser phrasing silently returns the mock's no-action message instead of
executing a trade, and the test's "trade executed" assertion fails — or worse, is written loosely enough
to pass anyway, testing nothing.
**Why it happens:** The mock is a deliberately simple keyword matcher, not an NLU layer (documented in the
module's own docstring, read this session).
**How to avoid:** E2E chat messages must use one of the four exact shapes: `buy N TICKER`, `sell N
TICKER`, `add TICKER to my watchlist`, `remove TICKER from my watchlist` (case-insensitive; ticker matched
as `[a-z.]{1,10}`).
**Warning signs:** The chat E2E test's inline `ChatActionCard` assertion never finds a rendered action
card, or the assistant reply is literally *"This is a mock response (LLM_MOCK=true) — ask me to buy/sell a
ticker or update your watchlist."* (verified this session — `app/llm/mock.py` line 32-35, the exact
`_MOCK_NO_ACTION_MESSAGE` string).

### Pitfall 9: Docker Compose v1/v2 CLI mismatch in start/stop scripts
**What goes wrong:** A script that calls `docker-compose` (hyphenated, the deprecated standalone v1
binary) fails on a machine that only has the Compose V2 plugin (`docker compose`, space-separated) — or
vice versa on an older machine.
**Why it happens:** `version:` and the standalone binary are obsolete as of Compose V2 (GA 2022), but not
every environment has migrated `[CITED: WebSearch — Docker Compose version-key deprecation, cross-checked
across docs.docker.com and multiple independent sources]`. This environment confirmed `Docker Compose
version v5.3.1` (the V2 plugin) this session.
**How to avoid:** DEPLOY-01/03's scripts and Dockerfile only need `docker build`/`docker run` (no compose
required for the production path at all — compose is only used by `test/docker-compose.test.yml`, which
can assume V2 since it's a project-internal test-only file, not a student's first-run path). If a root
`docker-compose.yml` convenience wrapper is added (discretionary), prefer `docker compose` syntax without
a `version:` key.
**Warning signs:** `docker-compose: command not found` on a machine with only the V2 plugin installed.

### Pitfall 10: Committing stale `test/artifacts/` output
**What goes wrong:** `test/artifacts/{report,results}` (two files, verified present this session, from
some earlier ungoverned Playwright run) sit untracked-but-not-ignored; a future `git add -A` would commit
stale, environment-specific test output.
**Why it happens:** No `.gitignore` entry exists for `test/artifacts/` yet (verified this session — absent
from `.gitignore`'s contents).
**How to avoid:** Delete the two existing files and add `test/artifacts/` to `.gitignore` as part of this
phase's housekeeping, before `test/docker-compose.test.yml` starts producing new (correct) output there.
**Warning signs:** `git status` shows `test/artifacts/...` as untracked after running the new E2E suite.

## Code Examples

Verified patterns from official sources (also embedded above under Architecture Patterns — collected here
for quick reference):

### Playwright config with an environment-driven base URL (supports both compose and local runs)
```ts
// test/playwright.config.ts
// Source: pattern per Playwright's own project-config conventions
// [CITED: context7 /microsoft/playwright]
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // shared SQLite state across specs — avoid cross-test races
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:8000',
    trace: 'on-first-retry',
  },
  reporter: [['html', { outputFolder: '../test/artifacts/report' }]],
})
```

### `test/docker-compose.test.yml`
```yaml
# Source: pattern combining Compose's documented healthcheck-gated depends_on
# with Playwright's official Docker image
# [CITED: WebSearch — Compose Specification (versionless); context7 /microsoft/playwright]
services:
  app:
    build:
      context: ..
      dockerfile: Dockerfile
    environment:
      LLM_MOCK: "true"
      FINALLY_DB_PATH: /app/db/finally.db
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/api/health')"]
      interval: 5s
      timeout: 3s
      retries: 10
    expose:
      - "8000"

  playwright:
    image: mcr.microsoft.com/playwright:v1.62.1-noble
    depends_on:
      app:
        condition: service_healthy
    working_dir: /work
    volumes:
      - ../test:/work
    environment:
      BASE_URL: http://app:8000
    command: sh -c "npm ci && npx playwright test"
```
Note: no top-level `version:` key — the field is obsolete under the versionless Compose Specification
`[CITED: WebSearch — cross-checked across docs.docker.com and multiple independent 2025-2026 sources]`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Manual `app.mount("/", StaticFiles(directory=..., html=True))` catch-all for SPA serving | FastAPI native `app.frontend(path, directory=..., fallback="auto"/"index.html")` | FastAPI 0.138.0 (2026-06-20), refined through 0.141.1 (2026-07-29, same-day bugfix to the initial 0.141.0 feature release) `[CITED: WebFetch fastapi.tiangolo.com/release-notes/]` | **Not adopted in this phase** — see rationale below. Documented as the future upgrade path once the API has a longer track record and the project has budget to re-verify the FastAPI bump doesn't regress anything across 13 skipped minor versions |
| Ubuntu "Jammy"/"Focal"-tagged Playwright Docker images | `-noble` (Ubuntu 24.04) tagged images | Default since Playwright v1.47.0 | This phase should use `v1.62.1-noble`, matching the pinned `@playwright/test` version |
| `docker-compose` (hyphenated v1 standalone binary) + `version:` key in compose files | `docker compose` (v2 plugin, space-separated) + versionless Compose Specification | Compose V2 GA'd in 2022; `version:` fully obsolete since | `test/docker-compose.test.yml` should omit `version:` entirely; this environment has only the V2 plugin (`Docker Compose version v5.3.1`, verified this session) |
| Astral's uv+Python combined Docker images tagged `-bookworm`/`-bookworm-slim` (this researcher's training-data memory) | Tagged `-trixie`/`-trixie-slim` (Debian 13) | Reflects Astral's current documented tag convention, confirmed via direct `WebFetch` this session — this is exactly the kind of staleness trap the task description warned about | Use `ghcr.io/astral-sh/uv:python3.13-trixie-slim`, not a `-bookworm` variant remembered from training |

**Deprecated/outdated:**
- `next lint` — removed in Next.js 16 (confirmed this session via `WebFetch` to the official upgrade
  guide); irrelevant to this phase since `frontend/package.json`'s `lint` script (verified this session,
  line 9) already uses the flat-config `eslint` CLI directly, not `next lint`.
- **Why FastAPI's `app.frontend()` is deliberately not adopted here, despite being "current":** the
  official docs now describe it as the *recommended* approach (*"If you need to host a frontend, use
  `app.frontend()` instead"* `[CITED: WebFetch fastapi.tiangolo.com/tutorial/static-files/]`), but three
  facts argue against adopting it in this specific phase: (1) it is roughly six weeks old at this
  research date with a same-day post-release bugfix already shipped, signaling active stabilization; (2)
  this project's Next.js export is a single page with no client-side routes (verified this session — only
  `app/page.tsx` exists), so `app.frontend()`'s main advantage — automatic SPA-fallback routing — solves a
  problem this app doesn't have; (3) adopting it means bumping the locked `fastapi` from 0.128.7 to
  ≥0.138.0, thirteen minor versions, in the project's final phase with no time budgeted to re-verify the
  rest of the app's FastAPI-dependent behavior (dependency injection, response models, routers) across
  that gap. The manual `StaticFiles(html=True)` approach (Pattern 1) is functionally equivalent for this
  app's actual shape and is built on Starlette APIs that have been stable for years.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `node:24-slim` chosen over `node:22-slim` as the Dockerfile builder base | Standard Stack | Negligible — both satisfy Next.js 16's verified ≥20.9 minimum; explicitly Claude's discretion per CONTEXT.md |
| A2 | Container `HEALTHCHECK`/Compose healthcheck implemented via `python -c "import urllib.request..."` rather than installing `curl` | Architecture Patterns (Pattern 2), Code Examples | Low — this is standard Docker practice to avoid adding a package just for health checks, but was not verified against an official doc this session; if the syntax is wrong, `docker inspect --format='{{.State.Health.Status}}'` during Wave 1 execution will surface it immediately as `unhealthy`, not silently |
| A3 | `STATIC_DIR` resolved as `Path(__file__).resolve().parent.parent / "static"` (i.e., `backend/static`, landing at `/app/static` in the container given the Dockerfile's `WORKDIR /app` + `COPY backend/ ./`) | Architecture Patterns (Pattern 1, Pattern 2) | Medium — this is a new design choice, not read from existing code (the directory doesn't exist yet). The Dockerfile's `COPY --from=frontend-builder ... ./static` destination and this Python constant must agree exactly, or the app silently falls back to "API-only mode" inside a container where that's actually a bug, not an intentional dev-mode signal. The executor should add a startup-time assertion or a smoke test (`curl http://localhost:8000/` returns HTML, not just a 404) rather than trusting the log line alone |
| A4 | `uv.lock` is currently resolvable and `uv sync --frozen` will succeed unmodified inside the Docker build | Architecture Patterns (Pattern 2) | Low — not verified via `uv lock --check` this session; low likelihood of drift since `cd backend && uv run --extra dev pytest` currently passes against this same lockfile, but a stale lock would fail the Docker build immediately (loud, not silent) |
| A5 | `.env.example` should list exactly `OPENROUTER_API_KEY=`, `MASSIVE_API_KEY=`, `LLM_MOCK=false` with no other keys | Common Pitfalls (Pitfall 5) | Low — sourced from PLAN.md §5 (already read as project instruction, not this research's own claim), cross-checked against `README.md`'s "Environment Variables" table (verified this session) which lists the identical three keys |
| A6 | A root `docker-compose.yml` convenience wrapper is optional and can be safely omitted without weakening any requirement | Recommended Project Structure | None if omitted — CONTEXT.md explicitly marks this as discretionary and PLAN.md §4 itself calls it "optional." Only relevant if the planner chooses to include it |

**If this table is empty:** N/A — see entries above; every item here is a low-blast-radius judgment call
with a fast, loud failure mode (crashed container, failed build, or an obviously-wrong healthcheck status)
rather than a silent correctness risk.

## Open Questions

1. **Does the executor need to actually run the DEPLOY-02 persistence script during Wave 1, or is it
   deferred to a later verification wave?**
   - What we know: Pattern 5 provides the exact script; DEPLOY-02 explicitly requires "verified against a
     restart-with-existing-volume scenario" per REQUIREMENTS.md, which is language for an executed check,
     not just a written one.
   - What's unclear: Whether the plan should treat this as a per-wave gate (run it after the Dockerfile
     exists, before marking DEPLOY-02 complete) or defer it to `/gsd-verify-work`.
   - Recommendation: Run it as part of the wave that adds the Dockerfile — it's fully automatable and
     fast (a few seconds of container lifecycle), so there's no reason to defer it to a human-gated step.

2. **Should the Windows PowerShell scripts (`start_windows.ps1`/`stop_windows.ps1`) be treated as
   `checkpoint:human-verify` given this sandbox is macOS/Linux-only?**
   - What we know: This research environment has no Windows runner; `.planning/config.json`'s
     `human_verify_mode` is `"end-of-phase"`.
   - What's unclear: Whether the executor can validate PowerShell syntax any other way (e.g., a linter)
     without an actual Windows machine.
   - Recommendation: Write the `.ps1` scripts mirroring the `.sh` scripts' logic exactly (same env-file
     fallback, same idempotency check via `docker ps --filter name=finally`), and flag them for human
     verification on an actual Windows machine — this is a genuine environment gap, not a research gap.

3. **Should a GitHub Actions CI workflow be added to wire in the new pytest/vitest/playwright suites?**
   - What we know: `.github/workflows/` currently only has Claude Code review workflows (verified this
     session); no requirement names CI.
   - What's unclear: Whether the project wants automated CI as part of "one-command ship" or considers it
     out of scope.
   - Recommendation: Skip it this phase (CONTEXT.md marks it discretionary and no requirement covers it);
     the three test commands (`uv run --extra dev pytest`, `npx vitest run`, the Compose E2E command) are
     themselves the deliverable, and CI wiring is a natural but separate follow-up.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine | DEPLOY-01, DEPLOY-02, TEST-04 | ✓ | 29.6.2 (verified this session) | — |
| Docker Compose (V2 plugin) | TEST-04 (`test/docker-compose.test.yml`) | ✓ | v5.3.1 (verified this session) | — |
| Node.js | Frontend build stage, TEST-03 dev loop | ✓ | v24.18.0 (verified this session) | — |
| npm | Frontend/test dependency installs | ✓ | 11.16.0 (verified this session) | — |
| Python | Backend dev/test loop | ✓ | 3.13.3 (verified this session) | — |
| uv | Backend dependency management | ✓ | 0.11.32 (verified this session) | — |
| A Windows machine/VM | DEPLOY-03's `.ps1` scripts (execution-time verification) | ✗ | — | Write scripts mirroring the `.sh` logic; flag for human verification (see Open Question 2) |
| `OPENROUTER_API_KEY` (real value) | Not required by this phase — `LLM_MOCK=true` is the E2E path | ✗ (resolves empty in this sandbox, per task context) | — | No fallback needed; TEST-04's chat scenario is explicitly scoped to the mock path, and a real-key round trip is already a deferred item per CONTEXT.md |

**Missing dependencies with no fallback:** none blocking — the one missing dependency (a Windows runner)
has an explicit human-verification fallback already built into the phase's own `human_verify_mode`
config.

**Missing dependencies with fallback:** Windows execution environment (fallback: human verification of
scripts mirroring the tested `.sh` logic).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest 8.x via `uv run --extra dev pytest` (existing — `backend/pyproject.toml` `[tool.pytest.ini_options]`, verified this session) |
| Frontend framework | Vitest 4.1.10 (NEW — `frontend/vitest.config.ts`, per Pattern 3) |
| E2E framework | Playwright Test 1.62.1 (NEW — `test/playwright.config.ts`) |
| Backend config file | `backend/pyproject.toml` (existing) |
| Frontend config file | `frontend/vitest.config.ts` (new — Wave 0) |
| E2E config file | `test/playwright.config.ts` (new — Wave 0) |
| Backend quick run | `cd backend && uv run --extra dev pytest -x` |
| Frontend quick run | `cd frontend && npx vitest run` |
| E2E quick run | `docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright` |
| Backend full suite | `cd backend && uv run --extra dev pytest --cov=app` |
| Frontend full suite | `cd frontend && npx vitest run --coverage` |
| Persistence check | `bash test/verify-persistence.sh` (Pattern 5 — not a pytest/vitest test; a standalone shell script exercising two container lifecycles) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|-------------|
| DEPLOY-01 | Static mount does not shadow `/api/*` (unit-level proof, no Docker needed) | unit | `cd backend && uv run --extra dev pytest tests/test_static_mount.py -x` | ❌ Wave 0 |
| DEPLOY-01 | Built image serves both API and static frontend on port 8000 | integration/shell | `docker build -t finally:test . && docker run -d --rm -p 8000:8000 -e LLM_MOCK=true --name finally-verify finally:test && curl -sf http://localhost:8000/api/health && curl -sf http://localhost:8000/ | grep -qi '<html' ; docker stop finally-verify` | ❌ Wave 0 (Dockerfile doesn't exist yet) |
| DEPLOY-02 | Positions/cash/watchlist/trades/chat history survive a stop → start cycle on the same volume | integration/shell (not pytest — see Pattern 5) | `bash test/verify-persistence.sh` | ❌ Wave 0 |
| DEPLOY-03 | Start script is idempotent (running it twice yields exactly one running container) | integration/shell | `bash scripts/start_mac.sh && bash scripts/start_mac.sh; test "$(docker ps --filter name=finally -q | wc -l)" -eq 1` | ❌ Wave 0 |
| DEPLOY-03 | Stop script removes the container but never the volume | integration/shell | `bash scripts/stop_mac.sh; docker ps -a --filter name=finally -q | wc -l` expect `0`; `docker volume ls --filter name=finally-data -q` expect the volume still present | ❌ Wave 0 |
| DEPLOY-03 | Windows scripts mirror the same behavior | manual (human-verify) | N/A — no Windows runner in this sandbox (Open Question 2) | ❌ Wave 0, human-verify at phase gate |
| TEST-03 | Price flash animation fades after ~500ms | unit | `cd frontend && npx vitest run components/WatchlistRow.test.tsx` (use `vi.useFakeTimers()` to advance past the 500ms `setTimeout` verified this session in `WatchlistRow.tsx` lines 56-59) | ❌ Wave 0 |
| TEST-03 | Watchlist add/remove (CRUD) updates the grid | unit | `cd frontend && npx vitest run components/WatchlistPanel.test.tsx` (or split across `AddTickerForm.test.tsx`/`RemoveTickerButton.test.tsx`) | ❌ Wave 0 |
| TEST-03 | Portfolio display calculations (P&L, % change derived from live price + avg cost) | unit | `cd frontend && npx vitest run components/PositionsTable.test.tsx` | ❌ Wave 0 |
| TEST-03 | Chat message rendering, including the CR-01 regression (Pattern 4) | unit | `cd frontend && npx vitest run components/ChatPanel.test.tsx` | ❌ Wave 0 |
| TEST-04 | Fresh start, watchlist CRUD, buy/sell, portfolio visualizations, AI chat trade execution (mock), SSE reconnection | e2e | `docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && uv run --extra dev pytest -x` and `cd frontend && npx vitest run`
  (both fast, seconds-scale; run for any commit touching their respective trees)
- **Per wave merge:** Full backend suite with coverage, full frontend suite with coverage, plus — once the
  Dockerfile/scripts exist — the DEPLOY-01/02/03 shell checks above
- **Phase gate:** Full Playwright E2E suite green via `docker compose -f test/docker-compose.test.yml up
  --build --abort-on-container-exit --exit-code-from playwright`, plus `test/verify-persistence.sh` green,
  before `/gsd-verify-work 5`. The Windows `.ps1` scripts remain human-verify per `human_verify_mode:
  "end-of-phase"` (`.planning/config.json`, verified this session) since no Windows runner exists here.

### Wave 0 Gaps

- [ ] `frontend/vitest.config.ts` + `frontend/vitest.setup.ts` — framework install (Pattern 3)
- [ ] `frontend/components/WatchlistRow.test.tsx` — covers price flash (TEST-03)
- [ ] `frontend/components/WatchlistPanel.test.tsx` (or split `AddTickerForm.test.tsx` /
      `RemoveTickerButton.test.tsx`) — covers watchlist CRUD (TEST-03)
- [ ] `frontend/components/PositionsTable.test.tsx` — covers portfolio display calculations (TEST-03)
- [ ] `frontend/components/ChatPanel.test.tsx` — covers chat message rendering + the CR-01 regression
      (TEST-03, Pattern 4)
- [ ] `backend/tests/test_static_mount.py` — new backend test proving the static mount doesn't shadow
      `/api/*` through the same `TestClient` instance (needs a small fixture static directory since the
      real `frontend/out/` won't exist in a unit-test context — a `tmp_path`-based fixture with a
      placeholder `index.html`, monkeypatching `STATIC_DIR`, is the natural shape)
- [ ] `Dockerfile`, `.dockerignore` — net-new (Pattern 2)
- [ ] `scripts/start_mac.sh`, `stop_mac.sh`, `start_windows.ps1`, `stop_windows.ps1` — net-new
- [ ] `.env.example` — net-new
- [ ] `test/verify-persistence.sh` — net-new (Pattern 5)
- [ ] `test/docker-compose.test.yml`, `test/playwright.config.ts`, `test/package.json`, `test/e2e/*.spec.ts`
      — net-new (Code Examples)
- [ ] `.gitignore` gains `test/artifacts/`; the two stale artifact files are deleted (Pitfall 10)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | This app has no authentication by design (single-user, `user_id="default"` hardcoded per PLAN.md §7); Phase 5 introduces no auth surface |
| V3 Session Management | No | No sessions exist in this app |
| V4 Access Control | No | Single-user, no change in this phase |
| V5 Input Validation | No (unchanged) | Existing routes' Pydantic models are untouched by this phase; no new user-facing input is introduced |
| V6 Cryptography | No | No cryptographic operations added |

None of the standard V2-V6 categories gain new controls in this phase. The real security surface Phase 5
introduces is **deployment/configuration hygiene** — secrets and data handling around the Docker build and
container runtime — which the threat table below covers directly since it falls outside the V2-V6 set.

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Secrets (`.env`, containing `OPENROUTER_API_KEY`) copied into a Docker image layer instead of injected at runtime | Information Disclosure | `.dockerignore` excludes `.env`; the Dockerfile never has a `COPY .env` instruction; secrets are only ever passed via `docker run --env-file .env` / `-e` at container-start time (Pattern 2, Common Pitfall 3) |
| A developer's live `db/finally.db` (containing simulated trade/chat history) baked into the image | Information Disclosure | `.dockerignore` excludes `db/*.db*`; the container always starts from a fresh, lazily-seeded database inside the mounted volume (DB-02, unchanged from Phase 1) |
| Container process running as root, widening the blast radius of any future RCE in a dependency | Elevation of Privilege | Add a non-root `USER` directive in the Dockerfile's final stage for the production app image (not required for the Playwright E2E-only container, which Playwright's own docs accept running as root for trusted first-party test code `[VERIFIED: context7 /microsoft/playwright — docs/src/docker.md]`) |
| The existing dev-only CORS allowlist (`http://localhost:3000`) widened to a wildcard in a future edit, now that Phase 5 makes it "seem" unused in production | Spoofing / CSRF-adjacent Tampering | Keep the exact-origin allowlist (CONTEXT.md's own recommendation, already implemented — verified this session, `main.py` lines 68-74: `allow_origins=["http://localhost:3000"]`); the container doesn't need CORS since it's same-origin, so there's no pressure to widen it — just update the stale comment noting Phase 5 "removes this," since the recommendation is to keep it |
| Stale `test/artifacts/` E2E output (screenshots, traces) accidentally committed, potentially capturing environment details or account-like state from mock runs | Information Disclosure | `.gitignore` gains `test/artifacts/` this phase (Pitfall 10) |

## Sources

### Primary (HIGH confidence — in-repo, read directly this session)
- `frontend/node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md` — Next.js 16.2.12's own
  bundled Vitest setup guide, exact version match to this repo's installed Next.js
- `backend/app/main.py` — `create_app()`, router registration order, existing CORS middleware
- `backend/app/db/connection.py` — `FINALLY_DB_PATH` override and `DEFAULT_DB_PATH` arithmetic
- `backend/app/llm/mock.py` — mock trigger-phrase regexes
- `backend/app/routes/{portfolio,watchlist,chat}.py`, `backend/app/market/stream.py` — router prefixes
- `backend/tests/conftest.py` — `client`/`temp_db` fixtures
- `backend/pyproject.toml`, `backend/uv.lock` — dependency/version ground truth
- `frontend/package.json`, `frontend/next.config.ts`, `frontend/lib/api.ts` — existing config, confirmed
  unchanged by this phase
- `frontend/components/{ChatPanel,WatchlistRow,PositionsTable,AddTickerForm,WatchlistPanel,ChatActionCard}.tsx`
- `.planning/phases/05-one-command-ship/05-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`,
  `.planning/config.json`
- `.gitignore`, `README.md`, repo root `ls -la` — confirmed absence of `Dockerfile`, `.env.example`,
  `docker-compose.yml`, `scripts/`

### Secondary (MEDIUM confidence — Context7/WebFetch official docs, cross-checked)
- Context7 `/kludex/starlette` — `StaticFiles` constructor signature, `html=True` behavior, route-priority
  ordering semantics
- Context7 `/websites/fastapi_tiangolo` — `StaticFiles` tutorial page, `app.frontend()`/`router.frontend()`
  API reference
- WebFetch `fastapi.tiangolo.com/release-notes/` — confirms `app.frontend()` shipped 0.138.0 (2026-06-20),
  refined 0.141.0/0.141.1 (2026-07-29)
- WebFetch `fastapi.tiangolo.com/tutorial/static-files/` — confirms `app.frontend()` is the currently-
  recommended approach for SPA hosting
- Context7 `/microsoft/playwright` — Docker image naming (`-noble` since v1.47.0), official run/pull
  commands, root-user rationale for trusted E2E code
- Context7 `/vitest-dev/vitest` — config shape cross-check against the bundled Next.js doc
- Context7 `/testing-library/testing-library-docs` — async query (`findBy*`) guidance, `act()` warning FAQ,
  example fetch-and-render test structure
- WebFetch `docs.astral.sh/uv/guides/integration/docker/` — two-sync pattern, `UV_COMPILE_BYTECODE`/
  `UV_LINK_MODE` env vars, combined `uv`+Python image tag convention (`-trixie`/`-trixie-slim`)
- WebFetch `nextjs.org/docs/app/guides/upgrading/version-16` — Node.js 20.9+ minimum requirement table

### Tertiary (LOW confidence — WebSearch, cross-checked across multiple independent sources)
- Node.js 22/24 LTS status as of August 2026 (Node 24 Active LTS, Node 22 Maintenance LTS since March
  2026) — cross-checked across `dev.to`, `herodevs.com`, `pocketlantern.dev` results
- Docker Compose `version:` key obsolescence — cross-checked across `docs.docker.com`, `adamj.eu`, and
  multiple forum/blog sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version confirmed live against the npm registry this session;
  base-image tags confirmed against vendor docs directly (not training memory), catching a real staleness
  gap (uv's `-bookworm` → `-trixie` tag rename)
- Architecture: HIGH — the two riskiest claims (Starlette route-ordering semantics, `StaticFiles(html=True)`
  behavior) were read directly from Starlette's own docs via Context7 this session, and cross-referenced
  against this repo's actual single-page `frontend/out/` output (verified by directory listing)
- Pitfalls: MEDIUM — most pitfalls are grounded in in-repo file reads or official docs; a couple (the
  `python -c urllib` healthcheck idiom, exact Compose YAML indentation conventions) are standard Docker
  practice not individually doc-verified this session (see Assumptions Log A2)

**Research date:** 2026-08-04
**Valid until:** 7 days (fast-moving) — FastAPI alone shipped four minor releases in the six weeks before
this research, including the exact feature (`app.frontend()`) this document deliberately declines to
adopt; if phase execution slips more than ~1-2 weeks, re-run the `npm view`/registry checks and re-confirm
the FastAPI release-notes claim before trusting this document's version pins verbatim.
