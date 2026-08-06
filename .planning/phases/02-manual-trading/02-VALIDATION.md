---
phase: 2
slug: manual-trading
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-03
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Populated directly from `02-RESEARCH.md`'s `## Validation Architecture` section (this file was missed during the initial plan-phase pass and is being backfilled after the plan-checker flagged its absence — content is unchanged from what the research already specified, not newly authored judgment).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3+ / pytest-asyncio 0.24+ [VERIFIED: backend/pyproject.toml] |
| **Config file** | `backend/pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| **Quick run command** | `cd backend && uv run --extra dev pytest tests/db/test_portfolio.py -x` |
| **Full suite command** | `cd backend && uv run --extra dev pytest -v` |
| **Estimated runtime** | ~2 seconds (mirrors Phase 1's suite, which ran in 1.6s at 94 tests) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && uv run --extra dev pytest tests/db/test_portfolio.py tests/routes/test_portfolio.py -x`
- **After every plan wave:** Run `cd backend && uv run --extra dev pytest -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | PORT-02, PORT-04 | T-02-01 / T-02-02 | Atomic buy: cash debited only if sufficient, via `UPDATE...WHERE` | unit | `pytest tests/db/test_portfolio.py::test_buy_fractional_shares -x` | ❌ W0 | ⬜ pending |
| 02-01-01 | 01 | 1 | PORT-02, PORT-04 | T-02-01 | Exact-balance buy spends exactly all cash (boundary) | unit | `pytest tests/db/test_portfolio.py::test_buy_exact_balance -x` | ❌ W0 | ⬜ pending |
| 02-01-01 | 01 | 1 | PORT-04 | T-02-01 | Insufficient-cash buy rejected, state byte-identical after | unit | `pytest tests/db/test_portfolio.py::test_buy_rejected_insufficient_cash -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | PORT-03 | T-02-02 | Full-position sell deletes the `positions` row (not quantity=0) | unit | `pytest tests/db/test_portfolio.py::test_sell_full_position_deletes_row -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | PORT-03 | — | Partial sell reduces quantity, avg_cost unchanged | unit | `pytest tests/db/test_portfolio.py::test_sell_partial_reduces_quantity -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | PORT-04 | T-02-02 | Insufficient-shares sell rejected, state byte-identical after | unit | `pytest tests/db/test_portfolio.py::test_sell_rejected_insufficient_shares -x` | ❌ W0 | ⬜ pending |
| 02-02-01/02 | 02 | 2 | PORT-04 | T-02-01 / T-02-02 | Concurrency proof: N simultaneous buys against fixed cash never overspend (4 race scenarios: buys, full sells, partial sells, mixed) | unit | `pytest tests/db/test_portfolio.py::test_concurrent_buys_never_exceed_cash -x` | ❌ W0 | ⬜ pending |
| 02-01-01 | 01 | 1 | PORT-01 | — | `GET /api/portfolio` returns correct P&L/% for a known position+price | unit | `pytest tests/routes/test_portfolio.py::test_get_portfolio_computes_pnl -x` | ❌ W0 | ⬜ pending |
| 02-01-01 | 01 | 1 | PORT-01 | — | Position with no cached price returns null current_price, not a crash | unit | `pytest tests/routes/test_portfolio.py::test_get_portfolio_missing_price_returns_null -x` | ❌ W0 | ⬜ pending |
| 02-03/02-04 | 03/04 | 2/3 | UI-05, UI-03 | — | Trade bar buy/sell flow, header live update | manual-only | N/A — visual/live-tick behavior; same category of gap Phase 1 deferred to `/gsd-verify-work` (flash animation, live rendering require a real browser session) | ❌ N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/db/test_portfolio.py` — covers PORT-02, PORT-03, PORT-04 (data-access-layer tests, mirroring `test_watchlist.py`'s `temp_db` fixture + `asyncio.gather` concurrency style)
- [ ] `backend/tests/routes/test_portfolio.py` — covers PORT-01, PORT-05 (route-level status codes/shapes, mirroring existing route test conventions)
- [ ] No new fixtures needed — `temp_db` (`backend/tests/conftest.py:14-20`) and `client` (`backend/tests/conftest.py:23-33`) already cover this phase's needs, verified during research.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Trade bar buy/sell instant fill, no confirmation dialog, header/positions-table live update | UI-05, UI-03, PORT-05 | Visual/live-tick rendering behavior requires a real browser session — same category of gap Phase 1 deferred to `/gsd-verify-work` | Start backend + frontend (backgrounded), open the app, execute a buy and a sell from the trade bar, confirm cash/positions/header update instantly with no dialog and no page reload; confirm P&L recolors live as the price stream ticks |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (per `02-0{1,2,3,4}-PLAN.md`'s `<verify>` blocks)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (all 8 tasks across the 4 plans carry automated verify commands)
- [x] Wave 0 covers all MISSING references (both new test files listed above)
- [x] No watch-mode flags (all commands are one-shot `pytest -x`/`-v`, no `--watch`)
- [x] Feedback latency < 5s (mirrors Phase 1's 94-test suite at 1.6s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-08-03 (backfilled by the orchestrator directly from `02-RESEARCH.md`'s already-complete `## Validation Architecture` section, after the plan-checker correctly flagged this file's absence — a step-ordering miss in this session's plan-phase orchestration, not a content gap; RESEARCH.md's validation content was already complete and detailed)
