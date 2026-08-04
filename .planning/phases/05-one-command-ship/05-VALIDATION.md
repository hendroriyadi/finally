---
phase: 5
slug: one-command-ship
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-04
---

# Phase 5 — Validation Strategy

> Written directly from `05-RESEARCH.md`'s `## Validation Architecture` section BEFORE planning
> (proactive, as in Phases 3 and 4).
>
> **This phase is different from every prior one.** Phases 1-4 all closed `human_needed` because their
> central claims needed a browser. Phase 5's central claims — "one command, one port, both surfaces"
> and "state survives a restart" — are shell-assertable with `curl` and a real container lifecycle.
> They should be *proven here*, not deferred. The only genuinely un-runnable item in this environment
> is the Windows `.ps1` pair (no Windows runner exists).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Backend framework** | pytest 8.x (existing) [VERIFIED: `backend/pyproject.toml`] |
| **Frontend framework** | Vitest 4.1.10 + React Testing Library (**NEW** — the project's first frontend test framework) |
| **E2E framework** | Playwright Test 1.62.1 (**NEW**) |
| **Backend quick run** | `cd backend && uv run --extra dev pytest -x` |
| **Frontend quick run** | `cd frontend && npx vitest run` |
| **E2E run** | `docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright` |
| **Persistence check** | `bash test/verify-persistence.sh` (a standalone shell script exercising two container lifecycles — deliberately not a pytest/vitest test) |
| **Estimated runtime** | backend ~7s (209 tests); frontend seconds; E2E minutes (image build dominates) |

**Environment availability** (all verified): Docker 29.6.2, Docker Compose v5.3.1, Node 24.18.0,
npm 11.16.0, Python 3.13.3, uv 0.11.32. **Not available:** a Windows runner; a real
`OPENROUTER_API_KEY` (irrelevant here — the E2E path is `LLM_MOCK=true` by design).

---

## Sampling Rate

- **Per task commit:** `cd backend && uv run --extra dev pytest -x` and `cd frontend && npx vitest run` — whichever trees the commit touches
- **Per plan wave:** full backend suite + full frontend suite, plus (once the Dockerfile and scripts exist) the DEPLOY-01/02/03 shell checks below
- **Phase gate:** Playwright E2E suite green **and** `test/verify-persistence.sh` green before `/gsd-verify-work 5`

---

## Per-Task Verification Map

| Task ID | Requirement | Secure/Correct Behavior | Test Type | Automated Command | File Exists | Status |
|---------|-------------|--------------------------|-----------|-------------------|-------------|--------|
| (planner-assigned) | DEPLOY-01 | The static mount does not shadow `/api/*` — provable at unit level, no Docker needed | unit | `cd backend && uv run --extra dev pytest tests/test_static_mount.py -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | DEPLOY-01 | The built image serves the API **and** the static frontend on one port | integration/shell | `docker build -t finally:test . && docker run -d --rm -p 8000:8000 -e LLM_MOCK=true --name finally-verify finally:test`, then `curl -sf localhost:8000/api/health` and `curl -sf localhost:8000/ \| grep -qi '<html'`, then `docker stop finally-verify` | ❌ W0 | ⬜ pending |
| (planner-assigned) | DEPLOY-02 | Cash, positions, trades, watchlist, and chat history all survive a stop → start cycle on the same volume | integration/shell | `bash test/verify-persistence.sh` | ❌ W0 | ⬜ pending |
| (planner-assigned) | DEPLOY-03 | The start script is idempotent — running it twice leaves exactly one container | integration/shell | `bash scripts/start_mac.sh && bash scripts/start_mac.sh; test "$(docker ps --filter name=finally -q \| wc -l)" -eq 1` | ❌ W0 | ⬜ pending |
| (planner-assigned) | DEPLOY-03 | The stop script removes the container but **never** the volume | integration/shell | `bash scripts/stop_mac.sh`; assert 0 containers and that `finally-data` still exists | ❌ W0 | ⬜ pending |
| (planner-assigned) | DEPLOY-03 | The Windows scripts mirror the same behavior | manual-only | No Windows runner in this environment | ❌ N/A | ⬜ pending |
| (planner-assigned) | TEST-03 | Price flash fades after ~500ms | unit | `cd frontend && npx vitest run components/WatchlistRow.test.tsx` (`vi.useFakeTimers()` past the 500ms timeout) | ❌ W0 | ⬜ pending |
| (planner-assigned) | TEST-03 | Watchlist add/remove updates the grid | unit | `cd frontend && npx vitest run components/WatchlistPanel.test.tsx` | ❌ W0 | ⬜ pending |
| (planner-assigned) | TEST-03 | Portfolio display calculations (P&L, % change from live price + avg cost) | unit | `cd frontend && npx vitest run components/PositionsTable.test.tsx` | ❌ W0 | ⬜ pending |
| (planner-assigned) | TEST-03 | Chat message rendering **including the CR-01 regression** | unit | `cd frontend && npx vitest run components/ChatPanel.test.tsx` | ❌ W0 | ⬜ pending |
| (planner-assigned) | TEST-04 | Fresh start, watchlist CRUD, buy/sell, portfolio visualizations, AI chat trade execution (mock), SSE reconnection | e2e | `docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `frontend/vitest.config.ts` + `frontend/vitest.setup.ts` — framework install
- [ ] `frontend/components/WatchlistRow.test.tsx` — price flash (TEST-03)
- [ ] `frontend/components/WatchlistPanel.test.tsx` (or split into `AddTickerForm`/`RemoveTickerButton`) — watchlist CRUD (TEST-03)
- [ ] `frontend/components/PositionsTable.test.tsx` — portfolio display calculations (TEST-03)
- [ ] `frontend/components/ChatPanel.test.tsx` — chat rendering + the **CR-01 regression** (TEST-03)
- [ ] `backend/tests/test_static_mount.py` — the mount does not shadow `/api/*`, asserted through one `TestClient`; needs a `tmp_path` fixture static dir with a placeholder `index.html`, since the real `frontend/out/` does not exist in a unit-test context
- [ ] `Dockerfile`, `.dockerignore` — net-new
- [ ] `scripts/start_mac.sh`, `stop_mac.sh`, `start_windows.ps1`, `stop_windows.ps1` — net-new
- [ ] `.env.example` — net-new (PLAN.md §4 calls for it; it is currently absent)
- [ ] `test/verify-persistence.sh` — net-new
- [ ] `test/docker-compose.test.yml`, `test/playwright.config.ts`, `test/package.json`, `test/e2e/*.spec.ts` — net-new
- [ ] `.gitignore` gains `test/artifacts/`; the two stale artifact files are deleted

---

## The CR-01 Regression Test (called out specifically)

Phase 4's code review found a **critical** bug in `ChatPanel`: the transcript branched on a
never-cleared `historyError` flag first, so one failed history load permanently masked the conversation
even as later sends succeeded. The review noted the component had **zero** test coverage.

The regression test is therefore the single highest-value frontend test in this phase, and its shape is
specified rather than left open: mock `fetchChatHistory` to reject, mount, assert the error copy shows;
then mock `sendChatMessage` to resolve, send a message, and **assert the user's message and the reply
are visible** — i.e. that the error banner no longer wins. A test that only asserted the error appears
would have passed against the bug.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `start_windows.ps1` / `stop_windows.ps1` build, run, and stop the container idempotently | DEPLOY-03 | No Windows runner exists in this environment; the scripts are written to mirror the `.sh` logic, which **is** automatically verified | On a Windows machine with Docker Desktop: run the start script twice (expect one container, no error), browse to `http://localhost:8000`, then run the stop script twice (expect no container, volume retained) |

Everything else in this phase is automatable here — a deliberate departure from Phases 1-4, whose
central claims all required a browser.

---

## Validation Sign-Off

- [x] Every requirement except DEPLOY-03's Windows half maps to an automated command
- [x] DEPLOY-01 is verified at two levels — a unit test for route-shadowing and a real container for the one-port claim
- [x] DEPLOY-02 is verified by an actual stop/start/assert cycle, not by inspecting a `-v` flag
- [x] Wave 0 covers every MISSING file referenced above
- [x] No watch-mode flags
- [x] Backend/frontend feedback latency < 10s; the E2E suite is a phase-gate cost, not a per-commit one
- [x] `nyquist_compliant: true`

**Approval:** approved 2026-08-04 (written proactively from `05-RESEARCH.md`'s complete
`## Validation Architecture` section, before planning)
