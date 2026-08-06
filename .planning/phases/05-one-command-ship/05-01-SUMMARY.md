---
phase: 05-one-command-ship
plan: 01
subsystem: infra
tags: [docker, fastapi, staticfiles, uv, deployment]

requires:
  - phase: 04-ai-copilot
    provides: "the complete application (four routers, chat persistence) that this image packages"
  - phase: 01-live-market-terminal
    provides: "FINALLY_DB_PATH env override in app/db/connection.py, which the image sets explicitly"
provides:
  - "Dockerfile — multi-stage build serving API + static frontend from one uvicorn process on port 8000"
  - ".dockerignore — keeps secrets, the developer database, virtualenvs and node_modules out of every layer"
  - "STATIC_DIR + guarded StaticFiles mount in backend/app/main.py"
  - "backend/tests/test_static_mount.py — unit proof the mount cannot shadow /api/*"
  - "test/verify-persistence.sh — two-lifecycle shell proof of DEPLOY-02"
affects: [05-02, 05-04]

actuals:
  tokens: 14000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Catch-all StaticFiles mount registered as the last statement of the app factory, guarded on directory existence — the guard is what lets one codebase serve API-only in a checkout and API+frontend in the image, with no try/except and no separate entrypoint"

key-files:
  created: [Dockerfile, .dockerignore, backend/tests/test_static_mount.py, test/verify-persistence.sh]
  modified: [backend/app/main.py, .gitignore]

key-decisions:
  - "node:24-slim over PLAN.md's indicative 'Node 20 slim' — Active LTS, this project's own dev version, clears Next.js 16's >=20.9 floor"
  - "ghcr.io/astral-sh/uv:python3.13-trixie-slim — `-trixie`, NOT the stale `-bookworm` tag family"
  - "FastAPI stays at 0.128.7; its native app.frontend() needs >=0.138.0 and solves an SPA-fallback problem this single-page export does not have"
  - "Dev CORS middleware kept (exact-origin allowlist, inert in the same-origin container, still needed by npm run dev); only its stale comment was corrected"

patterns-established:
  - "Phase-5 verification standard: prove infrastructure claims against real running containers (always detached, always explicitly removed) rather than deferring them to a human — the first phase in this project able to do so"

requirements-completed: [DEPLOY-01, DEPLOY-02]

coverage:
  - id: D1
    description: "A single image serves the API and the exported frontend on port 8000"
    requirement: DEPLOY-01
    verification:
      - kind: integration
        ref: "docker build + docker run -d + curl /api/health (JSON) + curl / (HTML) + curl /api/watchlist (tickers) — run this session"
        status: pass
      - kind: unit
        ref: "backend/tests/test_static_mount.py — 7 tests"
        status: pass
    human_judgment: false
  - id: D2
    description: "The catch-all static mount cannot shadow /api/*"
    requirement: DEPLOY-01
    verification:
      - kind: unit
        ref: "backend/tests/test_static_mount.py#test_inline_api_route_is_not_shadowed_by_the_static_mount, #test_router_supplied_api_route_is_not_shadowed, #test_static_mount_is_the_last_route_registered"
        status: pass
      - kind: other
        ref: "verify gate compares line numbers: last include_router < app.mount"
        status: pass
    human_judgment: false
  - id: D3
    description: "A checkout with no built frontend still starts the backend API-only instead of raising"
    requirement: DEPLOY-01
    verification:
      - kind: unit
        ref: "backend/tests/test_static_mount.py#test_app_starts_without_a_static_directory"
        status: pass
    human_judgment: false
  - id: D4
    description: "Cash, positions, trades, watchlist, and chat history survive container destruction and replacement on the same volume"
    requirement: DEPLOY-02
    verification:
      - kind: integration
        ref: "bash test/verify-persistence.sh — 4/4 dimensions pass; mutation spot-check confirms it fails when persistence is broken"
        status: pass
    human_judgment: false
  - id: D5
    description: "No secret or developer database enters the image; the runtime process is unprivileged"
    requirement: DEPLOY-01
    verification:
      - kind: integration
        ref: "docker exec: no .env in /app, id -un returns appuser, /app/db owned by appuser"
        status: pass
    human_judgment: false

duration: ~35min
completed: 2026-08-04
status: complete
---

# Phase 5, Plan 01: Docker Image + Persistence Proof Summary

**One image built from this repo answers `GET /api/health` with JSON and `GET /` with the trading terminal's HTML on the same port 8000 — and the data it writes survives the container's own destruction, both proven against containers that actually ran.**

## Performance

- **Tasks:** 2 completed
- **Files:** 4 created, 2 modified
- **Tests:** 216 backend tests passing (was 209; +7 from `test_static_mount.py`)
- **Note:** executed directly by the orchestrator rather than a subagent, following this session's established pattern after repeated executor session-limit failures.

## Accomplishments
- **DEPLOY-01 proven, not deferred.** A real container answered `/api/health` (JSON), `/` (the terminal's HTML), `/api/watchlist` (seeded tickers), and 404'd an unknown path — then was removed.
- **DEPLOY-02 proven, not deferred.** Four state dimensions written through the HTTP API survived container removal and replacement on the same named volume.
- Multi-stage `Dockerfile`: `node:24-slim` builds the export; `ghcr.io/astral-sh/uv:python3.13-trixie-slim` installs the backend via Astral's two-sync split and copies the export to `/app/static`.
- `STATIC_DIR` + directory-guarded `StaticFiles(html=True)` mount as the last statement of `create_app()`.
- 7 unit tests covering mount ordering, both API route kinds, html-mode 404, the SSE route's presence (asserted structurally, never requested), and the no-static-directory dev path.
- Image hygiene verified by inspection: no `.env`, no developer database, process runs as `appuser`, `/app/db` writable for SQLite + WAL sidecars.

## Task Commits

1. **Task 1: One image, one port, both surfaces** — `feat(05-01)`
2. **Task 2: Prove the data outlives the container** — `test(05-01)`

## Decisions Made
All four recorded in the frontmatter's `key-decisions`. The one worth restating: **FastAPI was deliberately not bumped.** Its native `app.frontend()` API would be the idiomatic modern answer, but it requires ≥0.138.0 against this project's locked 0.128.7, and it exists to solve SPA client-routing fallback — a problem a single-page export does not have. A manual mount is both lower-risk and a better fit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Shell escaping] The persistence script's Python one-liners failed to parse**
- **Found during:** Task 2, first run of `verify-persistence.sh`
- **Issue:** `python3 -c '...print(f"{json.load(sys.stdin)[\"cash_balance\"]:.4f}")'` — inside a single-quoted bash string the `\"` survives literally, so Python received a backslash and raised `SyntaxError: unexpected character after line continuation character`.
- **Fix:** Replaced the escaped-quote f-strings with plain double quotes inside the single-quoted shell argument, and swapped the f-string for `"%.4f" %` formatting.
- **Verification:** Script runs clean; all four dimensions report.
- **Committed in:** the Task 2 commit (found and fixed before it was ever committed)

---

**Total deviations:** 1 auto-fixed (a mechanical shell-quoting bug in new code, not a plan defect)

## Issues Encountered
None beyond the escaping bug above. Notably the image built and ran correctly on the first attempt — the `-trixie` tag, the two-sync split, the static-path pairing, and the `mkdir`-before-`chown` volume-ownership sequencing all worked as the research predicted.

## Verification Evidence

**DEPLOY-01** (against a running container):
```
/api/health   -> {"status":"ok"}
/             -> <!DOCTYPE html><html lang="en" ...
/api/watchlist-> {"tickers":[{"ticker":"AAPL",...}]}
/nope         -> 404
whoami        -> appuser
```

**DEPLOY-02** (`bash test/verify-persistence.sh`):
```
PASS cash            8590.0100
PASS positions       [('AAPL', 3.0), ('MSFT', 2.0)]
PASS watchlist       [... 'PYPL' ...]
PASS chat history    2 messages
```

**Mutation spot-check** (`FINALLY_DB_PATH` pointed outside the mount — never committed):
```
FAIL cash        before=8589.91  after=10000.00
FAIL positions   before=[AAPL 3, MSFT 2]  after=[]
FAIL watchlist   before=[...PYPL...]  after=[no PYPL]
FAIL chat        before=2  after=0
```
Restored → passes again. The proof is genuinely load-bearing.

## Next Phase Readiness
- Plan 05-02 (start/stop scripts) can proceed: the image builds, the volume contract is proven, and `.env.example` is its to create.
- Plan 05-04 (Playwright E2E) can proceed: the container serves the full app on one port under `LLM_MOCK=true`, which is exactly what its compose file needs.

---
*Phase: 05-one-command-ship*
*Completed: 2026-08-04*
