# Phase 5: One-Command Ship - Context

**Gathered:** 2026-08-04
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run — grey areas resolved directly from PLAN.md/REQUIREMENTS.md/codebase state rather than interactive discussion, per explicit user direction to build the full project without interactive check-ins)

<domain>
## Phase Boundary

This phase makes everything built in Phases 1-4 runnable by one command: a single Docker container on
port 8000 serving both the API and the static frontend, a volume-mounted `db/` that survives restarts,
idempotent start/stop scripts for macOS/Linux and Windows, frontend component tests (the project's
first), and a Playwright E2E suite running against the container under `LLM_MOCK=true`.

It is the only phase that adds no user-facing feature. Everything here is packaging and proof.

Out of scope: any new product behavior; the optional AWS App Runner / Terraform `deploy/` directory
(PLAN.md §11 explicitly calls it a stretch goal, "not part of the core build").

</domain>

<decisions>
## Implementation Decisions

### Current state (verified this session, not assumed)
- **No `Dockerfile`, no `docker-compose.yml`, no `scripts/` directory exist.** All are net-new.
- **`backend/app/main.py` does not serve static files at all** — it mounts four API routers and a
  health endpoint, nothing else. DEPLOY-01's "one port serves both" requires adding a `StaticFiles`
  mount, and that is the single most consequential code change in this phase.
- **`frontend` already produces a static export**: `next.config.ts` sets `output: 'export'` and
  `images.unoptimized`, and `npm run build` writes `frontend/out/` (verified — `out/404.html` etc.
  exist). No frontend build-config change is needed.
- **`NEXT_PUBLIC_API_URL` already defaults to `""`** (`frontend/lib/api.ts`'s `API_BASE`), which
  resolves to same-origin relative paths. That default is *exactly* what the single-container
  deployment needs, so the container must simply not set that variable. No code change.
- **`db/` exists with a tracked `.gitkeep`**, and `finally.db`/`-shm`/`-wal`/`-journal` are gitignored.
  It is already shaped as the volume mount target.
- **`test/` contains only `test/artifacts/{report,results}`** — stale Playwright output from some
  earlier run, with no config, no spec files, and no `package.json`. The E2E suite is net-new; those
  two leftover artifact files should be removed and the directory gitignored as part of this phase.
- **No frontend test framework is installed anywhere** (`frontend/package.json` has no Vitest/Jest/RTL).
  TEST-03 requires adding one — the first new frontend dev dependency since Phase 3's `recharts`.
- **Docker 29.6.2 is available** in this environment.

### DEPLOY-01: single container, single port
- Multi-stage `Dockerfile` per PLAN.md §11: a Node stage running `npm ci && npm run build`, then a
  Python stage installing `uv`, running `uv sync`, and copying the Node stage's `frontend/out` in.
- **Node base image is Claude's discretion, and PLAN.md's "Node 20 slim" should be treated as
  indicative rather than binding**: this project runs Next.js 16 (which requires Node ≥20.9) and was
  developed on Node 24. Pin a version that is definitely new enough — Node 22 or 24 slim — rather than
  copying `20` literally and risking an engine-mismatch failure at image-build time.
- **Static mount ordering is the trap to avoid**: FastAPI matches routes in declaration order, so a
  catch-all `StaticFiles(html=True)` mounted at `/` must be added *after* all four API routers, or it
  will shadow `/api/*`. The mount must also not break the SSE stream endpoint. Whatever ordering is
  chosen needs a test that hits an API route and a static route through the same app instance.
- **Serving path must be environment-tolerant**: the static directory exists in the container but not
  in a local `uv run uvicorn` dev session. Mount it conditionally on the directory existing, so a
  developer running the backend alone doesn't get a startup crash — and log which mode was chosen.
- **CORS**: `main.py`'s existing dev-only middleware carries a comment saying "Phase 5's single-origin
  Docker container removes this." Claude's discretion on whether to actually remove it — recommendation
  is to **keep** it: it is an exact-origin allowlist to `http://localhost:3000` (never a wildcard), it
  costs nothing in the container where the frontend is same-origin, and removing it breaks the
  `npm run dev` workflow every future contributor uses. If it is kept, update that stale comment.

### DEPLOY-02: persistence across restarts
- `docker run -v finally-data:/app/db ...` per PLAN.md §11, with the backend writing `finally.db` into
  that directory. `FINALLY_DB_PATH` already exists as the override (`app/db/connection.py`), so the
  container sets it to the mounted path rather than relying on the default's path arithmetic
  (`parents[3]` from `connection.py` resolves differently inside the image than in the repo).
- The requirement says "verified against a restart-with-existing-volume scenario" — so this needs an
  actual stop/start/assert cycle, not just a volume flag in a run command.

### DEPLOY-03: start/stop scripts
- `scripts/start_mac.sh`, `scripts/stop_mac.sh`, `scripts/start_windows.ps1`, `scripts/stop_windows.ps1`
  per PLAN.md §4. All four must be idempotent (PLAN.md §11: "safe to run multiple times").
- Start: build the image if absent or if `--build` is passed, run with the volume, port mapping, and
  `--env-file .env`, print the URL, optionally open a browser. Stop: stop and remove the container but
  **never** the volume.
- **`.env` handling is a real edge case**: `--env-file .env` fails hard if the file is missing, and
  `.env` is gitignored so a fresh clone won't have one. The scripts should either create it from an
  example or degrade gracefully — a fresh cloner hitting a cryptic Docker error on their first command
  would defeat the entire point of this phase. There is currently **no `.env.example` at the repo
  root** (PLAN.md §4 says one should be committed); adding it is in scope.

### TEST-03: frontend component tests
- Framework choice is Claude's discretion; **Vitest + React Testing Library** is the recommendation
  (Vitest is the standard pairing for a Vite/Next TS project and needs no Babel config), but any
  framework that runs in CI without a browser is acceptable.
- Required coverage per the requirement text: price flash animation, watchlist CRUD, portfolio display
  calculations, and chat message rendering.
- **`ChatPanel` deserves priority**: Phase 4's code review found a critical bug in it (a sticky
  `historyError` that permanently masked the transcript) and explicitly noted the component had *zero*
  test coverage. A regression test for that specific bug — error state, then a successful send, then
  assert the message is visible — is the single highest-value frontend test in this phase.

### TEST-04: Playwright E2E
- Per PLAN.md §12, a `test/docker-compose.test.yml` spinning up the app container plus a Playwright
  container, keeping browser dependencies out of the production image.
- Runs with `LLM_MOCK=true` — which Phase 4 verified end-to-end, and which is the reason the AI chat
  scenario is testable at all without an API key. `OPENROUTER_API_KEY` resolves empty in this sandbox,
  so **no E2E test may depend on a real LLM call.**
- Scenarios required by the requirement: fresh start, watchlist add/remove, buy/sell, portfolio
  visualizations, AI chat with trade execution, SSE reconnection.
- **The mock's trigger phrases are the contract** for the chat E2E scenario: `app/llm/mock.py` matches
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

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/db/connection.py` — `FINALLY_DB_PATH` env override and `get_db_path()`; the container
  sets that variable rather than depending on the default's repo-relative path arithmetic.
- `backend/app/main.py` — `create_app()` and its lifespan; the `StaticFiles` mount goes here, after
  the four `include_router` calls.
- `backend/app/llm/mock.py` — the deterministic `LLM_MOCK=true` responses and their trigger regexes;
  the E2E chat scenario is written against these.
- `backend/tests/conftest.py` — `temp_db` and `client` fixtures, if any new backend test needs them
  (e.g. a static-mount-does-not-shadow-`/api` test).
- `frontend/next.config.ts` — already correct for static export; do not change.
- `frontend/lib/api.ts` — `API_BASE` already defaults to same-origin; do not change.

### Established Patterns
- Backend: `from __future__ import annotations`, full type hints, module-level `logger`, prose
  docstrings explaining *why*, `run_db()` for all blocking I/O.
- Tests: evidence discipline — assert against a fresh independent read rather than the value the code
  under test just returned. Phases 2, 3, and 4 each used a **mutation spot-check** (deliberately break
  the behavior, watch the specific test fail, restore) to prove a load-bearing test wasn't vacuous;
  the DEPLOY-02 persistence test is the natural candidate for the same treatment here.
- Frontend: `"use client"` on anything using hooks/browser APIs; `.then()`-chain fetch effects (not
  awaited async calls) to satisfy `eslint-config-next` 16's `react-hooks/set-state-in-effect`.

### Integration Points
- `Dockerfile` (new, repo root) — the Node stage's output feeds the Python stage.
- `backend/app/main.py` — the one code file this phase modifies for DEPLOY-01.
- `.env.example` (new, repo root) — referenced by PLAN.md §4/§5 but currently absent.
- `.gitignore` — should gain `test/artifacts/` (currently untracked but not ignored).

</code_context>

<specifics>
## Specific Ideas

- **Verify the container actually works, don't just build it.** Every prior phase deferred live
  verification to a human because a browser session was needed. This phase's central claim —
  "one command, one port, both surfaces" — is verifiable *without a browser*: build the image, run it,
  `curl localhost:8000/api/health` and `curl localhost:8000/` and assert both respond correctly.
  That is a shell assertion, and it should be done rather than deferred.
  **Any container must be started detached (`-d`) and explicitly stopped afterward** — a foreground
  `docker run` hangs the tool call exactly as a foreground `uvicorn` does.
- **DEPLOY-02 is the one requirement that is easy to fake.** A test that merely checks the `-v` flag is
  present proves nothing. It requires: start container → write state (a trade) → stop container →
  start again with the same volume → assert the state is still there.
- `.dockerignore` matters more than usual here: without it the build context includes `node_modules`,
  `.venv`, `frontend/out`, `.git`, and `db/finally.db` — slow, and the last one would bake a developer's
  local database into the image.

</specifics>

<deferred>
## Deferred Ideas

- AWS App Runner / Terraform `deploy/` directory — PLAN.md §11 explicitly marks it a stretch goal
  outside the core build.
- Closing out Phases 1-4's deferred live-browser verifications (`/gsd-verify-work 1` through `4`).
  Phase 5's Playwright suite covers much of the same ground automatically, so those may become
  largely redundant once TEST-04 passes — worth re-assessing after this phase rather than before.
- A live-API-key LLM round trip (Phase 4's one genuinely unexercised dependency). Still needs a human
  with a real `OPENROUTER_API_KEY`; nothing in this phase changes that.

</deferred>
