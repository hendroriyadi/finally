---
phase: 04-ai-copilot
review: 04-REVIEW.md
fixed: 2026-08-04
findings_total: 8
findings_fixed: 8
findings_accepted: 0
---

# Phase 4: Code Review Fix Report

Applied directly by the orchestrator (not via `gsd-code-fixer`): three executor dispatches had already
failed on session usage limits during this phase, and every finding had a concrete, well-specified fix.

## Critical

### CR-01: Chat panel permanently hid new messages after one failed history load — **fixed**
A genuine bug, introduced in Plan 04-04. `ChatPanel`'s transcript branched on `historyError` first and
unconditionally, and the flag was set once by the mount fetch and never cleared. A single transient
failure of `GET /api/chat/history` (backend not yet up, a network blip) therefore stranded the user
permanently: `submit()` would go on to succeed, update `messages`, and call `refresh()`, but every one
of those updates rendered behind a banner the user could never get past.

Fixed in two independent places, either of which alone would close it:
1. **The render branch** (primary): messages now win whenever any exist. `historyError` only renders
   when there is genuinely nothing else to show. The error element also gained `role="alert"`.
2. **The flag** (secondary): a successful send clears `historyError`, since a completed round trip
   makes a stale mount-time failure untrue.

## Warnings

### WR-01: `journal_mode=WAL` set before `busy_timeout`, racing on a fresh database — **fixed**
The reviewer reproduced this against a fresh file with 8 threads racing `connect()`. I reproduced it
independently and found the reviewer's suggested fix (reordering the pragmas) **necessary but not
sufficient** — the `journal_mode=WAL` switch takes an exclusive lock and can return `SQLITE_BUSY`
*without* invoking the busy handler, so a timeout alone does not save it.

Measured, 40 trials × 8 racing threads on a fresh file each time:

| Version | "database is locked" failures |
|---|---|
| Original (WAL then timeout) | 3 |
| Reorder only (timeout then WAL) | 2 |
| Reorder **+ retry the switch** | **0** |

Shipped the reorder plus a bounded retry (`_WAL_SWITCH_ATTEMPTS = 10`, linear backoff). The
previously-flaky `test_concurrent_init_db_calls_do_not_raise` now passes **25/25** consecutive runs.
This code predates Phase 4 but is newly exercised by this phase's chat-persistence writers.

### WR-02: No timeout on the LLM call — **fixed**
`REQUEST_TIMEOUT_SECONDS = 30.0` passed to `litellm.completion()`. A hung upstream previously left the
user on "FinAlly is thinking…" indefinitely *and* held a worker thread for the duration. 30s is far
beyond the Cerebras path's expected latency (the assumption behind having no token streaming at all),
so a call reaching this bound has already failed in every sense that matters, and `chat_completion()`'s
existing `except Exception` turns it into the same graceful fallback as any other failure.

### WR-03: Textarea kept its grown height after send — **fixed**
`submit()` resets the element's height to `auto` when it clears the draft.

### WR-04: All send failures showed the same "check your connection" copy — **fixed**
A 4xx now renders "FinAlly couldn't accept that message — try rephrasing it." — telling a user to check
a connection that is working sends them to fix something that isn't broken. 5xx and non-`ApiError`
failures keep the original connectivity copy.

## Info

### IN-01: No length bounds on the LLM schemas' ticker fields — **fixed**
`Trade.ticker` and `WatchlistChange.ticker` now carry `Field(min_length=1, max_length=10)`, matching
`AddTickerRequest.ticker`'s bound. Defense in depth — `normalize_ticker()` remains the real validation —
but leaving them unbounded made model output the one ticker source in the app with no limit at its own
boundary, an asymmetry with no reason behind it.

### IN-02: Untyped `market_source` parameter — **fixed**
Both extracted helpers now annotate it as `MarketDataSource`.

### IN-03: TS/wire mismatch on `ChatActionResult` — **fixed, and it closed a latent crash**
Verified the actual wire against both endpoints: FastAPI serializes the response model's optional
fields as explicit `null` rather than omitting them, on **both** `POST /api/chat` and
`GET /api/chat/history`. The TS interface declared them `?` (i.e. `| undefined`), so
`ChatActionCard`'s `action.quantity !== undefined` guard would pass a `null` straight into
`.toFixed()`. Not reachable today (a successful trade always carries both fields), but one backend
change away from a runtime crash. Types are now `| null` and the guards are `!= null`, which handles
both.

## Verification

- `cd backend && uv run --extra dev ruff check app/ tests/` — clean
- `cd backend && uv run --extra dev pytest -q` — **209 passed**, 3 consecutive runs
- `test_concurrent_init_db_calls_do_not_raise` — 25/25 consecutive passes (was intermittently failing)
- `cd frontend && npm run lint` — clean
- `cd frontend && npm run build` — static export completes, no prerender error

---
**Total:** 8 of 8 fixed, 0 accepted. Two findings turned out to be more serious than their filed
severity: WR-01's suggested fix was insufficient on its own (needed a retry, measured), and IN-03 was
guarding a latent crash rather than a cosmetic type mismatch.
