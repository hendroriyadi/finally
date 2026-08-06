# Pitfalls Research

**Domain:** AI trading workstation — SQLite persistence, portfolio/trade math, LLM auto-execution, SSE frontend, single-container Docker
**Researched:** 2026-08-01
**Confidence:** MEDIUM (web search cross-referenced across 3-10 sources per topic; no official framework docs contradicted these findings, but none are project-verified yet)

## Critical Pitfalls

### Pitfall 1: Float arithmetic corrupts cash balance, avg_cost, and P&L over time

**What goes wrong:**
Using Python `float` for `cash_balance`, `avg_cost`, `quantity` (fractional shares), and P&L math produces values like `0.30000000000000004`. Individually tiny, these errors compound across many trades and portfolio snapshots — a user's displayed cash balance drifts from the "true" value, average cost basis after several partial buys/sells becomes visibly wrong, and P&L percentages don't reconcile with manual calculation. This is especially bad here because `avg_cost` is recalculated on every buy (weighted average) and `quantity` supports fractional shares, so rounding compounds fastest exactly where correctness matters most (repeated buys of the same ticker).

**Why it happens:**
Binary floating point cannot exactly represent most decimal fractions. Developers default to `float` because SQLite's `REAL` column type maps naturally to it, and the PLAN.md schema literally specifies `REAL` for `quantity`, `avg_cost`, `cash_balance`, `price`, and `total_value`. Nobody notices until a demo where numbers visibly don't add up.

**How to avoid:**
- Do all money/quantity math in Python using `Decimal` (constructed from strings, e.g. `Decimal("10.5")`, never `Decimal(10.5)`), converting to/from `float`/`REAL` only at the SQLite storage boundary.
- Round only once, at the final display/storage step — never round intermediate values (e.g. don't round `avg_cost` after each trade, only when displaying).
- Write a dedicated pytest module that runs a sequence of buys/sells and asserts the final cash balance and avg_cost match hand-calculated Decimal values exactly (not `pytest.approx`).
- Keep the weighted-average-cost formula centralized in one function (`recalculate_position`) so rounding behavior is consistent everywhere it's used.

**Warning signs:**
- Portfolio total value displayed doesn't exactly equal cash + sum(positions × price) when checked with a calculator.
- Unit tests use `pytest.approx()` for money assertions instead of exact equality — a sign floats are already in play and being tolerated rather than fixed.

**Phase to address:**
Portfolio/trade-execution API phase (the phase that implements `POST /api/portfolio/trade` and position/avg_cost recalculation logic).

---

### Pitfall 2: Check-then-deduct race condition on cash balance and share quantity

**What goes wrong:**
The natural implementation of trade execution is: (1) read `cash_balance`/`position.quantity`, (2) validate sufficient funds/shares in Python, (3) write updated values. Between steps 1 and 3, if two trade requests for the same user execute concurrently (e.g., a manual trade click racing with an LLM-triggered auto-execution, or the frontend double-firing on a slow network), both can pass the check before either commits, letting the user "sell" shares they don't have or spend cash they don't have — corrupting `cash_balance` into a negative number or `positions.quantity` into a negative number.

**Why it happens:**
This is a single-user app so the risk feels academic, but it's very real here specifically because trades can originate from two different code paths that both call the same trade-execution logic concurrently: the manual trade bar and the LLM's auto-executed `trades[]` array in a chat response. A user chatting "buy AAPL" while also clicking the manual buy button, or the frontend firing a duplicate request on retry, creates exactly this window. FastAPI's async model doesn't prevent this — `await` points inside the check-then-write sequence let another request interleave.

**How to avoid:**
- Make the balance/quantity check and the update a single atomic SQL statement, not separate read-then-write in Python: e.g. `UPDATE users_profile SET cash_balance = cash_balance - :cost WHERE id = :user_id AND cash_balance >= :cost`, then check `rowcount == 1`; if 0 rows affected, reject as insufficient funds. Same pattern for `positions.quantity` on sells.
- Alternatively, serialize all trade execution (manual and LLM-triggered) through a single `asyncio.Lock` per user (trivial here since there's exactly one user) so trade application is never concurrent within the process.
- Because SQLite only allows one writer at a time anyway (see Pitfall 3), wrapping the whole check+update in one `BEGIN IMMEDIATE` transaction is a natural fit and gets this correctness for free.

**Warning signs:**
- Trade execution code has a visible gap between "read current balance" and "write new balance" as separate statements.
- No test exists that fires two trades for the same ticker concurrently and asserts final state is consistent.

**Phase to address:**
Portfolio/trade-execution API phase. Verify with a concurrency test (fire N concurrent buy requests that collectively exceed cash balance; assert exactly enough succeed to exhaust cash and the rest are rejected with no negative balance).

---

### Pitfall 3: SQLite "database is locked" errors under concurrent access from multiple background tasks + API requests

**What goes wrong:**
This app has several concurrent writers to the same SQLite file: the trade-execution endpoint, the LLM chat endpoint (which also executes trades), the 30-second portfolio-snapshot background task, and potentially the market-data background task if it ever persists anything. SQLite allows only one writer at a time; without WAL mode and a busy timeout, concurrent writes throw `SQLITE_BUSY: database is locked` and requests fail with 500s — often intermittently, making it hard to reproduce and easy to ship broken.

**Why it happens:**
Default SQLite journal mode (rollback journal) locks the entire database file for the duration of a write and errors immediately if another writer holds the lock, rather than waiting. Developers using `aiosqlite` or plain `sqlite3` without setting `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout` hit this the moment two things write around the same time — which, with a 30-second snapshot task running for the app's entire lifetime, is not a rare edge case.

**How to avoid:**
- Enable `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` (or higher) on every connection at startup — WAL allows readers to proceed while one writer is active, and busy_timeout makes SQLite retry/wait instead of erroring immediately.
- Keep write transactions as short as possible: acquire the connection, execute, commit, release — never hold a connection open across an `await` that calls out to the LLM or another I/O operation.
- Prefer a single serialized write path (one connection or a tiny connection pool with a write mutex) over opening many concurrent connections for writes; SQLite's single-writer limitation makes a connection pool for writes largely pointless and only adds contention.
- Set `PRAGMA synchronous=NORMAL` (safe when combined with WAL) for better write throughput without sacrificing durability guarantees needed here.

**Warning signs:**
- Intermittent 500 errors on `/api/portfolio/trade` or `/api/chat` that don't reproduce reliably, especially when they coincide with the ~30s snapshot interval.
- No `PRAGMA` statements visible anywhere in the database connection setup code.

**Phase to address:**
Database/schema phase (set WAL + busy_timeout as part of initial connection setup, before any other phase writes to the DB). Verify by running the portfolio-snapshot background task alongside a burst of trade requests in a test and confirming no lock errors.

---

### Pitfall 4: LLM auto-executes trades from structured output with no server-side re-validation, or trusts the LLM's own arithmetic

**What goes wrong:**
Because PLAN.md deliberately has no confirmation dialog, the chat endpoint parses the LLM's structured JSON `trades[]` array and executes them directly. Two distinct failure modes emerge: (1) the code executes trades using values taken directly from the LLM's output without running them through the exact same validation path (sufficient cash, sufficient shares, valid ticker) as manual trades — meaning a hallucinated ticker or a quantity larger than the user owns silently corrupts state or crashes; (2) if the LLM is asked to reason about quantities, prices, or P&L in its own text and that reasoning is used anywhere downstream, LLM arithmetic is unreliable and shouldn't be trusted for anything financial — only structured fields, validated server-side, should drive state changes.

**Why it happens:**
It's tempting to treat "the LLM said do a $5,000 buy of AAPL" as equivalent to "the user clicked buy" and route it through a shortcut. But the LLM output is untrusted input (it can hallucinate a ticker not in the watchlist, a fractional quantity that's absurd, or duplicate a trade if the response is retried) and, separately, prompt injection is a real risk: if any user-supplied or fetched text ever gets echoed back into context (e.g., a watchlist ticker name, a pasted news snippet in a future feature), it could attempt to steer the LLM into recommending/executing unintended trades. Even without malicious input, models are known to follow embedded instructions regardless of source, so treating "the model said so" as authorization is fragile.

**How to avoid:**
- Route every LLM-proposed trade through the identical `execute_trade()` function and validation used for manual trades — same insufficient-funds/insufficient-shares checks, same atomic update pattern (Pitfall 2). Never bypass validation because "the LLM already checked."
- Validate ticker symbols against the current watchlist (or a known-symbol allowlist) before executing — reject and report back to the LLM/user rather than attempting an unknown ticker.
- Never let the LLM's own stated numbers (e.g., "that will cost $1,230") drive stored state — always recompute price × quantity server-side from the live price cache at execution time, and only use the LLM's `ticker`/`side`/`quantity` fields as the trade request, exactly like a manual order.
- Treat structured-output parsing defensively (see Pitfall 5): if `trades[]` is malformed or a trade fails validation, surface the error back into the chat response ("insufficient funds for that trade") rather than crashing the endpoint or silently dropping it.
- Log every LLM-triggered action (already covered by the `chat_messages.actions` column) so any unexpected trade is traceable to the exact prompt/response that caused it.

**Warning signs:**
- Chat endpoint code path for executing trades looks different from the manual trade endpoint's validation logic (duplicated or divergent logic is the tell).
- No test exercises "LLM proposes a trade for a ticker not on the watchlist" or "LLM proposes a buy that exceeds cash balance."

**Phase to address:**
Chat/LLM integration phase. Verify with tests that feed crafted (mocked) LLM responses containing invalid tickers, oversized quantities, and malformed JSON, asserting the system rejects/reports rather than corrupting state.

---

### Pitfall 5: Structured-output parsing assumes well-formed JSON matching the schema every time

**What goes wrong:**
LiteLLM's OpenRouter integration has known rough edges with structured outputs: OpenRouter's own adapter has, at various points, sent the wrong `response_format.type`, and `supports_response_schema` detection for OpenRouter models can be unreliable in LiteLLM depending on version. Even with "response healing" features on OpenRouter's side fixing JSON *syntax* errors, a response can still be syntactically valid JSON that doesn't match the expected *schema* (missing `message` field, `trades` present but malformed, extra/renamed keys, `quantity` as a string instead of a number). Code that does `json.loads(response)` and directly indexes into `["trades"]` without schema validation will throw unhandled exceptions or, worse, silently execute a malformed trade if the LLM/parser coerces unexpected types.

**Why it happens:**
Structured-output support in LiteLLM→OpenRouter→Cerebras is a longer chain than a direct OpenAI call, and each hop (LiteLLM's request translation, OpenRouter's routing, Cerebras's inference of an open model) is a place where schema enforcement can be imperfect. Developers test against a handful of "happy path" prompts during development and don't budget for the occasional malformed response in production.

**How to avoid:**
- Validate every LLM response against a Pydantic model (or equivalent JSON schema validator) before touching the parsed data — reject/retry on validation failure rather than trusting `json.loads()` output directly.
- Wrap the LLM call + parse in a try/except that, on failure, returns a graceful chat response ("I had trouble processing that, please try again") instead of a 500 error, and does not execute any trades from a partially-parsed response.
- Test with `LLM_MOCK=true` using both well-formed and deliberately malformed mock responses (missing fields, wrong types, extra fields) to exercise the failure path, not just the happy path.
- Pin/verify the exact `response_format` LiteLLM sends to OpenRouter for the `openrouter/openai/gpt-oss-120b` model during initial integration (check via cerebras-inference skill guidance) rather than assuming structured outputs "just work" the first time.

**Warning signs:**
- Chat endpoint has no try/except around JSON parsing of the LLM response.
- No Pydantic (or similar) model validates the LLM's structured output before it's used to execute trades.

**Phase to address:**
Chat/LLM integration phase.

---

### Pitfall 6: SSE reconnection silently loses price updates or creates duplicate streams

**What goes wrong:**
The browser's native `EventSource` auto-reconnects on disconnect (~3s default retry) and, if the server sends `id:` fields on each event, resends a `Last-Event-ID` header on reconnect. If the server ignores that header and just resumes streaming from "now," any price ticks that occurred during the disconnect window are silently lost — for this app that mainly means a gap in the frontend-accumulated sparkline data (since sparklines are built client-side from the SSE stream, not fetched from history). Separately, if frontend code manually closes and recreates the `EventSource` (e.g., in a `useEffect` cleanup that doesn't run before a new connection is opened, or on window focus/visibility handlers), it's easy to end up with two simultaneous open connections to `/api/stream/prices`, doubling server load and causing duplicate/out-of-order price events on the client.

**Why it happens:**
`EventSource`'s reconnection is automatic and mostly invisible, so it's easy to build and test only the "stays connected" happy path. React's effect lifecycle (especially in StrictMode, which double-invokes effects in development) makes it easy to accidentally open a second connection without closing the first.

**How to avoid:**
- In the single `useEffect` that creates the `EventSource`, always return a cleanup function that calls `.close()`, and never create a new `EventSource` without first closing any existing one (guard with a ref).
- Since sparklines are purely accumulated client-side from "since page load" (per PLAN.md), a gap on reconnect is cosmetically acceptable (sparkline has a visible flat/skip) but should not be silently swallowed as an error — surface the `yellow` "reconnecting" status (already planned in the header) whenever `EventSource.onerror` fires, and only clear it on the next successful `onmessage`.
- Do not rely on `Last-Event-ID` for correctness in this app (state loss on reconnect is acceptable given prices are always re-derived from the live cache), but do make sure the *connection status indicator* accurately reflects reconnecting vs. connected vs. failed — this is a named PLAN.md requirement (Section 2/10) and easy to fake with a static "connected" dot that never actually reflects `EventSource.readyState`.
- Test SSE resilience explicitly (already called out in PLAN.md Section 12): disconnect the backend mid-stream in an E2E test and verify the frontend shows "reconnecting" then recovers without duplicate ticker rows or frozen prices.

**Warning signs:**
- Connection status dot is hardcoded to green rather than driven by `EventSource.readyState`/`onerror`/`onopen` events.
- No cleanup function in the `useEffect` that opens the `EventSource`.

**Phase to address:**
Frontend SSE integration phase (watchlist/live-price streaming). Verify via the E2E "SSE resilience" scenario already specified in PLAN.md §12.

---

### Pitfall 7: Lazy SQLite schema init races or partially initializes the database on concurrent/first-request startup

**What goes wrong:**
PLAN.md specifies lazy initialization: the backend checks for the SQLite file/tables on startup or first request and creates+seeds if missing. If this check-then-create logic isn't idempotent and atomic, two things can go wrong in a Dockerized deployment: (1) if FastAPI runs with multiple workers/processes (e.g., `uvicorn --workers N` or a process manager that starts several instances), each can race to check "does the table exist?" simultaneously and both attempt `CREATE TABLE`, with the loser crashing on "table already exists," or both attempt to seed the default watchlist/user profile, causing UNIQUE constraint violations or duplicate seed rows; (2) if init happens on first HTTP request rather than at app startup, the very first request(s) hitting the server concurrently (e.g., the frontend's initial parallel calls to `/api/watchlist`, `/api/portfolio`, and opening the SSE stream) can race against the not-yet-created schema.

**Why it happens:**
"Lazy init on first request" sounds simple but conflates two different lifecycles: process startup and request handling. It's easy to write `if not table_exists(): create_and_seed()` without wrapping it in a transaction or a startup-time lock, especially since single-worker local dev never surfaces the race.

**How to avoid:**
- Run schema creation and seeding during FastAPI's `lifespan`/startup event, not on first request — this guarantees it happens exactly once per process before any request is served, and (with a single-container, single-process deployment per PLAN.md's "single Docker container" model) there's no multi-worker race to begin with. Explicitly run uvicorn with a single worker process, since SQLite's single-writer model doesn't benefit from multiple workers anyway.
- Make schema creation idempotent regardless: `CREATE TABLE IF NOT EXISTS` for every table, and `INSERT OR IGNORE` (or a `SELECT` existence check inside the same transaction) for seed data, so re-running init on every startup (e.g., container restart with an existing volume) is always safe and never duplicates rows.
- Make sure the Docker volume mount path (`db/` → `/app/db`) exists and is writable before the app starts; a missing/read-only mount surfaces as a confusing "unable to open database file" error that looks like a code bug.
- Test the exact restart scenario: start the container fresh (empty volume) → verify seed data appears once; stop and restart the same container/volume → verify no duplicate seed rows and existing user data (trades, cash balance) persists unchanged.

**Warning signs:**
- Schema/seed logic lives inside a request handler or dependency rather than a `lifespan` startup hook.
- No `IF NOT EXISTS` / `OR IGNORE` in the DDL or seed `INSERT` statements.
- Dockerfile/CMD doesn't explicitly pin `--workers 1` (or equivalent single-process guarantee).

**Phase to address:**
Database/schema phase, verified again in the Docker packaging phase (restart-with-existing-volume test belongs there since it's specifically about container lifecycle).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Storing money/quantity as `float`/`REAL` instead of `Decimal` | Simpler serialization, matches SQLite's native type | Silent arithmetic drift in avg_cost/cash balance that's hard to debug once compounded | Never — fix from the start; cost of switching later is a full data-model rewrite |
| Skipping atomic UPDATE-with-WHERE for balance checks, using app-level read-then-write | Faster to write initially | Race condition corrupts balances under any concurrent trade path (manual + LLM) | Never — this is a single small function; no reason to defer |
| Executing LLM trades through a separate code path from manual trades | Faster to bolt the chat feature on | Validation drift — a fix to manual trade validation doesn't automatically protect LLM-triggered trades | Never — always route through one `execute_trade()` |
| Running schema init on first request instead of app startup lifespan | Marginally less code to wire up | Race conditions on cold start, harder to reason about ordering with SSE/other startup tasks | Only acceptable for a true single-process, single-request-at-a-time toy; not here given SSE + concurrent initial page-load requests |
| No retry/backoff on LLM call failures (just surface the error) | Simpler chat endpoint | Flaky demo experience if OpenRouter/Cerebras has a transient hiccup | Acceptable for MVP given `LLM_MOCK=true` covers CI; add one retry before shipping to real users |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-------------------|
| LiteLLM → OpenRouter → Cerebras structured outputs | Assuming `response_format: json_schema` is honored end-to-end without checking; not validating the parsed response against a Pydantic model | Explicitly verify the request LiteLLM sends (via cerebras-inference skill guidance), and always validate the response against a schema before use — treat "valid JSON" and "matches schema" as two separate checks |
| Massive/Polygon.io REST client (optional, already built) with new SSE route | Re-polling or re-fetching from Massive inside the new SSE endpoint instead of reading the existing shared price cache | SSE route must only read from the already-implemented in-memory price cache; no new data-fetching logic per PROJECT.md constraint |
| Next.js static export served by FastAPI | Client-side routes/assets 404 because FastAPI's catch-all route doesn't handle Next.js's exported file structure (trailing slashes, `_next/` asset paths) correctly | Mount the static export directory explicitly and add a catch-all fallback to `index.html` for client-side routing, tested against the actual `next export` output structure, not assumptions |
| Docker multi-stage build (Node build → Python runtime) | Frontend `output: 'export'` not producing static files where the Python stage expects them (e.g. hardcoded API base URL baked in that only works at a different origin) | Frontend must call relative `/api/*` paths (already specified in PLAN.md) with no build-time env var pointing at a different origin, so the static export works identically when served by FastAPI on port 8000 |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Portfolio-snapshot background task and trade execution both writing to SQLite without WAL | Intermittent "database is locked" errors that get worse the more frequently snapshots are taken | WAL mode + busy_timeout (Pitfall 3) | Noticeable even at single-user scale once the 30s snapshot task overlaps a trade request |
| Recomputing full portfolio valuation (positions × live price) on every SSE tick server-side (if ever added) | CPU/DB load scales with number of watched tickers × update frequency | Keep valuation computation client-side or only on-demand (`/api/portfolio` GET), not inside the SSE push loop | Would surface immediately if someone "optimizes" by pushing computed portfolio value over SSE instead of raw prices |
| `chat_messages` history grows unbounded and is fully reloaded into every LLM prompt | LLM context/cost grows every conversation turn, latency creeps up over a long session | Cap conversation history sent to the LLM (e.g., last N messages) per PLAN.md's "recent conversation history" wording — don't load the entire table | Becomes visible after ~20-30 chat turns in a single session |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Trusting LLM structured output as pre-validated | LLM (or injected content it reads) could trigger trades on invalid tickers/quantities, or exploit validation gaps the manual-trade path doesn't have | Route every LLM trade through identical server-side validation as manual trades (Pitfall 4) |
| No bounds checking on trade quantity from either manual or LLM path | Absurd quantities (negative, NaN, extremely large) could corrupt `positions.quantity` or crash P&L math | Validate `quantity > 0` and finite/numeric on every trade request, both manual and LLM-originated, at the single shared `execute_trade()` entry point |
| SQLite file world-writable inside the Docker volume | Low risk here (single-user, local demo) but sloppy container hygiene | Ensure the `db/` directory and file have sane ownership/permissions in the Dockerfile, not run as root unnecessarily |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Connection status dot doesn't reflect real `EventSource` state | User trusts stale prices believing they're live | Drive the dot directly from `EventSource.onopen`/`onerror`/reconnect state, not a static assumption |
| LLM trade auto-executes with no visible confirmation and the chat response arrives before the SSE-driven portfolio UI updates | User sees a chat message claiming a trade happened but the positions table/cash balance appears momentarily stale, looking like a bug | Have the chat response's "action confirmations" (per PLAN.md §10) trigger an immediate optimistic refresh of portfolio state in the frontend rather than waiting for the next poll/snapshot |
| Sparklines silently show a flat gap after an SSE reconnect with no indication why | User thinks the ticker stopped moving | Tie the sparkline/price display to the same connection-status signal so a reconnect gap is visually distinguishable from "price didn't change" |

## "Looks Done But Isn't" Checklist

- [ ] **Trade execution:** Often missing atomic check-and-deduct — verify with a concurrency test firing simultaneous buys that collectively exceed cash balance.
- [ ] **LLM auto-execution:** Often missing shared validation with manual trades — verify the LLM trade path and manual trade path call the exact same function, not parallel implementations.
- [ ] **SSE connection status:** Often hardcoded/static — verify by killing the backend mid-session and confirming the dot turns yellow/red and recovers.
- [ ] **SQLite lazy init:** Often works on fresh container but breaks on restart-with-existing-volume — verify by stopping/restarting the container against the same volume and confirming no duplicate seed rows and prior trades/cash persist.
- [ ] **Money math:** Often "looks right" in the UI (rounded to 2 decimals for display) while the underlying stored values have drifted — verify with an exact (non-approx) unit test asserting cash balance after a sequence of trades matches hand-computed Decimal values.
- [ ] **Structured-output parsing:** Often only tested against well-formed mock LLM responses — verify by feeding malformed/missing-field mock responses through `LLM_MOCK` and confirming graceful degradation, not a 500.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|------------------|
| Float-based money/quantity already shipped | MEDIUM | Migrate storage/computation to Decimal, write a one-time data migration that re-derives `avg_cost`/`cash_balance` from the append-only `trades` log (since it's the source of truth) rather than trusting the drifted `positions`/`users_profile` rows |
| Race condition already caused a negative balance in testing/demo | LOW | Reset the SQLite volume (fresh seed) for demo purposes; fix the atomic UPDATE pattern before next session — no production users to migrate |
| LLM executed an unintended/invalid trade | LOW | Since it's a simulated portfolio, revert via a compensating trade or reset the volume; add the missing validation before continuing |
| SQLite lock errors under load | LOW | Add WAL + busy_timeout pragmas; no data loss typically, just failed requests that can be retried |
| Duplicate seed rows from a lazy-init race | LOW | Add `UNIQUE` constraint enforcement (already specified in PLAN.md schema) so duplicates fail loudly instead of silently double-seeding; clean up via `DELETE` keeping the earliest row, or just reset the volume during development |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| Float arithmetic drift | Portfolio/trade-execution phase | Exact-equality unit tests on cash/avg_cost after a scripted trade sequence |
| Check-then-deduct race condition | Portfolio/trade-execution phase | Concurrency test: N simultaneous trades exceeding available cash/shares |
| SQLite "database is locked" | Database/schema phase (connection setup) | Test snapshot background task running concurrently with a burst of trades, no lock errors |
| LLM trades bypass shared validation | Chat/LLM integration phase | Test LLM-mocked invalid-ticker and insufficient-funds trade proposals get rejected, not silently corrupted |
| Structured-output parsing fragility | Chat/LLM integration phase | Test malformed/schema-violating mock LLM responses degrade gracefully |
| SSE reconnection data loss / duplicate connections | Frontend SSE integration phase | E2E "SSE resilience" test (disconnect/reconnect, verify status indicator and no duplicate rows) per PLAN.md §12 |
| Lazy SQLite init race / non-idempotent seeding | Database/schema phase, re-verified in Docker packaging phase | Fresh-volume start test + restart-with-existing-volume test, both asserting exactly one seed set and no duplicate rows |

## Sources

- [SQLAlchemy Database Locks Using FastAPI: A Simple Guide](https://medium.com/@mojimich2015/sqlalchemy-database-locks-using-fastapi-a-simple-guide-3e7dcd552d87) — MEDIUM confidence
- [Using SQLite and asyncio effectively — Piccolo docs](https://piccolo-orm.readthedocs.io/en/1.1.1/piccolo/tutorials/using_sqlite_and_asyncio_effectively.html) — MEDIUM confidence
- [The Concurrency Trap in FastAPI: From Race Conditions to Deadlocks with Global Variables](https://datasciocean.com/en/other/fastapi-race-condition/) — MEDIUM confidence
- [SQLite concurrent writes and "database is locked" errors](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) — MEDIUM confidence
- [Python floating-point arithmetic issues and limitations (official docs)](https://docs.python.org/3/tutorial/floatingpoint.html) — HIGH confidence (official Python docs)
- [You can use floating-point numbers for money (counterpoint, still confirms core risk)](https://www.evanjones.ca/floating-point-money.html) — MEDIUM confidence
- [Why financial calculations go wrong and how to get them right](https://dev.to/usmanzahidcode/why-financial-calculations-go-wrong-and-how-to-get-them-right-34gm) — LOW-MEDIUM confidence
- [Assessing Automated Prompt Injection Attacks in Agentic Environments (arXiv)](https://arxiv.org/pdf/2606.10525) — MEDIUM confidence
- [SoK: Security of Autonomous LLM Agents in Agentic Commerce (arXiv)](https://arxiv.org/pdf/2604.15367) — MEDIUM confidence
- [Design Patterns for Securing LLM Agents against Prompt Injections (arXiv)](https://arxiv.org/html/2506.08837v2) — MEDIUM confidence
- [Last-Event-ID - Expert Guide to HTTP headers](https://http.dev/last-event-id) — MEDIUM confidence
- [Server-Sent Events: A Practical Guide for the Real World](https://tigerabrodi.blog/server-sent-events-a-practical-guide-for-the-real-world) — MEDIUM confidence
- [Using server-sent events — MDN](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) — HIGH confidence (official MDN docs)
- [SQLite User Forum: How to init a database schema with many concurrent accessors](https://sqlite.org/forum/info/1f241fba417b0e2bc02dc44c1004c5174a75a4d7f9fcd864352c92f153aa0d75) — HIGH confidence (official SQLite forum)
- [How to Run SQLite in Docker (When and How)](https://oneuptime.com/blog/post/2026-02-08-how-to-run-sqlite-in-docker-when-and-how/view) — MEDIUM confidence
- [Race conditions in money paths — TOCTOU on balance, paid-flag, and resource limits](https://vibe-eval.com/patterns/race-conditions-in-money-paths/) — MEDIUM confidence
- [OWASP: Race Conditions](https://owasp.org/www-community/pages/vulnerabilities/race_conditions) — HIGH confidence (official OWASP)
- [Race Condition Vulnerabilities in Financial Transaction Processing Systems](https://www.sourcery.ai/vulnerabilities/race-condition-financial-transactions) — MEDIUM confidence
- [aiosqlitepool (PyPI)](https://pypi.org/project/aiosqlitepool/) — MEDIUM confidence
- [SQLite WAL Mode and Connection Strategies for High-Throughput Apps](https://dev.to/software_mvp-factory/sqlite-wal-mode-and-connection-strategies-for-high-throughput-mobile-apps-beyond-the-basics-eh0) — LOW-MEDIUM confidence
- [Structured Outputs — OpenRouter docs](https://openrouter.ai/docs/guides/features/structured-outputs) — HIGH confidence (official OpenRouter docs)
- [Response Healing: Reduce JSON Defects by 80%+ — OpenRouter](https://openrouter.ai/announcements/response-healing-reduce-json-defects-by-80percent) — HIGH confidence (official OpenRouter docs)
- [LiteLLM GitHub Discussion: Forcing Structured JSON Output in LiteLLM + OpenRouter](https://github.com/BerriAI/litellm/discussions/11652) — MEDIUM confidence (project maintainer discussion)
- [LiteLLM GitHub Issue: Incorrect supports_response_schema for OpenRouter models (crewAI)](https://github.com/crewAIInc/crewAI/issues/2729) — MEDIUM confidence
- [OpenRouter Structured Output Broke Before Translation Quality Did — 3 Layers of Defense](https://dev.to/lovanaut55/openrouter-structured-output-broke-before-translation-quality-did-3-layers-of-defense-for-1cdb) — LOW-MEDIUM confidence

---
*Pitfalls research for: AI trading workstation (FinAlly) — SQLite/portfolio/LLM-auto-execution/SSE/Docker milestone*
*Researched: 2026-08-01*
