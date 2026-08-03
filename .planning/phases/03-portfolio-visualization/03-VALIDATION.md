---
phase: 3
slug: portfolio-visualization
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-03
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Written directly from `03-RESEARCH.md`'s `## Validation Architecture` section BEFORE planning (proactive step this time, per the lesson learned from Phase 2 where this file was missed and caught late by the plan-checker).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 (backend, existing) [VERIFIED: backend test cache]; no frontend test framework installed yet [VERIFIED: frontend/package.json has no test script/dependency] |
| **Config file** | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`, `asyncio_mode = "auto"`) |
| **Quick run command** | `cd backend && uv run --extra dev pytest tests/db/test_portfolio.py tests/routes/test_portfolio.py -x` |
| **Full suite command** | `cd backend && uv run --extra dev pytest -v` |
| **Estimated runtime** | ~2-3 seconds (128 backend tests as of Phase 2, growing) |

---

## Sampling Rate

- **Per task commit:** `cd backend && uv run --extra dev pytest tests/db/test_portfolio.py tests/routes/test_portfolio.py -x`
- **Per plan wave:** `cd backend && uv run --extra dev pytest -v`
- **Phase gate:** Full backend suite green before `/gsd-verify-work`. Frontend visual/interaction checks (treemap rendering, chart appearance, click-to-select UX) remain `human_needed` per this project's established Phase 1/2 pattern — no frontend test framework exists yet (that gap is pre-existing, tracked project-wide under TEST-03/Phase 5, not introduced by this phase).

---

## Per-Task Verification Map

| Task ID | Requirement | Secure/Correct Behavior | Test Type | Automated Command | File Exists | Status |
|---------|-------------|--------------------------|-----------|-------------------|-------------|--------|
| (planner-assigned) | PORT-06 | `record_portfolio_snapshot()` inserts a row with correct `total_value`/`recorded_at` | unit | `pytest tests/db/test_portfolio.py -k snapshot -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | PORT-06 | Snapshot background task fires every 30s and survives a failed iteration without dying (mirrors `SimulatorDataSource`'s lifecycle pattern) | unit | new test mirroring `tests/market/test_simulator_source.py`'s lifecycle-test shape | ❌ W0 | ⬜ pending |
| (planner-assigned) | PORT-06 | Trade route triggers an immediate post-trade snapshot | integration | `pytest tests/routes/test_portfolio.py -k snapshot -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | PORT-06 | Snapshots survive a "restart" (visible via a fresh, independent `connect()`) | integration | new test: insert via one `run_db()` call, assert visible via a second independent connection | ❌ W0 | ⬜ pending |
| (planner-assigned) | PORT-07 | `GET /api/portfolio/history` returns snapshots ordered by `recorded_at` | integration | `pytest tests/routes/test_portfolio.py -k history -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | PORT-08 | Treemap sizing/coloring math (weight calc, opacity clamp, neutral-fill threshold) | manual-only | No frontend test framework installed yet | ❌ N/A | ⬜ pending |
| (planner-assigned) | UI-02 | Clicking a watchlist row updates `selectedTicker` and the detail chart's rendered ticker | manual-only | No frontend test framework installed; Playwright E2E is Phase 5's TEST-04 | ❌ N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/db/test_snapshots.py` (or an extension of `backend/tests/db/test_portfolio.py` — planner's choice) — covers PORT-06's `record_portfolio_snapshot()`, including the restart-durability proof
- [ ] `backend/tests/routes/test_portfolio.py` extension — covers PORT-06's post-trade trigger and PORT-07's `GET /api/portfolio/history`
- [ ] No new fixtures needed — `temp_db` and `client` (`backend/tests/conftest.py`) already cover this phase's needs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Treemap renders positions sized/colored correctly by weight and P&L | PORT-08 | No frontend test framework installed yet (pre-existing gap, tracked under Phase 5's TEST-03) | Start backend + frontend (backgrounded), open the app with 2+ positions, confirm rectangle sizes are proportional to market value and colors match P&L sign/magnitude |
| P&L line chart renders portfolio value history | PORT-07 | Same as above | Confirm the chart shows points accumulating over 30s and immediately after a trade |
| Clicking a watchlist ticker loads it into the detail chart, which keeps updating live | UI-02 | Same as above; also genuinely interactive (click event) | Click several different watchlist rows, confirm the detail chart switches to each and continues updating from the live SSE stream |

---

## Validation Sign-Off

- [x] All tasks expected to have `<automated>` verify or Wave 0 dependencies for backend work; frontend visual/interaction work is manual-only by documented project-wide convention (no test framework yet)
- [x] Sampling continuity: backend tasks all carry automated verify per the map above
- [x] Wave 0 covers all MISSING references (both new/extended test files listed above)
- [x] No watch-mode flags
- [x] Feedback latency < 5s (mirrors Phase 1/2's suite speed)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-08-03 (written proactively from `03-RESEARCH.md`'s complete `## Validation Architecture` section, before planning — avoiding the step-ordering miss that required a late backfill in Phase 2)
