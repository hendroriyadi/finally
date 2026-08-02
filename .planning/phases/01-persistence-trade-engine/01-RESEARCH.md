# Phase 1: Persistence & Trade Engine - Research

**Researched:** 2026-08-02
**Domain:** SQLite persistence (stdlib `sqlite3`), atomic transaction design, FastAPI lifespan, Decimal money math
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Schema (locked by PLAN.md §7 — not a grey area, restated here for the planner):**
- Six tables, all with `user_id TEXT DEFAULT 'default'`: `users_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages` (chat_messages table is created now for schema completeness even though Phase 3 is the first writer — avoids a schema migration later).
- IDs: TEXT PRIMARY KEY, UUIDs (except `users_profile.id` which is the literal string `"default"`).
- Timestamps: TEXT, ISO 8601 (`datetime.now(UTC).isoformat()`).
- Money/quantity columns (`cash_balance`, `quantity`, `avg_cost`, `price`, `total_value`): SQLite `REAL`. This is a PLAN.md constraint, not open for reconsideration (PROJECT.md: "Build exactly what PLAN.md specifies").
- UNIQUE `(user_id, ticker)` on `watchlist` and `positions`.
- Seed: one `users_profile` row (`cash_balance=10000.0`), ten `watchlist` rows (AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX — same list already seeded in `app/market/seed_prices.py`, so watchlist and market-data seed tickers must match).

**Decimal/Float Boundary:**
- Use Python `Decimal` for all money and share-quantity arithmetic inside the trade-execution and valuation functions (weighted-average cost, cash debit/credit, P&L) to avoid float drift across repeated trades.
- Convert `Decimal → float` only at the two boundaries: writing to SQLite `REAL` columns, and serializing to JSON for the API layer (Phase 2's concern, but the functions this phase writes should return `Decimal` or `float` consistently — return `float` from public repository functions so Phase 2 doesn't need to know about `Decimal`, keeping `Decimal` usage internal to the engine module).
- No fixed rounding/quantization scheme is imposed (e.g. no forced 2-decimal cash rounding) — fractional shares and prices can carry full precision; this avoids inventing a rounding rule PLAN.md never specified.

**Concurrency (DB-03):**
- On every connection: `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` (5 seconds). WAL is a one-time durable setting on the database file; `busy_timeout` is per-connection and must be set each time a connection opens.
- Follow the codebase's established pattern (documented in ARCHITECTURE.md, used by `massive_client.py`) for blocking I/O: use the stdlib `sqlite3` module (no new dependency), and wrap each blocking call in `asyncio.to_thread()` rather than introducing `aiosqlite` or an ORM.
- Trade execution (the check-then-write for sufficient cash/shares) must run as a single SQLite transaction (`BEGIN IMMEDIATE` or equivalent) so the check and the write are atomic against concurrent writers — this is what makes PORT-04 true under WAL with multiple threads/tasks issuing trades.

**Lazy Init:**
- On backend startup (or first DB access), check whether `db/finally.db` exists / has tables. If missing, execute `schema.sql` then `seed.sql`. No separate migration command; safe to call on every startup (idempotent).
- DB file path: `db/finally.db` relative to project root (the top-level `db/` volume-mount directory, not `backend/db/` which holds only the SQL definition files).

**Module Layout (planner's discretion within these constraints):**
- `backend/db/schema.sql`, `backend/db/seed.sql` are treated in CONTEXT.md as "already exist as empty placeholders" — **this is corrected below**, see Common Pitfalls: neither the directory nor the files exist on disk yet.
- Connection/init helper and repository/engine code goes under `backend/app/` in a new package (e.g. `backend/app/db/` for connection + lazy-init, `backend/app/portfolio/` for trade execution + valuation) — exact naming is the planner's call, following the existing `snake_case` module / `PascalCase` class conventions.
- Hard constraint: exactly ONE trade-execution entry point that both Phase 2's manual-trade route and Phase 3's AI-trade path call — no parallel/duplicate validation logic.

### Claude's Discretion
- Exact internal module/file names within `backend/app/db/` and `backend/app/portfolio/` (or whatever the planner names them).
- Whether lazy-init runs via FastAPI `lifespan` context manager or a startup event — planner's call, prefer whichever is more idiomatic for the FastAPI version already pinned in `pyproject.toml` (`fastapi>=0.115.0`, which supports `lifespan`).
- Exact concurrency test design proving "two writers don't get 'database is locked'" — e.g. `asyncio.gather()` of multiple concurrent trade calls, or multi-threaded — planner/executor's call, using `pytest-asyncio` (already a dev dependency).

### Deferred Ideas (OUT OF SCOPE)
- REST route handlers, request/response validation models — Phase 2.
- Any UI representation of positions/trades — Phase 4/5.
- LLM-initiated trades — Phase 3 (but must reuse this phase's `execute_trade()` unchanged, per CHAT-03).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DB-01 | System persists user cash balance, watchlist, positions, trades, portfolio snapshots, and chat history in SQLite | Schema DDL fully specified below (`## Code Examples` → schema.sql); six-table structure verbatim from PLAN.md §7 |
| DB-02 | Database schema and seed data are lazily initialized on startup if missing (no manual migration step) | `## Architecture Patterns` → Lazy Init pattern + FastAPI `lifespan` pattern (Context7-verified); idempotency test design in Validation Architecture |
| DB-03 | SQLite runs in WAL mode with `busy_timeout` set to support safe concurrent writers | `## Common Pitfalls` → WAL/busy_timeout pitfalls; `## Code Examples` → connection helper |
| PORT-04 | Trade execution validates sufficient cash (buy) or sufficient shares (sell) atomically before committing, preventing check-then-deduct races | `## Architecture Patterns` → BEGIN IMMEDIATE pattern; `## Code Examples` → `execute_trade()` |
| TEST-01 | Backend unit tests cover portfolio trade execution logic, P&L calculations, and edge cases (insufficient cash/shares, fractional shares) | `## Validation Architecture` → Requirements → Test Map; `## Common Pitfalls` → float-drift regression test design |
</phase_requirements>

## Summary

This phase has no new external dependencies — everything needed (`sqlite3`, `decimal`, `uuid`, `asyncio`, `contextlib`) is in the Python 3.12 stdlib, and `fastapi`/`pytest-asyncio` are already pinned in `backend/pyproject.toml`. The work is concentrated in three areas: (1) a small connection helper that opens a stdlib `sqlite3.Connection` per call with WAL mode + `busy_timeout` set, wrapped in `asyncio.to_thread()` — matching the existing `massive_client.py` pattern exactly; (2) a single `execute_trade()` function that opens an explicit `BEGIN IMMEDIATE` transaction so the "check funds/shares, then write" sequence is atomic against concurrent callers; (3) `Decimal`-internal money math that converts to `float` only at the SQLite-write and JSON-serialization boundaries.

The most consequential finding from this session is **not** technical-pattern research — it's an environment fact only discoverable by reading the actual filesystem and git history: `db/finally.db` (94 KB, six tables already created, 12 watchlist rows, 2 positions, 2 trades, 52 snapshots, WAL sidecar files present) is **already committed to git** (commit `f204e01`, "start of GSD"), and `.gitignore` does **not** match this filename — it only ignores `db.sqlite3`/`db.sqlite3-journal` (Django defaults), not `db/finally.db`. This directly contradicts PLAN.md §4's claim that "`finally.db` is gitignored." It also means `backend/db/schema.sql` and `backend/db/seed.sql` — which CONTEXT.md describes as "already exist as empty placeholders" — **do not exist at all**; the `backend/db/` directory itself is absent. The planner must add a task to (a) create `backend/db/` and its two SQL files from scratch, (b) fix `.gitignore` to actually exclude `db/*.db*`, and (c) remove the stale committed binary from git tracking (`git rm --cached db/finally.db`) before lazy-init logic is exercised, otherwise tests and manual runs will silently operate against pre-polluted, already-WAL-mode data instead of a clean seeded state.

**Primary recommendation:** Use stdlib `sqlite3` with `isolation_level=None` (manual transaction control) + explicit `PRAGMA busy_timeout=5000` and `PRAGMA journal_mode=WAL` per connection; wrap every connection-opening call in `asyncio.to_thread()`; execute trades inside an explicit `BEGIN IMMEDIATE ... COMMIT/ROLLBACK` block; keep `Decimal` internal to the trade-engine module and convert to `float` only at the repository-function return boundary. Delete `db/finally.db` from git tracking and fix `.gitignore` as a first task in this phase.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema definition (`schema.sql`, `seed.sql`) | Database / Storage | API / Backend | DDL is data-tier, but lazy-execution logic that runs it lives in the backend process |
| Connection lifecycle (WAL, busy_timeout, `asyncio.to_thread`) | API / Backend | Database / Storage | Enforced per-connection from backend code; the effect (WAL mode) is a durable DB-file property |
| Lazy init / seed-on-startup | API / Backend | Database / Storage | Runs from FastAPI `lifespan`; writes to the DB tier |
| Trade execution (`execute_trade`, atomic check-then-write) | API / Backend | Database / Storage | Business-logic validation lives in Python; atomicity guarantee is enforced by the SQLite transaction |
| Portfolio valuation (current value, unrealized P&L) | API / Backend | — | Pure computation combining `PriceCache` reads + `positions` rows; no DB write, no external I/O |
| Price lookups (`PriceCache.get_price`) | API / Backend | — | Reads the already-built, frozen in-memory cache; this phase never touches market-data internals |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlite3` (stdlib) | Python 3.12/3.13 bundled (SQLite engine 3.49.1 locally verified `[VERIFIED: local python3 -c "import sqlite3; print(sqlite3.sqlite_version)" → 3.49.1]`) | SQLite driver | No new dependency; matches existing codebase pattern (`massive_client.py` uses sync client + `asyncio.to_thread`), avoids ORM/async-driver complexity CONTEXT.md explicitly rejects |
| `decimal.Decimal` (stdlib) | bundled | Exact money/quantity arithmetic | Avoids binary-float drift across repeated buy/sell operations; CONTEXT.md locks this in |
| `uuid` (stdlib) | bundled | Primary key generation for `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages` | TEXT PRIMARY KEY UUIDs per PLAN.md §7 |
| `asyncio` (stdlib) | bundled | `asyncio.to_thread()` wrapping for blocking `sqlite3` calls | Established pattern, see `backend/app/market/massive_client.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `fastapi` | `0.128.7` locked `[VERIFIED: backend/uv.lock — "name = \"fastapi\"" / "version = \"0.128.7\""]` | `lifespan` context manager for startup init | Wiring lazy-init into app startup (Phase 2 wires the real app; this phase can expose an `init_db()` the app calls) |
| `pytest-asyncio` | `1.3.0` locked `[VERIFIED: backend/uv.lock — "name = \"pytest-asyncio\"" / "version = \"1.3.0\""]` | Async test support, `asyncio_mode = "auto"` already configured | All async trade-execution and concurrency tests |

No new packages are required for this phase — see Package Legitimacy Audit below.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `sqlite3` + `asyncio.to_thread` | `aiosqlite` | Native async API, but adds a dependency and a second concurrency model not used anywhere else in the codebase; CONTEXT.md explicitly rejects this |
| stdlib `sqlite3` + `asyncio.to_thread` | SQLAlchemy / SQLModel ORM | Would give migrations/relationship mapping, but PLAN.md never calls for an ORM and the schema is small/fixed (6 tables); adds significant surface area for a project whose stated goal is simplicity |
| Manual `Decimal`↔`float` boundary conversion | Store money as TEXT/INTEGER cents | More precise, but PLAN.md §7 explicitly specifies `REAL` columns for money/quantity — not open for reconsideration per CONTEXT.md |

**Installation:**
```bash
# No new packages — sqlite3, decimal, uuid are stdlib.
# fastapi and pytest-asyncio are already declared in backend/pyproject.toml.
cd backend && uv sync --extra dev
```

## Package Legitimacy Audit

**Not applicable — this phase introduces zero new external packages.** All functionality (`sqlite3`, `decimal`, `uuid`, `dataclasses`, `contextlib`, `asyncio`) is Python 3.12 stdlib. `fastapi` and `pytest-asyncio` are pre-existing pinned dependencies verified against `backend/uv.lock` above; no registry lookup or legitimacy check is required for stdlib modules or already-locked dependencies.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
FastAPI lifespan (startup)
        │
        ▼
 init_db(db_path) ──[asyncio.to_thread]──► sqlite3.connect(db_path)
        │                                          │
        │                                    PRAGMA journal_mode=WAL   (durable, one-time)
        │                                    PRAGMA busy_timeout=5000  (per-connection)
        │                                          │
        │                                    tables exist? ──no──► executescript(schema.sql)
        │                                          │                executescript(seed.sql)
        │                                         yes
        │                                          │
        ▼                                          ▼
 (app continues serving)                    connection closed
                                                    │
   ── runtime request path (Phase 2 will call these) ──
                                                    │
   execute_trade(ticker, qty, side, user_id) ──[asyncio.to_thread]──► sqlite3.connect(db_path)
        │                                                                   │
        │                                                          PRAGMA busy_timeout=5000
        │                                                          BEGIN IMMEDIATE
        │                                                                   │
        │◄──────────────── PriceCache.get_price(ticker) ────────────────────┤ (read, outside txn)
        │                                                                   │
        │                                          SELECT cash_balance / positions.quantity
        │                                          validate: buy → cash >= qty*price
        │                                                    sell → owned_qty >= qty
        │                                          ┌── insufficient ──► ROLLBACK, raise/return error
        │                                          │
        │                                     sufficient
        │                                          │
        │                          UPDATE users_profile.cash_balance
        │                          INSERT/UPDATE positions (weighted avg cost on buy;
        │                                                    delete row if qty → 0 on sell)
        │                          INSERT trades (append-only log)
        │                          INSERT portfolio_snapshots (immediately after trade, per PORT-06 —
        │                                                       Phase 2 wires the 30s background task,
        │                                                       this phase's engine just writes the row)
        │                                          COMMIT
        ▼
   returns float-typed result (Decimal used only internally)
```

### Recommended Project Structure
```
backend/
├── db/
│   ├── schema.sql          # CREATE TABLE x6 (does not exist yet — see Common Pitfalls)
│   └── seed.sql             # INSERT default user + 10 watchlist rows (does not exist yet)
├── app/
│   ├── db/
│   │   ├── __init__.py      # exports connection helper + init function
│   │   ├── connection.py    # get_connection(db_path) -> sqlite3.Connection (WAL + busy_timeout)
│   │   └── init.py          # init_db(db_path) -> bool (idempotent lazy init, runs schema+seed)
│   └── portfolio/
│       ├── __init__.py      # exports execute_trade, get_portfolio_value, repository functions
│       ├── repository.py    # CRUD-style functions per table (positions, trades, snapshots, cash)
│       ├── engine.py         # execute_trade() — the single validated entry point (PORT-04)
│       └── valuation.py      # pure functions: unrealized P&L, total portfolio value, % change
└── tests/
    ├── db/
    │   ├── __init__.py
    │   ├── conftest.py       # tmp_path-based isolated db fixture
    │   ├── test_connection.py
    │   └── test_init.py      # asserts idempotent lazy init (no double-seed)
    └── portfolio/
        ├── __init__.py
        ├── test_engine.py    # buy/sell, insufficient cash/shares, fractional shares, exact-balance
        ├── test_valuation.py
        └── test_concurrency.py  # asyncio.gather() concurrent trades, no "database is locked"
```

### Pattern 1: Connection helper with WAL + busy_timeout, wrapped for async

**What:** A small synchronous helper that opens a `sqlite3.Connection`, sets pragmas, and is always called through `asyncio.to_thread()` from async code — connection-per-call, not a shared pool. This matches the codebase's existing sync-in-thread pattern exactly (`massive_client.py`) and avoids the complexity of a connection pool for a single-user, single-file SQLite workload.

**When to use:** Every DB access from async route handlers, background tasks, or the trade engine.

**Example:**
```python
# Source: Python 3 stdlib docs (Context7 /python/cpython) — sqlite3.connect() signature,
# isolation_level semantics; cpython's own Lib/dbm/sqlite3.py demonstrates the
# "PRAGMA journal_mode=wal in a try/except OperationalError" soft-optimization pattern.
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_BUSY_TIMEOUT_MS = 5000


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a new SQLite connection with WAL mode and busy_timeout configured.

    isolation_level=None disables sqlite3's implicit "DEFERRED" transaction
    management so callers can issue explicit BEGIN IMMEDIATE / COMMIT / ROLLBACK
    (required for atomic check-then-write in execute_trade()).
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={DEFAULT_BUSY_TIMEOUT_MS}")
    return conn
```

Every async caller wraps the *entire* unit of work (not just `connect()`) in a single `asyncio.to_thread()` call, so the connection, transaction, and close all happen on the same worker thread — `sqlite3.Connection` objects are not safe to share across threads by default (`check_same_thread=True` is the default).

```python
import asyncio

async def get_cash_balance(db_path: Path, user_id: str = "default") -> float:
    def _run() -> float:
        conn = get_connection(db_path)
        try:
            row = conn.execute(
                "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
            ).fetchone()
            return row["cash_balance"]
        finally:
            conn.close()
    return await asyncio.to_thread(_run)
```

### Pattern 2: Atomic check-then-write via `BEGIN IMMEDIATE`

**What:** The default `sqlite3.connect()` isolation level is `'DEFERRED'` `[CITED: Context7 /python/cpython — sqlite3.connect() signature: isolation_level='DEFERRED' default]` — a DEFERRED transaction only acquires the write lock on the *first write statement*, meaning two concurrent callers can both pass a SELECT-based "sufficient funds?" check before either one writes, causing a race. `BEGIN IMMEDIATE` acquires the write lock at transaction start, so a concurrent second writer either serializes behind the first (waiting up to `busy_timeout`) or fails fast with `SQLITE_BUSY` — never both passing the check `[CITED: SQLite community guidance, cross-checked across multiple sources — "any transaction that will write should use BEGIN IMMEDIATE"]`. Under WAL mode, `IMMEDIATE` and `EXCLUSIVE` behave identically since WAL readers never block writers, but only one writer may hold the WAL write lock at a time regardless `[CITED: SQLite WAL documentation via community sources]`.

**When to use:** `execute_trade()` — the single validated path for both buy and sell.

**Example:**
```python
# Source: pattern synthesized from Python stdlib sqlite3 isolation_level docs
# (Context7 /python/cpython) + SQLite BEGIN IMMEDIATE community guidance (cross-checked)
from decimal import Decimal
from datetime import UTC, datetime
import uuid


class InsufficientFundsError(Exception):
    pass


class InsufficientSharesError(Exception):
    pass


def _execute_trade_sync(
    db_path: Path, ticker: str, quantity: Decimal, side: str,
    current_price: float, user_id: str = "default",
) -> dict:
    conn = get_connection(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            price = Decimal(str(current_price))
            cost = quantity * price

            cash_row = conn.execute(
                "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
            ).fetchone()
            cash = Decimal(str(cash_row["cash_balance"]))

            pos_row = conn.execute(
                "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            ).fetchone()
            owned_qty = Decimal(str(pos_row["quantity"])) if pos_row else Decimal(0)

            if side == "buy":
                if cost > cash:
                    raise InsufficientFundsError(f"Need {cost}, have {cash}")
                new_qty = owned_qty + quantity
                old_avg = Decimal(str(pos_row["avg_cost"])) if pos_row else Decimal(0)
                new_avg = ((owned_qty * old_avg) + (quantity * price)) / new_qty
                conn.execute(
                    "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
                    (float(cash - cost), user_id),
                )
                conn.execute(
                    """INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(user_id, ticker) DO UPDATE SET
                         quantity = excluded.quantity,
                         avg_cost = excluded.avg_cost,
                         updated_at = excluded.updated_at""",
                    (str(uuid.uuid4()), user_id, ticker, float(new_qty), float(new_avg),
                     datetime.now(UTC).isoformat()),
                )
            elif side == "sell":
                if quantity > owned_qty:
                    raise InsufficientSharesError(f"Own {owned_qty}, tried to sell {quantity}")
                new_qty = owned_qty - quantity
                conn.execute(
                    "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
                    (float(cash + cost), user_id),
                )
                if new_qty <= Decimal("1e-9"):
                    conn.execute(
                        "DELETE FROM positions WHERE user_id = ? AND ticker = ?",
                        (user_id, ticker),
                    )
                else:
                    conn.execute(
                        "UPDATE positions SET quantity = ?, updated_at = ? "
                        "WHERE user_id = ? AND ticker = ?",
                        (float(new_qty), datetime.now(UTC).isoformat(), user_id, ticker),
                    )
            else:
                raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")

            conn.execute(
                "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, ticker, side, float(quantity), float(price),
                 datetime.now(UTC).isoformat()),
            )
            conn.execute("COMMIT")
            return {"ticker": ticker, "side": side, "quantity": float(quantity), "price": float(price)}
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
```

Note: the `ON CONFLICT ... DO UPDATE` upsert requires SQLite ≥ 3.24 (bundled with Python 3.12+ is far newer — locally verified 3.49.1), so this is safe to use instead of a manual SELECT-then-INSERT-or-UPDATE branch.

### Pattern 3: FastAPI `lifespan` for lazy DB init

**What:** `fastapi>=0.93.0` (well below the `>=0.115.0` pinned here) recommends the `@asynccontextmanager`-decorated `lifespan` function over the deprecated `@app.on_event("startup")` decorator `[CITED: Context7 /websites/fastapi_tiangolo — "Define Lifespan Events in FastAPI" + release-notes 0.93.0 entry]`.

**When to use:** Wiring `init_db()` to run once when the FastAPI app starts (Phase 2 will own the actual `FastAPI()` app object; this phase should expose `init_db(db_path)` as a plain function so Phase 2's `lifespan` can call it — do not couple this phase's code to FastAPI at all, keeping it framework-agnostic and directly unit-testable).

**Example:**
```python
# Source: https://fastapi.tiangolo.com/advanced/events (Context7 /websites/fastapi_tiangolo)
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(DB_PATH)   # this phase's function — idempotent, safe on every startup
    yield
    # no cleanup needed for SQLite connections (they're opened/closed per-call)

app = FastAPI(lifespan=lifespan)
```

This phase does not need to write the `FastAPI()` app itself (no routes exist yet — Phase 2's job). It only needs to deliver `init_db(db_path: Path) -> None` as a plain async-callable function so Phase 2 can drop it into `lifespan` unchanged.

### Anti-Patterns to Avoid
- **Sharing one `sqlite3.Connection` across requests/threads:** `check_same_thread=True` is the default for a reason — the codebase's own pattern (`PriceCache` uses locks, `massive_client.py` uses one-shot `to_thread` calls) favors connection-per-operation over a shared connection or pool. Don't introduce a global connection.
- **Using default `isolation_level='DEFERRED'` for trade execution:** leaves a window where two concurrent trade calls both pass the balance check before either writes. Must use `isolation_level=None` + explicit `BEGIN IMMEDIATE`.
- **Constructing `Decimal` from a `float` directly** (`Decimal(10.1)`): imports the float's binary imprecision (`Decimal(10.1)` → `Decimal('10.0999999999999996447...')`). Always go through `str()`: `Decimal(str(10.1))` or construct from the SQL row value via `Decimal(str(row["cash_balance"]))`.
- **Leaving a `quantity=0` position row after a full sell:** per CONTEXT.md, this would render oddly in Phase 4/5's positions table and heatmap. Delete the row when quantity reaches (approximately) zero.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic check-then-write concurrency control | A custom in-process lock/mutex around trade execution | SQLite's own `BEGIN IMMEDIATE` transaction locking | A Python-level lock only protects against races *within this process*; SQLite's own locking is what actually matters once multiple connections exist (even multiple threads in the same process each open their own connection under the connection-per-call pattern), and it's already provided by the engine for free |
| Money precision | A custom fixed-point integer-cents encoder/decoder | stdlib `decimal.Decimal` | `Decimal` is exact, well-tested, and already the standard idiom; PLAN.md doesn't ask for cents-as-integers and that would be a bigger schema change than specified |
| Idempotent schema creation | Hand-written "check each table individually" branching logic | `CREATE TABLE IF NOT EXISTS` in `schema.sql` + a single "does `users_profile` have a row?" check before running `seed.sql` | Simpler, and SQLite's own `IF NOT EXISTS` guards make schema re-execution safe; only the *seed* step needs a manual idempotency guard (seed data doesn't have a `IF NOT EXISTS` SQL equivalent for `INSERT`) |

**Key insight:** In this domain, the two hard problems (atomic concurrency, exact money math) both have solved, well-documented library/language-level answers — reaching for a custom lock or a custom decimal encoding would be strictly worse and harder to test than what's already provided.

## Common Pitfalls

### Pitfall 1: `backend/db/` does not exist — CONTEXT.md's premise is wrong

**What goes wrong:** CONTEXT.md states `backend/db/schema.sql`, `backend/db/seed.sql` "already exist as empty placeholders per STRUCTURE.md — fill these in." This session verified via `ls` that **the `backend/db/` directory does not exist at all** on disk `[VERIFIED: ls /Users/hendro/Documents/Projects/finally/.claude/worktrees/gsd-settings/backend — output lists only app/, tests/, market_data_demo.py, pyproject.toml, uv.lock, CLAUDE.md — no db/ directory]`. STRUCTURE.md (a codebase-map doc, not filesystem truth) described an aspirational structure, not the actual state.

**Why it happens:** Codebase-map docs (STRUCTURE.md, ARCHITECTURE.md) are generated snapshots that can describe planned structure alongside implemented structure without clearly separating the two; CONTEXT.md's auto-generated mode inherited this ambiguity without re-verifying against the filesystem.

**How to avoid:** The plan's first task must create `backend/db/` and write `schema.sql`/`seed.sql` from scratch — not "fill in" pre-existing files. Verify with `ls backend/db/` before assuming any starting content exists.

**Warning signs:** A plan step that says "edit `backend/db/schema.sql`" (implying edit-in-place) rather than "create `backend/db/schema.sql`" will fail with a file-not-found or directory-not-found error.

### Pitfall 2: A stale, git-committed `db/finally.db` already exists with the target schema and polluted data

**What goes wrong:** `db/finally.db` (94,208 bytes) already exists at the top-level `db/` path and already contains all six target tables with data: `users_profile` (1 row), `watchlist` (**12** rows — not the expected 10), `positions` (2 rows), `trades` (2 rows), `portfolio_snapshots` (52 rows), `chat_messages` (4 rows) `[VERIFIED: sqlite3 db/finally.db ".schema" and per-table "select count(*)" run this session]`. WAL sidecar files (`db/finally.db-shm`, `db/finally.db-wal`) are present and untracked, meaning something already ran this file in WAL mode. Critically, **this file is tracked in git** — `git ls-files db/` returns `db/finally.db`, committed in `f204e01 "start of GSD"` — and `.gitignore` does not match it: the only DB-related patterns present are `db.sqlite3` and `db.sqlite3-journal` (Django-template leftovers), which do not match `db/finally.db` or its `-shm`/`-wal` sidecars `[VERIFIED: cat .gitignore this session — grep for "db" shows only "db.sqlite3" and "db.sqlite3-journal"]`. This directly contradicts PLAN.md §4: "`db/finally.db` is created at runtime, gitignored."

**Why it happens:** Likely an artifact of an earlier exploratory run (e.g. a demo, an earlier attempt at this phase, or a schema drafted outside of this planning cycle) that got swept into the initial "start of GSD" commit before `.gitignore` was written for this project's actual filenames.

**How to avoid:** Add a task early in this phase's plan: (1) `git rm --cached db/finally.db` to un-track the committed binary (leave the working-tree file or delete it — lazy-init will regenerate it), (2) add `db/*.db`, `db/*.db-shm`, `db/*.db-wal`, `db/*.db-journal` to `.gitignore` (keep `db/.gitkeep` tracked), (3) ensure lazy-init logic is exercised against a genuinely fresh/deleted file during manual verification, not the pre-existing polluted one. Do not assume "database exists → tables exist → skip init" is sufficient idempotency logic without also checking that the *seed row count* looks sane (e.g. seeded watchlist should be exactly the 10 PLAN.md tickers, not whatever ad-hoc set produced the 12 rows found here).

**Warning signs:** Manual testing that shows a watchlist of 12 tickers instead of 10, or positions/trades already present on what should be a "fresh install."

### Pitfall 3: `sqlite3`'s default transaction handling silently defeats atomicity

**What goes wrong:** If `execute_trade()` is written using the default `sqlite3.connect(db_path)` (no `isolation_level=None`), the module manages transactions implicitly with `DEFERRED` semantics before the first `INSERT`/`UPDATE`/`DELETE`. A read-then-write sequence (SELECT cash_balance, then later UPDATE it) does not hold a write lock during the SELECT, so two concurrent trade calls can both read a passing balance before either writes — exactly the race PORT-04 requires preventing.

**Why it happens:** `sqlite3`'s implicit transaction management optimizes for the common single-writer case and is easy to overlook when reading tutorials that only discuss autocommit vs. one implicit transaction mode.

**How to avoid:** Always open trade-execution connections with `isolation_level=None` and issue `conn.execute("BEGIN IMMEDIATE")` explicitly before the SELECT/validate/UPDATE sequence, `COMMIT` on success, `ROLLBACK` in the `except` branch.

**Warning signs:** A concurrency test using `asyncio.gather()` on multiple simultaneous buy orders (each individually affordable, but not affordable in aggregate) succeeds for more orders than the cash balance allows.

### Pitfall 4: `Decimal` constructed from a `float` re-imports the float's imprecision

**What goes wrong:** `Decimal(10.1)` produces `Decimal('10.0999999999999996447286321199499070644378662109375')` — the float's binary representation, not the decimal literal `[CITED: cross-checked web sources on Decimal/float conversion pitfalls, standard/well-known Python behavior]`. If a repository function reads a `REAL` column value (already a Python `float` once fetched by `sqlite3`) and does `Decimal(row["cash_balance"])` instead of `Decimal(str(row["cash_balance"]))`, the "exact arithmetic" guarantee is silently defeated at the read boundary.

**Why it happens:** `Decimal(float)` is valid Python and doesn't raise — it just silently produces an imprecise value, so this bug doesn't surface until a float-drift regression test specifically checks for it.

**How to avoid:** Establish one conversion helper used everywhere data crosses the REAL↔Decimal boundary — e.g. `def to_decimal(value: float) -> Decimal: return Decimal(str(value))` — and never call `Decimal(...)` directly on a raw float elsewhere in the trade-engine module.

**Warning signs:** A repeated buy/sell round-trip test (e.g. 1000 iterations) shows the final cash balance drifting away from the expected value by fractions of a cent.

## Code Examples

### Schema (`backend/db/schema.sql`)

Verbatim column/type/constraint specification per PLAN.md §7 `[CITED: /Users/hendro/Documents/Projects/finally/planning/PLAN.md §7 Database — read this session]`. The existing on-disk (but git-polluted) `db/finally.db` already contains an equivalent schema including `CHECK` constraints and indexes not explicitly required by PLAN.md but harmless/beneficial to keep (`[VERIFIED: sqlite3 db/finally.db ".schema" run this session]` — shown as a design reference, not a requirement to reuse the polluted file itself):

```sql
-- Source: PLAN.md §7 Database (schema fields, types, constraints) — this session's Read
CREATE TABLE IF NOT EXISTS users_profile (
    id           TEXT PRIMARY KEY DEFAULT 'default',
    cash_balance REAL NOT NULL DEFAULT 10000.0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id       TEXT PRIMARY KEY,
    user_id  TEXT NOT NULL DEFAULT 'default',
    ticker   TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS positions (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL DEFAULT 'default',
    ticker     TEXT NOT NULL,
    quantity   REAL NOT NULL,
    avg_cost   REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS trades (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default',
    ticker      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity    REAL NOT NULL,
    price       REAL NOT NULL,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default',
    total_value REAL NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL DEFAULT 'default',
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    actions    TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist (user_id);
CREATE INDEX IF NOT EXISTS idx_positions_user ON positions (user_id);
CREATE INDEX IF NOT EXISTS idx_trades_user_time ON trades (user_id, executed_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_user_time ON portfolio_snapshots (user_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_chat_user_time ON chat_messages (user_id, created_at);
```

### Seed (`backend/db/seed.sql`) — tickers must match `app/market/seed_prices.py`

```sql
-- Ticker list verbatim from backend/app/market/seed_prices.py SEED_PRICES keys
-- [VERIFIED: backend/app/market/seed_prices.py:4-15 — "AAPL": 190.00, "GOOGL": 175.00,
--  "MSFT": 420.00, "AMZN": 185.00, "TSLA": 250.00, "NVDA": 800.00, "META": 500.00,
--  "JPM": 195.00, "V": 280.00, "NFLX": 600.00]
INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at)
VALUES ('default', 10000.0, datetime('now'));

-- watchlist rows: seed.sql (or the Python seed step) must insert exactly these 10 tickers
-- with UUID ids and ISO timestamps generated in Python (SQL alone can't generate UUIDs
-- portably) — recommend seeding watchlist rows from Python using the same
-- SEED_PRICES.keys() list imported from app.market.seed_prices, not a second hardcoded
-- SQL list, to guarantee the two lists cannot drift apart (per CONTEXT.md's explicit warning).
```

Recommendation: because SQLite has no built-in UUID generation and PLAN.md requires TEXT UUIDs, seed the `watchlist` table's rows from Python (iterating `app.market.seed_prices.SEED_PRICES.keys()`) rather than a static `seed.sql` INSERT list — this is the only way to guarantee the two ticker lists (market simulator's seed prices and the DB watchlist) can never diverge, which is an explicit CONTEXT.md requirement. `seed.sql` itself can still hold the single `users_profile` INSERT since that has no UUID/dynamic-list concern.

### Valuation (pure functions, no DB writes)

```python
# Formulas synthesized from PLAN.md §2/§10 (unrealized P&L, % change) — no external source;
# standard portfolio-math definitions, not library-specific.
from decimal import Decimal

def unrealized_pnl(quantity: Decimal, avg_cost: Decimal, current_price: Decimal) -> Decimal:
    return (current_price - avg_cost) * quantity

def percent_change(avg_cost: Decimal, current_price: Decimal) -> Decimal:
    if avg_cost == 0:
        return Decimal(0)
    return ((current_price - avg_cost) / avg_cost) * Decimal(100)

def total_portfolio_value(cash_balance: Decimal, position_values: list[Decimal]) -> Decimal:
    return cash_balance + sum(position_values, start=Decimal(0))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `sqlite3.Connection.isolation_level` string values (`"DEFERRED"`/`"IMMEDIATE"`/`"EXCLUSIVE"`/`None`) | `sqlite3.Connection.autocommit` boolean/`LEGACY_TRANSACTION_CONTROL` attribute | Python 3.12 `[CITED: Context7 /python/cpython sqlite3 docs — connect() signature lists both isolation_level and autocommit parameters]` | Either API works on 3.12+; this research uses the more widely-documented `isolation_level=None` + explicit `BEGIN` pattern since it is unambiguous and portable to any 3.x version, but the planner may use `autocommit=True` equivalently if preferred |
| `@app.on_event("startup")` | `lifespan` async context manager | FastAPI 0.93.0 (2023) `[CITED: Context7 /websites/fastapi_tiangolo release-notes]` | `on_event` is deprecated; `lifespan` is the only pattern to use going forward, already assumed by CONTEXT.md |

**Deprecated/outdated:**
- `@app.on_event("startup")`/`@app.on_event("shutdown")`: superseded by `lifespan`; do not introduce this deprecated pattern even though Phase 2 (not this phase) is the one that will actually construct the `FastAPI()` app.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `BEGIN IMMEDIATE` community guidance ("any transaction that will write should use IMMEDIATE") is presented as MEDIUM-confidence cross-checked web guidance, not official SQLite documentation text quoted verbatim | Architecture Patterns → Pattern 2 | Low — this is well-established SQLite community practice consistent with SQLite's own locking model description (WAL readers never block writers; only one writer at a time), but the planner should treat the exact wording as paraphrase, not a direct quote from sqlite.org |
| A2 | Recommendation to delete a position row when quantity reaches ~zero (vs. zeroing it) | Common Pitfalls → Pitfall 4 / Code Examples | Low — CONTEXT.md explicitly leaves this as "planner's call" but flags the phantom-zero-row risk; deleting is the safer default for Phase 4/5 rendering, but this is a recommendation, not a verified requirement |
| A3 | `Decimal("1e-9")` as the "effectively zero" epsilon threshold for full-position sells | Code Examples → Pattern 2 | Low — no PLAN.md-specified tolerance exists; since trade quantities/prices flow through exact `Decimal` arithmetic without forced rounding, exact-quantity sells should produce an exact `Decimal(0)`, making the epsilon a defensive fallback rather than a load-bearing threshold — but if a future phase introduces rounding, this value may need revisiting |

## Open Questions

1. **Should the stale, committed `db/finally.db` be deleted from the working tree entirely, or left for lazy-init to detect/handle?**
   - What we know: it's already schema-compatible and git-tracked; lazy-init as specified ("if missing, create + seed") will NOT re-seed or fix it since tables already exist.
   - What's unclear: whether the plan should include an explicit "reset to clean state" step, or rely on `git rm --cached` + a fresh `db/finally.db` being generated by whoever runs the app next (a git-tracked-then-untracked file still exists on disk until manually deleted).
   - Recommendation: the plan should explicitly delete the working-tree `db/finally.db`/`-shm`/`-wal` files (not just untrack them) as part of the same task that fixes `.gitignore`, so the very next `uv run pytest` / app startup exercises real lazy-init against a truly absent file — this is the only way to end-to-end-verify DB-02.

2. **Where does the DB path (`db/finally.db` relative to project root) get resolved from, given `backend/` is a separate uv project with its own working directory?**
   - What we know: PLAN.md says the path is `db/finally.db` "relative to project root," and the container mounts `/app/db`; there is no existing env-var/config pattern for this in the codebase yet (only `MASSIVE_API_KEY` is read via `os.environ` in `factory.py`).
   - What's unclear: whether this phase should hardcode `Path(__file__).parent.parent.parent.parent / "db" / "finally.db"`-style path arithmetic from `backend/app/db/`, or accept the path as a constructor/factory parameter (consistent with the existing DI pattern) that Phase 2's app wiring supplies explicitly.
   - Recommendation: accept `db_path: Path` as an explicit parameter on `init_db()`, `get_connection()`, and `execute_trade()` (or a factory that closes over it) rather than hardcoding traversal — this makes the tests trivial (pass a `tmp_path` fixture) and defers the "what is the real path in production" decision to Phase 2/6 wiring, consistent with the "Claude's Discretion" module-layout guidance in CONTEXT.md.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | All backend code | ✓ | 3.13.3 (local) `[VERIFIED: python3 --version run this session]`; project requires `>=3.12` per `pyproject.toml` | — |
| SQLite engine (bundled with Python's `sqlite3`) | WAL mode, `busy_timeout`, `ON CONFLICT` upsert (needs ≥3.24) | ✓ | 3.49.1 `[VERIFIED: python3 -c "import sqlite3; print(sqlite3.sqlite_version)" run this session]` | — |
| `uv` | Dependency management, running tests | ✓ | 0.11.32 `[VERIFIED: uv --version run this session]` | — |
| `fastapi`, `pytest-asyncio` | lifespan pattern, async tests | ✓ (locked) | `fastapi==0.128.7`, `pytest-asyncio==1.3.0` `[VERIFIED: backend/uv.lock]` | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none — this phase has no new external dependencies.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ with pytest-asyncio 1.3.0 (`asyncio_mode = "auto"`) `[VERIFIED: backend/pyproject.toml [tool.pytest.ini_options] this session]` |
| Config file | `backend/pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) |
| Quick run command | `cd backend && uv run --extra dev pytest tests/db tests/portfolio -x` |
| Full suite command | `cd backend && uv run --extra dev pytest -v` (or `--cov=app` for coverage) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DB-01 | All six tables persist rows across a connection close/reopen cycle | integration | `uv run --extra dev pytest tests/db/test_init.py -x` | ❌ Wave 0 |
| DB-02 | `init_db()` is idempotent — calling twice does not duplicate the seeded `users_profile`/`watchlist` rows | integration | `uv run --extra dev pytest tests/db/test_init.py::test_init_is_idempotent -x` | ❌ Wave 0 |
| DB-03 | WAL mode + busy_timeout allow concurrent writers without "database is locked" errors | concurrency | `uv run --extra dev pytest tests/portfolio/test_concurrency.py -x` | ❌ Wave 0 |
| PORT-04 | Concurrent trades on a limited cash balance never overspend (atomicity) | concurrency | `uv run --extra dev pytest tests/portfolio/test_concurrency.py::test_concurrent_buys_do_not_overspend -x` | ❌ Wave 0 |
| TEST-01 | Fractional shares, exact-balance buy, full-position sell to zero, insufficient cash/shares rejection | unit | `uv run --extra dev pytest tests/portfolio/test_engine.py -x` | ❌ Wave 0 |
| TEST-01 (float-drift) | 1000-iteration buy/sell round trip does not drift the cash balance | regression | `uv run --extra dev pytest tests/portfolio/test_engine.py::test_no_float_drift_over_many_trades -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && uv run --extra dev pytest tests/db tests/portfolio -x`
- **Per wave merge:** `cd backend && uv run --extra dev pytest -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/db/__init__.py` — package marker (mirrors existing `tests/market/` pattern)
- [ ] `backend/tests/db/conftest.py` — `tmp_path`-based isolated DB fixture (each test gets its own `finally.db` under pytest's tmp dir, never touches the real `db/finally.db`)
- [ ] `backend/tests/db/test_connection.py` — asserts WAL mode + busy_timeout pragmas are actually set on a fresh connection
- [ ] `backend/tests/db/test_init.py` — covers DB-01, DB-02
- [ ] `backend/tests/portfolio/__init__.py` — package marker
- [ ] `backend/tests/portfolio/conftest.py` — seeded-DB + fake `PriceCache` fixtures for engine/valuation tests
- [ ] `backend/tests/portfolio/test_engine.py` — covers TEST-01 (buy/sell, fractional shares, exact-balance, insufficient cash/shares, full-position-sell-to-zero, float-drift regression)
- [ ] `backend/tests/portfolio/test_valuation.py` — covers unrealized P&L / % change / total value pure functions
- [ ] `backend/tests/portfolio/test_concurrency.py` — covers DB-03, PORT-04 via `asyncio.gather()` of concurrent `execute_trade()` calls
- [ ] Framework install: none — `pytest`, `pytest-asyncio` already installed via `uv sync --extra dev`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | Single-user, hardcoded `user_id="default"`, no auth in this milestone (documented Out of Scope in REQUIREMENTS.md) |
| V3 Session Management | no | No sessions — no login |
| V4 Access Control | no | Single-user; no authorization boundaries to enforce in this phase |
| V5 Input Validation | yes | All SQL uses parameterized queries (`?` placeholders) exclusively — never string-formatted/f-string SQL, which would be a SQL-injection vector even though input currently only comes from the LLM/internal callers, not directly from untrusted network input in this phase (routes are Phase 2) |
| V6 Cryptography | no | No secrets/crypto handled by the persistence layer itself |

### Known Threat Patterns for stdlib `sqlite3` + Decimal money math

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| SQL injection via string-interpolated ticker/user_id values | Tampering | Always use `?` parameterized queries (`conn.execute("... WHERE ticker = ?", (ticker,))`); never `f"... WHERE ticker = '{ticker}'"`. All examples in this document use parameterization. |
| Float-precision drift used to under/overstate cash or share balances over many trades | Tampering / Information Disclosure (of an incorrect balance) | `Decimal`-internal arithmetic (this phase's core design), converting to `float` only at the write/serialize boundary; float-drift regression test in Validation Architecture |
| TOCTOU (time-of-check-to-time-of-use) race on cash/share sufficiency check | Tampering | `BEGIN IMMEDIATE` transaction wrapping the entire check-then-write sequence (Pattern 2 above) — this is the primary security-relevant guarantee this phase delivers (PORT-04) |
| Uncommitted stale/committed database artifact leaking into version control (this session's Pitfall 2 finding) | Information Disclosure | Remove `db/finally.db` from git tracking and correct `.gitignore`; a committed SQLite file could accumulate real (if simulated) portfolio data across contributors' machines if left unaddressed |

## Sources

### Primary (HIGH confidence)
- Context7 `/python/cpython` — `sqlite3.connect()` signature (isolation_level, autocommit defaults), `Lib/dbm/sqlite3.py` WAL-mode pragma pattern
- Context7 `/websites/fastapi_tiangolo` — `lifespan` async context manager pattern, 0.93.0 release notes
- This session's direct filesystem/git inspection: `ls backend/db/` (absent), `git ls-files db/` (tracked), `cat .gitignore` (no match), `sqlite3 db/finally.db ".schema"` + row counts, `python3 -c "import sqlite3; print(sqlite3.sqlite_version)"`, `uv --version`, `backend/uv.lock` (fastapi/pytest-asyncio locked versions)
- `/Users/hendro/Documents/Projects/finally/planning/PLAN.md` §7 (Database schema, verbatim column specification), §4 (directory structure claims — contradicted by filesystem check), §9 (Decimal/float is implied by "no fees" simple math, not directly specified — this phase's Decimal design is CONTEXT.md's, not PLAN.md's)
- `backend/app/market/seed_prices.py` (verbatim ticker list, lines 4-15), `backend/app/market/cache.py` (verbatim `get_price()` signature, lines 54-57), `backend/app/market/massive_client.py` (`asyncio.to_thread` pattern)

### Secondary (MEDIUM confidence)
- WebSearch, cross-checked across multiple results: SQLite `BEGIN IMMEDIATE` vs `DEFERRED` concurrency behavior under WAL mode
- WebSearch, cross-checked across multiple results: `Decimal`/float/SQLite `REAL`/JSON conversion boundary best practices

### Tertiary (LOW confidence)
- None used as authoritative — all WebSearch findings above were cross-checked across ≥3 independent result snippets before being cited at MEDIUM confidence.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, all versions verified against `uv.lock`/local environment directly
- Architecture: HIGH — WAL/busy_timeout/lifespan patterns confirmed via Context7 (official docs); BEGIN IMMEDIATE guidance is MEDIUM (cross-checked community sources, not a direct sqlite.org quote)
- Pitfalls: HIGH — the two most impactful pitfalls (missing `backend/db/`, stale committed `db/finally.db`) were discovered and verified by direct filesystem/git inspection this session, not inferred from documentation

**Research date:** 2026-08-02
**Valid until:** 2026-09-01 (30 days — stdlib/FastAPI patterns here are stable; re-verify the `db/finally.db` git-tracking finding immediately before planning starts, since it could be fixed by another session in the interim)
