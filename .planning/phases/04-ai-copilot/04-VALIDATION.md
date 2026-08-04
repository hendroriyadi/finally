---
phase: 4
slug: ai-copilot
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-04
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Written directly from
> `04-RESEARCH.md`'s `## Validation Architecture` section BEFORE planning (proactive step, per the
> lesson learned in Phase 2 where this file was missed and caught late by the plan-checker — Phase 3
> and Phase 4 both do this proactively).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3+ / pytest-asyncio 0.24+ (backend, existing) [VERIFIED: `backend/pyproject.toml:33-39`]; no frontend test framework installed yet [VERIFIED: `frontend/package.json` has no Vitest/Jest/RTL dependency — checked this session] |
| **Config file** | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`, `asyncio_mode = "auto"`) |
| **Quick run command** | `cd backend && uv run --extra dev pytest tests/llm/ tests/db/test_chat.py tests/routes/test_chat.py -x` |
| **Full suite command** | `cd backend && uv run --extra dev pytest` |
| **Estimated runtime** | ~4-5 seconds (143 backend tests as of Phase 3, growing) |

---

## Sampling Rate

- **Per task commit:** `cd backend && uv run --extra dev pytest tests/llm/ tests/db/test_chat.py tests/routes/test_chat.py -x` (this phase's new surface only, fast feedback)
- **Per plan wave:** `cd backend && uv run --extra dev pytest` (full backend suite — proves no regression to Phases 1-3)
- **Phase gate:** Full backend suite green before `/gsd-verify-work`, plus a manual UAT pass covering UI-04's docked/collapsible/loading-indicator behavior. No frontend test framework exists yet (pre-existing gap, tracked project-wide under TEST-03/Phase 5, not introduced by this phase).

---

## Per-Task Verification Map

| Task ID | Requirement | Secure/Correct Behavior | Test Type | Automated Command | File Exists | Status |
|---------|-------------|--------------------------|-----------|-------------------|-------------|--------|
| (planner-assigned) | CHAT-01 | `POST /api/chat` returns a complete `{message, actions}` JSON body; `GET /api/chat/history` reflects a prior send (refresh-durability) | integration | `pytest tests/routes/test_chat.py::test_post_chat_returns_message_and_actions tests/routes/test_chat.py::test_history_reflects_a_prior_send -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | CHAT-02 | Portfolio context (cash, positions w/ P&L, watchlist w/ live prices) and recent history are included fresh on every call, never cached | unit | `pytest tests/routes/test_chat.py::test_context_builder_includes_cash_and_positions tests/routes/test_chat.py::test_context_builder_reflects_a_trade_made_between_two_turns -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | CHAT-03 | AI-initiated buy/sell debits/credits cash and updates positions identically to a manual trade via `execute_trade()`; a post-trade snapshot is recorded (Pitfall 3) | integration | `pytest tests/routes/test_chat.py::test_mock_triggered_trade_updates_portfolio_like_a_manual_trade tests/routes/test_chat.py::test_mock_triggered_trade_records_a_snapshot -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | CHAT-04 | AI-initiated watchlist add/remove updates the `watchlist` table AND the live market source (Pitfall 2) | integration | `pytest tests/routes/test_chat.py::test_mock_triggered_add_ticker_updates_watchlist_and_starts_streaming tests/routes/test_chat.py::test_mock_triggered_remove_ticker_stops_streaming -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | CHAT-05 | Response `actions` array carries one entry per executed action with `status`/human-readable fields | integration | `pytest tests/routes/test_chat.py::test_response_actions_include_one_entry_per_executed_action -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | CHAT-06 | A failed action (insufficient cash) produces `status: "error"` + human-readable message, HTTP 200, never 500; a malformed model response produces a graceful fallback message, HTTP 200 | unit + integration | `pytest tests/llm/test_client.py::test_malformed_json_returns_none tests/routes/test_chat.py::test_insufficient_cash_action_returns_error_status_not_500 tests/routes/test_chat.py::test_llm_failure_returns_graceful_fallback_message -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | CHAT-07 | `LLM_MOCK=true` never imports/calls `litellm`; produces deterministic, schema-valid `ChatCompletionResult` for identical input | unit | `pytest tests/llm/test_mock.py::test_mock_never_calls_litellm tests/llm/test_mock.py::test_mock_is_deterministic_for_identical_input -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | TEST-02 | Structured-output parsing: valid JSON parses; missing optional fields default to `[]`; malformed/non-JSON returns `None`; schema-violating JSON returns `None`; a raised litellm exception returns `None` | unit | `pytest tests/llm/test_client.py -x` | ❌ W0 | ⬜ pending |
| (planner-assigned) | UI-04 | Docked/collapsible chat panel: input, scrolling history, loading indicator | manual-only | No frontend test framework installed yet | ❌ N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/llm/__init__.py` — new test package
- [ ] `backend/tests/llm/test_client.py` — covers TEST-02, CHAT-06's malformed-output clause
- [ ] `backend/tests/llm/test_mock.py` — covers CHAT-07
- [ ] `backend/tests/db/test_chat.py` — covers `append_chat_message()`/`list_recent_chat_messages()` in isolation, mirroring `tests/db/test_snapshots.py`'s style (writer correctness, ordering, actions JSON round-trip)
- [ ] `backend/tests/routes/test_chat.py` — covers CHAT-01 through CHAT-06's integration angles, using the existing `client`/`temp_db` fixtures from `tests/conftest.py` with `monkeypatch.setenv("LLM_MOCK", "true")` set per-test
- [ ] No new fixtures needed — `client` (TestClient with real lifespan) and `temp_db` (isolated SQLite file) from `tests/conftest.py` cover every test above; `LLM_MOCK` is set via `monkeypatch.setenv()` inside each test function (must vary per-test, so it is not a shared fixture)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Chat panel is docked/collapsible, with a working collapse toggle | UI-04 | No frontend test framework installed yet (pre-existing gap, tracked under Phase 5's TEST-03) | Start backend + frontend (backgrounded), open the app, confirm the panel docks alongside the existing dashboard grid and collapses/expands via its toggle without losing draft input or scroll position |
| Send message → loading indicator → reply renders, with inline trade/watchlist confirmations | CHAT-01, CHAT-05, UI-04 | Same as above; also genuinely interactive (message send + async reply) | Send a message that mock-triggers a trade or watchlist change (or, if a working `OPENROUTER_API_KEY` is available outside this sandbox, a real one); confirm the loading indicator appears while awaiting the reply, then the assistant's message and an inline confirmation card both render |
| Conversation persists across a page refresh | CHAT-01 | Same as above | Send a few messages, reload the page, confirm the same transcript reappears via `GET /api/chat/history` |

---

## Validation Sign-Off

- [x] All tasks expected to have `<automated>` verify or Wave 0 dependencies for backend work; UI-04 (frontend interaction/visual) is manual-only by documented project-wide convention (no test framework yet)
- [x] Sampling continuity: every backend requirement (CHAT-01 through CHAT-07, TEST-02) carries automated verify per the map above
- [x] Wave 0 covers all MISSING references (all four new/extended test files listed above)
- [x] No watch-mode flags
- [x] Feedback latency < 5s (mirrors Phase 1/2/3's suite speed)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-08-04 (written proactively from `04-RESEARCH.md`'s complete `## Validation Architecture` section, before planning — avoiding the step-ordering miss that required a late backfill in Phase 2)
