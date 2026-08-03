# Phase 2: Manual Trading - Research

**Researched:** 2026-08-03
**Domain:** Atomic financial transaction engine (FastAPI/SQLite backend) + live-derived portfolio state (Next.js/React frontend)
**Confidence:** HIGH

## Summary

Phase 2 adds exactly one new backend capability — a single, validated `execute_trade()` engine — plus its two read/write HTTP surfaces and the frontend that consumes them. Nothing about the domain is exotic: the codebase already contains the canonical solution to this phase's hardest problem (atomic check-then-act avoidance) in `backend/app/db/watchlist.py`'s `add_watchlist_ticker(..., max_size=...)`, proven race-free by an existing concurrency test. The trade engine is a structural copy of that pattern applied to `cash_balance` (buy) and `positions.quantity` (sell), with `Decimal` arithmetic inserted between the SQLite `REAL` boundary and the Python business logic.

The one genuine landmine this research surfaced is **not** in the SQL (that part is well-trodden ground in this repo) — it is in Pydantic response serialization. Pydantic v2 serializes `Decimal` fields to **JSON strings**, not JSON numbers, in `model_dump_json()`/`mode="json"` (and therefore in FastAPI `response_model` output, since FastAPI's `jsonable_encoder` calls `model_dump(mode="json", ...)` internally with no Decimal special-case of its own). If any Pydantic response model in this phase types a field as `Decimal`, the frontend receives `"152.34"` instead of `152.34` and every arithmetic consumer downstream (`current_price * quantity` in the header's live-value derivation) breaks silently on a type coercion or produces `NaN`. CONTEXT.md's locked decision — convert `Decimal` → `float` at the JSON-serialization boundary — is confirmed as the correct and necessary approach by this finding, not merely a style preference; the research below makes explicit *why* it is required, not optional.

**Primary recommendation:** Do all trade-engine arithmetic in `Decimal`, but declare every Pydantic request/response model field that reaches the wire as `float` (mirroring `AddTickerRequest`'s existing convention), and convert `Decimal → float(...)` explicitly at both the SQLite-write boundary and the response-model-construction boundary — never let a `Decimal` value flow directly into a Pydantic model field that will be JSON-serialized.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Trade validation & atomic mutation (`execute_trade()`) | API / Backend | Database / Storage | Business rule (sufficient cash/shares) must be enforced inside the same atomic SQL statement that performs the mutation — cannot be split across tiers without reintroducing the check-then-act race PORT-04 exists to prevent |
| Weighted-avg-cost recompute | API / Backend | — | Pure calculation on data already in hand inside the same DB transaction; no reason to push to client or a separate service |
| Position read / portfolio valuation (`GET /api/portfolio`) | API / Backend | Database / Storage | Source of truth for quantity/avg_cost/cash; backend is also where `PriceCache` (in-process, not exposed directly) lives, so joining position data with live price for a snapshot response is natively a backend job |
| Live total-value recompute (ticking every ~500ms with the price stream) | Browser / Client | — | Re-fetching `GET /api/portfolio` at SSE cadence (500ms) would hammer the backend for no reason — the frontend already holds live prices via `PriceStreamProvider`; multiplying held quantities/avg_cost (fetched at low frequency) by live price (already streamed) is a pure, cheap client-side derivation |
| Trade bar / positions table UI | Browser / Client | — | Standard presentation-tier form + table, no business logic duplicated client-side (server is authoritative on every trade) |

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Money math:** Use Python `Decimal` for all arithmetic inside `execute_trade()` — cash debit/credit, weighted-average cost recompute, proceeds calculation. Construct `Decimal` from `str(value)`, never from a raw float directly. Convert to `float` only at the two boundaries: writing to the `REAL` columns (`cash_balance`, `quantity`, `avg_cost`, `price`), and JSON-serializing for the API response. No fixed rounding/quantization scheme beyond full `Decimal` precision.
- **Atomicity pattern:** Follow `backend/app/db/watchlist.py`'s `add_watchlist_ticker(..., max_size=...)` idiom exactly: a single atomic `UPDATE ... WHERE <sufficiency condition>` statement checked via `cursor.rowcount`, never a separate `SELECT` followed by a conditional `UPDATE`.
  - Buy: `UPDATE users_profile SET cash_balance = cash_balance - ? WHERE id = ? AND cash_balance >= ?`; `rowcount == 0` → reject as insufficient cash.
  - Sell: the equivalent atomic guard against `positions.quantity`.
- **Single entry point:** `execute_trade(ticker, side, quantity, user_id=DEFAULT_USER_ID)` is the ONLY way any code (this phase's trade route, Phase 4's AI copilot later) mutates cash, positions, or trades. Reads current price from `app.state.price_cache` (same DI pattern as `app.state.market_source`); missing cached price → reject the trade.
- **Position upsert on buy:** `new_avg_cost = (old_qty * old_avg_cost + trade_qty * price) / (old_qty + trade_qty)`, all in `Decimal`. First buy inserts; subsequent buys update via the `(user_id, ticker)` UNIQUE constraint.
- **Position handling on sell:** Full-position sell (selling exactly `quantity`) deletes the `positions` row rather than leaving `quantity=0`. Partial sell reduces `quantity` in place; `avg_cost` unchanged by a sell.
- **Trade log:** Every successful buy/sell appends one row to `trades` in the same atomic unit of work as the cash/position mutation.
- **Rejection is silent-safe:** A rejected trade leaves cash, positions, and trade history byte-identical — verify via fresh-connection assertions, not the in-process return value.
- `POST /api/portfolio/trade` — body `{ticker, side: "buy"|"sell", quantity}`, calls `execute_trade()`, returns the updated position (or its absence, if the sell emptied it) plus new cash balance. No confirmation step, no fees.
- `GET /api/portfolio` — returns cash balance, computed total portfolio value (cash + sum of position market values at current cached prices), and every position with quantity, avg_cost, current_price, unrealized P&L, and % change. Positions with no current cached price surface a null/absent current price rather than crashing.
- Ticker validation on the trade route reuses `normalize_ticker`/`TICKER_PATTERN` from Phase 1's watchlist route — no second validation path.
- **Trade bar:** ticker input + quantity input + Buy button + Sell button. Instant fill, no confirmation dialog. Disabled/spinner state while in flight. On rejection, show the server's rejection reason inline.
- **Positions table:** ticker, quantity, avg cost, current price, unrealized P&L, % change — one row per open position, updating live as `GET /api/portfolio` values change. Introduce a shared portfolio-state fetch (poll or refetch after a trade) so trade bar, positions table, and header read one consistent portfolio state. No portfolio SSE stream this phase; refetch-on-trade-completion plus a light polling interval is sufficient.
- **Header (UI-03):** total portfolio value, cash balance, connection-status dot (dot already exists). Total portfolio value must update as prices tick, not just after a trade — combine the existing price stream with fetched position quantities/avg costs to recompute value client-side on every tick, rather than re-fetching `GET /api/portfolio` on every SSE frame.
- **Testing (TEST-01):** Backend unit tests must cover fractional-share buys/sells, exact-balance buy, full-position sell (row deleted), insufficient-cash rejection, insufficient-shares rejection, and a concurrency proof modeled on `test_concurrent_adds_never_exceed_cap`.

### Claude's Discretion

- Exact module/file layout for the new trade engine and portfolio read-side (e.g. `backend/app/portfolio/` mirroring `backend/app/db/`+`backend/app/routes/`, or folding into `backend/app/db/`).
- Exact polling interval (if any) for refreshing portfolio state beyond trade-completion refetch.
- Whether `execute_trade()` is a free function or a small class.

### Deferred Ideas (OUT OF SCOPE)

- Portfolio snapshots (30s interval + post-trade) and portfolio value history — Phase 3 (PORT-06/07).
- Heatmap and P&L chart — Phase 3.
- AI-initiated trades — Phase 4 (must call this phase's `execute_trade()` unchanged, per CHAT-03).
- Docker packaging — Phase 5.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PORT-01 | User can view current positions with ticker, quantity, avg cost, current price, unrealized P&L, and % change | `GET /api/portfolio` pattern below; null-current-price handling documented (Common Pitfalls, Code Examples) |
| PORT-02 | User can execute a market buy order (instant fill, no fees, no confirmation) | Atomic buy SQL pattern (Code Examples); Decimal boundary discipline (Common Pitfalls) |
| PORT-03 | User can execute a market sell order (instant fill, no fees, no confirmation) | Atomic sell SQL pattern + full-position-delete handling (Code Examples) |
| PORT-04 | Trade execution validates sufficient cash/shares atomically, preventing check-then-deduct races | `UPDATE ... WHERE ... AND rowcount` pattern verified against `add_watchlist_ticker` precedent and cross-checked sqlite3 `rowcount` semantics (Sources) |
| PORT-05 | User can view total portfolio value and cash balance, updating live | Client-side derivation pattern from `PriceStreamProvider` + polled positions (Architecture Patterns, Code Examples) |
| UI-03 | Header shows live portfolio total value, cash balance, connection-status dot | Header architecture pattern extending `AppHeader.tsx`/`PriceStreamProvider.tsx` (Code Examples) |
| UI-05 | Trade bar allows entering ticker, quantity, buy/sell with instant execution | Trade bar pattern mirroring `AddTickerForm.tsx`'s in-flight/error/empty-state discipline (Architecture Patterns) |
| TEST-01 | Backend unit tests cover trade execution logic, P&L calculations, edge cases | Test Framework / Phase Requirements → Test Map (Validation Architecture) |

## Project Constraints (from CLAUDE.md)

- **Root `CLAUDE.md`:** All work must follow `planning/PLAN.md` — market orders only (no fees, no confirmation dialogs), single SQLite file, single FastAPI process serving both API and static frontend, Decimal precision is implied by "no fixed rounding scheme" already locked in CONTEXT.md.
- **`backend/CLAUDE.md`:** Use `uv sync --extra dev` for backend deps; market data access must go through `app.market`'s `PriceCache`/`PriceUpdate` — this phase must read prices via `app.state.price_cache.get_price(ticker)` (returns `float | None`), never construct a second price source. Run tests via `uv run --extra dev pytest -v`; lint via `uv run --extra dev ruff check app/ tests/`.
- **`frontend/AGENTS.md`:** "This is NOT the Next.js you know" — Next 16.2.12 / React 19.2.4 are in use; read `node_modules/next/dist/docs/` before assuming any API from training data (e.g. App Router conventions may differ). No new frontend package is needed this phase (verified below), so this mainly constrains any App Router / client-component idioms the planner writes into the trade bar and positions table.

## Standard Stack

### Core

No new libraries this phase. Every capability is implementable with what is already a dependency:

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | 0.128.7 [VERIFIED: backend/uv.lock] | Trade route, response models | Already the project's only web framework |
| `pydantic` | 2.12.5 [VERIFIED: backend/uv.lock] | Request/response validation | Already in use (`AddTickerRequest`, `WatchlistResponse`) |
| `decimal` (stdlib) | Python 3.12 stdlib | Trade-engine arithmetic | Locked decision in CONTEXT.md; no third-party money library needed at this precision/complexity |
| `sqlite3` (stdlib) | Python 3.12 stdlib | Atomic UPDATE/INSERT with `rowcount` | Already the project's only DB driver, via `backend/app/db/connection.py` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `uuid` (stdlib) | — | New `trades`/`positions` row IDs | Same pattern as `watchlist.id` (`str(uuid.uuid4())`) |
| `lucide-react` | ^1.28.0 [VERIFIED: frontend/package.json] | Loading spinner icon in trade bar | Already used by `AddTickerForm.tsx` (`Loader2`) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `decimal.Decimal` | `pydantic.condecimal` / native `Decimal` Pydantic field end-to-end | Rejected: would require the `PlainSerializer(float, when_used='json')` override on every wire-facing field to avoid the string-serialization pitfall documented below — more moving parts than converting to `float` explicitly at the two boundaries CONTEXT.md already locked |
| Custom SSE portfolio stream | New `/api/stream/portfolio` SSE endpoint | Rejected by CONTEXT.md explicitly — "no portfolio SSE stream in this phase's scope"; client-side derivation from the existing price stream is prescribed instead |

**Installation:** None required — no new dependencies for this phase.

**Version verification:**
```
$ grep -A2 '^name = "pydantic"' backend/uv.lock   → pydantic 2.12.5
$ grep -A2 '^name = "fastapi"' backend/uv.lock    → fastapi 0.128.7
```
Both confirmed against the committed lockfile in this session — no registry lookup needed since these are pinned, already-installed dependencies, not new additions.

## Package Legitimacy Audit

**Not applicable.** This phase introduces zero new external packages (backend or frontend) — everything needed (`decimal`, `uuid`, `sqlite3`, existing `fastapi`/`pydantic`/`lucide-react`) is already a dependency of this codebase, verified directly against `backend/pyproject.toml`, `backend/uv.lock`, and `frontend/package.json` read this session. The Package Legitimacy Gate protocol is skipped per its own applicability condition ("whenever this phase installs external packages").

**Packages removed due to [SLOP] verdict:** none (no packages evaluated — none proposed)
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────── Browser ───────────────────────────┐
│                                                                  │
│  PriceStreamProvider (existing, unchanged)                     │
│    EventSource → GET /api/stream/prices  ──────┐               │
│         │ prices: PriceMap (ticker→PriceUpdate)  │               │
│         ▼                                        │               │
│  ┌──────────────┐   ┌──────────────────┐         │               │
│  │  Trade Bar    │   │ Positions/Portfolio     │  live prices    │
│  │  (form)       │──▶│  Context (NEW)          │◀────────────────┘
│  │ ticker, qty,  │   │  - polls/refetches       │
│  │ buy/sell      │   │    GET /api/portfolio    │
│  └──────┬───────┘   │    (cash, positions,     │
│         │ POST      │     avg_cost — source     │
│         │ /api/     │     of truth for qty)     │
│         │ portfolio/│  - derives LIVE value:    │
│         │ trade     │    cash + Σ(qty×price)    │
│         │           │    using streamed price,  │
│         ▼           │    not a refetch          │
│  ┌──────────────┐   └───────┬──────────┬───────┘
│  │ AppHeader     │◀──────────┘          │
│  │ total value,  │                      ▼
│  │ cash balance  │             ┌──────────────────┐
│  └──────────────┘              │ Positions Table   │
│                                  │ (per-row P&L,     │
│                                  │  live price)      │
│                                  └──────────────────┘
└──────────────────────────────────────────────────────────────────┘
                          │ HTTP (same-origin /api/*)
                          ▼
┌─────────────────────────── FastAPI ────────────────────────────┐
│                                                                  │
│  POST /api/portfolio/trade          GET /api/portfolio          │
│         │                                    │                  │
│         ▼                                    ▼                  │
│  ┌───────────────────────────────────────────────────┐         │
│  │            execute_trade() / read_portfolio()       │         │
│  │  - normalize_ticker() (reused from watchlist route)  │         │
│  │  - app.state.price_cache.get_price(ticker)           │         │
│  │  - Decimal arithmetic (weighted avg cost, proceeds)  │         │
│  │  - atomic UPDATE...WHERE + rowcount (buy/sell guard) │         │
│  │  - position upsert / full-sell delete                │         │
│  │  - trades row insert (same DB transaction)            │         │
│  └───────────────────────┬───────────────────────────┘         │
│                            │ run_db(fn) → asyncio.to_thread      │
│                            ▼                                     │
│              SQLite (WAL, busy_timeout=5000)                    │
│         users_profile │ positions │ trades                       │
└────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

Given Claude's discretion is explicit on layout, the pattern that most closely mirrors the existing `backend/app/db/` + `backend/app/routes/` split (and keeps `execute_trade()` next to the SQL it wraps, exactly like `add_watchlist_ticker`) is:

```
backend/app/
├── db/
│   ├── watchlist.py        # unchanged
│   └── portfolio.py        # NEW — execute_trade(), get_portfolio(), Decimal boundary
├── routes/
│   ├── watchlist.py        # unchanged
│   └── portfolio.py        # NEW — POST /api/portfolio/trade, GET /api/portfolio
backend/tests/
├── db/
│   └── test_portfolio.py   # NEW — mirrors test_watchlist.py's temp_db + concurrency style
└── routes/
    └── test_portfolio.py   # NEW — route-level status codes/shapes, mirrors existing route tests

frontend/
├── lib/
│   ├── api.ts               # extend: fetchPortfolio(), executeTrade()
│   └── types.ts             # extend: Position, PortfolioSnapshot types
├── components/
│   ├── PortfolioProvider.tsx  # NEW — shared context: polls GET /api/portfolio, derives live value from price stream
│   ├── TradeBar.tsx           # NEW
│   └── PositionsTable.tsx     # NEW
```

This keeps `backend/app/db/portfolio.py` as the single place `execute_trade()` lives — this is what makes it trivially reusable, unchanged, by Phase 4's chat route (CHAT-03), the same way `add_watchlist_ticker` is reusable by both the watchlist route and (potentially) a future chat-driven watchlist mutation.

### Pattern 1: Atomic buy — cash debit guarded by `rowcount`

**What:** A single `UPDATE users_profile SET cash_balance = cash_balance - ? WHERE id = ? AND cash_balance >= ?` statement. If `cursor.rowcount == 0`, no row matched the `cash_balance >= ?` guard, meaning insufficient cash — reject without ever having read-then-compared a balance in Python.

**When to use:** Every buy, unconditionally — this is the *only* path that debits `cash_balance`.

**Verified against:** `add_watchlist_ticker`'s `INSERT ... SELECT ... WHERE (SELECT COUNT(*) ...) < max_size` (`backend/app/db/watchlist.py:93-100` — quoted below) and confirmed by `test_concurrent_adds_never_exceed_cap` (`backend/tests/db/test_watchlist.py:20-38`), which proves 20 concurrent callers against the same atomic-guarded statement never overrun the guard. [VERIFIED: backend/app/db/watchlist.py:93-104]

```python
# backend/app/db/watchlist.py:93-104 (verbatim, the reference pattern)
cur = conn.execute(
    """
    INSERT INTO watchlist (id, user_id, ticker, added_at)
    SELECT ?, ?, ?, ?
    WHERE (SELECT COUNT(*) FROM watchlist WHERE user_id = ?) < ?
    """,
    (row_id, user_id, ticker, added_at, user_id, max_size),
)
if cur.rowcount == 0:
    raise WatchlistCapReachedError(
        f"watchlist for {user_id!r} is already at max_size={max_size}"
    )
```

### Pattern 2: Decimal boundary — never `Decimal(a_float)` directly

**What:** Every value entering `Decimal` arithmetic that originated as a `float` (SQLite `REAL` column read, `PriceCache.get_price()` return value, a Pydantic request field typed `float`) must be converted `Decimal(str(value))`, never `Decimal(value)`. `Decimal(0.1)` imports IEEE-754 binary imprecision (`Decimal('0.1000000000000000055511151231257827021181583404541015625')`); `Decimal(str(0.1))` does not (`Decimal('0.1')`).

**When to use:** At the top of `execute_trade()`, immediately after reading `cash_balance`/`quantity`/`avg_cost` from a DB row and `price` from `PriceCache.get_price()` — before any arithmetic touches them.

```python
from decimal import Decimal

price = price_cache.get_price(ticker)  # float | None, per app/market/cache.py:56-58
if price is None:
    raise TradeRejectedError(f"No live price available for {ticker}")
price_dec = Decimal(str(price))
quantity_dec = Decimal(str(quantity))  # quantity arrives as a float from the Pydantic request field
cost = price_dec * quantity_dec
```

### Pattern 3: Decimal → wire boundary — never a bare `Decimal` Pydantic field

**What:** Pydantic v2 serializes `Decimal` to a JSON **string** in `mode="json"` output by default (confirmed via Context7 official Pydantic docs — see Sources). FastAPI's `response_model` serialization path calls `obj.model_dump(mode="json", ...)` internally (via `jsonable_encoder`), so this string-not-number behavior applies to every FastAPI response, not just direct `model_dump_json()` calls. Any response model field intended to reach the frontend as a JSON number (`cash_balance`, `current_price`, `unrealized_pnl`, etc.) **must be typed `float`**, with the conversion `float(decimal_value)` happening in the route/engine layer before the Pydantic model is constructed — mirroring exactly what CONTEXT.md already locked ("Convert to float only at the two boundaries... JSON-serializing for the API response").

```python
# WRONG — response_model field typed Decimal serializes as a JSON string
class PositionResponse(BaseModel):
    quantity: Decimal   # → {"quantity": "10.5"} on the wire, not {"quantity": 10.5}

# RIGHT — convert before constructing the model
class PositionResponse(BaseModel):
    quantity: float
    avg_cost: float
    current_price: float | None
    unrealized_pnl: float | None
    change_percent: float | None

def _to_response(position_dec: dict[str, Decimal]) -> PositionResponse:
    return PositionResponse(
        quantity=float(position_dec["quantity"]),
        avg_cost=float(position_dec["avg_cost"]),
        current_price=float(position_dec["current_price"]) if position_dec["current_price"] is not None else None,
        unrealized_pnl=float(position_dec["pnl"]) if position_dec["pnl"] is not None else None,
        change_percent=float(position_dec["change_pct"]) if position_dec["change_pct"] is not None else None,
    )
```

### Pattern 4: Client-side live portfolio value derivation (no polling at SSE cadence)

**What:** Fetch `positions` (quantity, avg_cost) and `cash_balance` from `GET /api/portfolio` at low frequency (light poll interval, planner's discretion — every 5-10s is a reasonable default since only new trades or snapshots change these, and this phase has no snapshot writer yet) and after every trade completes. On every SSE price tick (already flowing through `usePriceStreamContext()`), recompute `totalValue = cashBalance + Σ(position.quantity × prices[position.ticker]?.price ?? position.avg_cost)` entirely client-side — no additional network call per tick.

**When to use:** `AppHeader` (total value + cash) and `PositionsTable` (per-row current price / unrealized P&L / % change) both need this; introduce one shared context (`PortfolioProvider`, siblings to `PriceStreamProvider`) so both consume one fetch, following the same "shared context so nobody double-opens a resource" rationale already documented in `PriceStreamProvider.tsx:9-14`. [VERIFIED: frontend/components/PriceStreamProvider.tsx:9-14] — quoted: `"Opens the single shared \`EventSource\` for the whole page and publishes it through context. This is the reason exactly one connection exists per page load: the header and the watchlist grid are siblings, so neither can own the stream without the other opening a second one."`

```typescript
// frontend/components/PortfolioProvider.tsx (new, pattern-matches PriceStreamProvider.tsx)
"use client";
import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import { fetchPortfolio } from "@/lib/api";
import { usePriceStreamContext } from "@/components/PriceStreamProvider";
import type { Position } from "@/lib/types";

interface PortfolioState {
  cashBalance: number;
  positions: Position[];       // quantity, avg_cost, ticker — from backend, low-frequency
  totalValue: number;          // derived client-side every render, using live prices
  refetch: () => Promise<void>;
}

const PortfolioContext = createContext<PortfolioState | null>(null);

export function PortfolioProvider({ children }: { children: ReactNode }) {
  const { prices } = usePriceStreamContext();  // ticks every ~500ms, from the existing stream
  const [cashBalance, setCashBalance] = useState(0);
  const [positions, setPositions] = useState<Position[]>([]);

  const refetch = useCallback(async () => {
    const data = await fetchPortfolio();
    setCashBalance(data.cash_balance);
    setPositions(data.positions);
  }, []);

  useEffect(() => {
    refetch();
    const interval = setInterval(refetch, 8000); // light poll; planner's discretion on exact value
    return () => clearInterval(interval);
  }, [refetch]);

  // Recomputed on every render — including every price-stream tick, since
  // `prices` (from context) changes identity on each SSE frame — with no
  // additional network call. This is the mechanism that satisfies "total
  // portfolio value must update as prices tick" (CONTEXT.md, UI-03) without
  // hammering GET /api/portfolio at 500ms cadence.
  const totalValue =
    cashBalance +
    positions.reduce((sum, p) => sum + p.quantity * (prices[p.ticker]?.price ?? p.avg_cost), 0);

  return (
    <PortfolioContext.Provider value={{ cashBalance, positions, totalValue, refetch }}>
      {children}
    </PortfolioContext.Provider>
  );
}

export function usePortfolioContext(): PortfolioState {
  const ctx = useContext(PortfolioContext);
  if (ctx === null) throw new Error("usePortfolioContext must be used within a PortfolioProvider");
  return ctx;
}
```

### Anti-Patterns to Avoid

- **`SELECT cash_balance ... ; if cash_balance >= cost: UPDATE ...`** — this is the exact check-then-act race PORT-04 forbids. Two concurrent trades can both pass the `SELECT` check before either commits its `UPDATE`, both proceeding to debit more cash than exists. The atomic `UPDATE ... WHERE cash_balance >= ?` pattern is not a style preference here — it is the only correct implementation.
- **A `Decimal` Pydantic response field left unconverted** — passes local testing (Python-side `model_dump()` keeps it as `Decimal`) but fails in production JSON output as a string, likely surfacing as `NaN` client-side or a silent string-concatenation bug in the total-value calculation rather than a loud error.
- **Re-fetching `GET /api/portfolio` on every SSE price frame** — defeats the purpose of the price stream being push-based and would issue ~2 requests/second/client for no correctness benefit, since only `positions`/`cash_balance` (which change on trade, not on price tick) need re-fetching.
- **Leaving a `quantity=0` position row after a full sell** — explicitly forbidden by CONTEXT.md; would render as a phantom position in this phase's own positions table (and Phase 3's heatmap).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Check-then-act race prevention | A manual lock, `threading.Lock`, or app-level mutex around trade execution | The atomic `UPDATE ... WHERE <guard> ` + `cursor.rowcount` pattern already proven in this codebase | SQLite's own writer-lock serializes all writes to a single connection anyway (WAL mode); a second, redundant app-level lock adds complexity without adding correctness, and doesn't compose with future multi-process deployment the way a DB-enforced atomic statement does |
| Money precision | Hand-rolled fixed-point integer cents, or trusting raw `float` for cash math | Python's stdlib `decimal.Decimal`, per CONTEXT.md's locked decision | `Decimal` is exact for base-10 arithmetic (what money/quantities need) and is already the codebase's chosen tool — introducing a competing precision scheme (integer cents) would fight `avg_cost`'s existing `REAL` column type and CONTEXT.md's explicit "no fixed rounding/quantization scheme" |
| Portfolio value polling / live update | A custom debounced polling scheduler, a second SSE stream, or WebSocket for portfolio value | Client-side derivation from the existing `PriceStreamProvider` context (Pattern 4 above) | CONTEXT.md explicitly rules out a new SSE stream for this phase; multiplying already-streamed prices by low-frequency-fetched quantities is strictly simpler and correctness-equivalent |

**Key insight:** Everything genuinely hard about this phase (the atomicity guarantee) was already solved once in this codebase during Phase 1's watchlist work — the risk isn't in inventing a new mechanism, it's in *not* recognizing the existing one applies, and instead reaching for a heavier tool (locks, a second read-then-write) that reintroduces the exact race the codebase already learned to avoid.

## Common Pitfalls

### Pitfall 1: Decimal fields silently serialize as strings, not numbers

**What goes wrong:** A Pydantic response model field typed `Decimal` returns `"152.34"` (a JSON string) to the frontend instead of `152.34` (a JSON number). The frontend's `current_price * quantity` arithmetic either throws, coerces oddly, or silently produces `NaN` depending on which side of the multiplication the string lands on.

**Why it happens:** Pydantic v2's `model_dump(mode="json")` — which both `model_dump_json()` and FastAPI's internal `jsonable_encoder` call — serializes `Decimal` to `str` by default; there is no automatic float coercion. [CITED: github.com/pydantic/pydantic/blob/main/docs/api/standard_library_types.md — "In JSON mode, Decimal instances are serialized as strings by default, but this behavior can be overridden using a serializer."]

**How to avoid:** Type every wire-facing Pydantic field `float`, and convert `Decimal → float` explicitly in the route/engine layer before constructing the response model (Pattern 3 above). This is exactly what CONTEXT.md's boundary rule already prescribes — this research explains *why* skipping it breaks, not just that it should be followed.

**Warning signs:** A frontend value renders as `"152.34"` with visible quotes in a debug log, or a computed total (`cash + Σ qty×price`) becomes `NaN` or a concatenated string like `"10000152.34"`.

### Pitfall 2: Constructing `Decimal` directly from a `float`

**What goes wrong:** `Decimal(0.1)` produces `Decimal('0.1000000000000000055511151231257827021181583404541015625')` — the binary float's exact (imprecise) value, not the decimal value the programmer intended. Downstream weighted-avg-cost or proceeds calculations accumulate this noise.

**Why it happens:** `float` itself already lost precision converting from the original decimal literal (e.g., `0.1` from JSON); `Decimal(float_value)` faithfully reproduces that lossy binary representation rather than correcting it.

**How to avoid:** Always route through `str()` first: `Decimal(str(value))`. This is CONTEXT.md's locked rule (Pattern 2 above) — the pitfall here is a planner or executor forgetting to apply it consistently at *every* point a float enters Decimal arithmetic (price from `PriceCache`, quantity from the request, `cash_balance`/`avg_cost` read back from SQLite `REAL` columns).

**Warning signs:** A weighted-average-cost test with exact expected decimal values (e.g., `10 @ $100.00` then `5 @ $110.00` → expected avg `$103.33...`) fails by a vanishingly small epsilon rather than being exactly wrong.

### Pitfall 3: `rowcount` misuse with `UPDATE ... RETURNING`

**What goes wrong:** If a future refactor adds `RETURNING` to the atomic UPDATE (to fetch the new balance in one round-trip instead of a follow-up `SELECT`), `cursor.rowcount` can become unreliable under specific edge cases (a table dropped and recreated within the same connection's lifetime).

**Why it happens:** Documented CPython `sqlite3` module edge case (cpython issues #93421, #101117) specifically involving `UPDATE...RETURNING` combined with table drop/recreate — not applicable to this codebase's actual pattern (plain `UPDATE ... WHERE`, no `RETURNING`, connections are never long-lived enough to see a drop/recreate per `backend/app/db/connection.py`'s per-call `connect()`/`close()` design).

**How to avoid:** Keep using the plain `UPDATE ... WHERE <guard>` + `cursor.rowcount` pattern this phase's design already calls for; do not add `RETURNING` to "optimize" a round-trip without re-verifying rowcount semantics for that specific combination.

**Warning signs:** N/A for this phase's planned implementation — documented here as a boundary to avoid crossing, not a bug currently present.

### Pitfall 4: Trade route double-validates instead of trusting `execute_trade()`

**What goes wrong:** The route layer re-implements "is there enough cash" as a Python `if` check before calling `execute_trade()`, in addition to the atomic guard inside `execute_trade()` itself — reintroducing a (now redundant, and misleadingly reassuring) check-then-act race at the route layer, since the route's own check reads a value that can be stale by the time `execute_trade()`'s atomic statement runs.

**Why it happens:** Feels natural to "fail fast" with a friendly error before hitting the DB — but a route-layer check based on a plain `GET`/`SELECT` cannot be atomic with the mutation, so it adds a false sense of safety, not real safety.

**How to avoid:** The route layer should call `execute_trade()` unconditionally and interpret its result/exception (e.g., a raised `InsufficientCashError` / `InsufficientSharesError` from the `rowcount == 0` branch) as the *only* source of rejection truth — exactly mirroring how the watchlist route trusts `add_watchlist_ticker`'s `WatchlistCapReachedError` rather than pre-checking `count_watchlist()` itself (`backend/app/routes/watchlist.py:76-79` explicitly documents this reasoning). [VERIFIED: backend/app/routes/watchlist.py:76-79] — quoted: `"The size cap and the duplicate check are both enforced inside the same atomic INSERT as add_watchlist_ticker's own statement (WR-01) — a separate count_watchlist() read-then-insert here would be a check-then-act race between concurrent POSTs."`

**Warning signs:** A test written against two near-simultaneous requests (the concurrency proof TEST-01 requires) intermittently allows a trade that should have been rejected, or vice-versa.

## Code Examples

### Atomic buy — full pattern including position upsert and trade log

```python
# Source: pattern derived from backend/app/db/watchlist.py:85-123 (verified this session),
# applying CONTEXT.md's locked weighted-avg-cost formula and Decimal boundary rule.
from __future__ import annotations
from decimal import Decimal
import sqlite3
import uuid
from datetime import datetime, timezone

from .connection import DEFAULT_USER_ID, run_db

class InsufficientCashError(Exception):
    """Raised when a buy's atomic cash guard blocks the UPDATE (rowcount == 0)."""

async def _execute_buy(
    ticker: str, quantity: Decimal, price: Decimal, user_id: str = DEFAULT_USER_ID
) -> dict:
    cost = quantity * price  # Decimal * Decimal, full precision
    now = datetime.now(timezone.utc).isoformat()
    trade_id = str(uuid.uuid4())

    def _txn(conn: sqlite3.Connection) -> dict:
        # 1. Atomic cash guard — the only place cash_balance is debited.
        cur = conn.execute(
            "UPDATE users_profile SET cash_balance = cash_balance - ? "
            "WHERE id = ? AND cash_balance >= ?",
            (float(cost), user_id, float(cost)),
        )
        if cur.rowcount == 0:
            raise InsufficientCashError(f"Insufficient cash to buy {quantity} {ticker}")

        # 2. Position upsert — weighted-average-cost recompute in Decimal.
        existing = conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
            (user_id, ticker),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, ticker, float(quantity), float(price), now),
            )
        else:
            old_qty = Decimal(str(existing["quantity"]))
            old_avg = Decimal(str(existing["avg_cost"]))
            new_qty = old_qty + quantity
            new_avg = (old_qty * old_avg + quantity * price) / new_qty
            conn.execute(
                "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? "
                "WHERE user_id = ? AND ticker = ?",
                (float(new_qty), float(new_avg), now, user_id, ticker),
            )

        # 3. Trade log — same atomic unit of work (same conn, committed together by run_db).
        conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES (?, ?, ?, 'buy', ?, ?, ?)",
            (trade_id, user_id, ticker, float(quantity), float(price), now),
        )
        return {"ticker": ticker, "trade_id": trade_id}

    return await run_db(_txn)
```

### Atomic sell — full-position delete vs. partial reduce

```python
# Source: pattern derived from backend/app/db/watchlist.py's atomic-guard idiom,
# applying CONTEXT.md's locked "full sell deletes the row" rule.
class InsufficientSharesError(Exception):
    """Raised when a sell's atomic quantity guard blocks the UPDATE (rowcount == 0)."""

def _txn(conn: sqlite3.Connection) -> dict:
    # Atomic share-quantity guard — the only place positions.quantity is debited.
    cur = conn.execute(
        "UPDATE positions SET quantity = quantity - ? "
        "WHERE user_id = ? AND ticker = ? AND quantity >= ?",
        (float(quantity), user_id, ticker, float(quantity)),
    )
    if cur.rowcount == 0:
        raise InsufficientSharesError(f"Insufficient shares to sell {quantity} {ticker}")

    # Full-position sell: delete rather than leave quantity == 0 (CONTEXT.md decision).
    # A tiny Decimal epsilon check would be over-engineering here since `quantity`
    # was validated to be <= the held amount by the UPDATE guard above — an exact
    # zero-after-subtraction check on the Decimal value (not the REAL column,
    # which already lost precision) is the correct comparison.
    remaining = existing_qty_decimal - quantity  # existing_qty_decimal fetched before the UPDATE
    if remaining == Decimal("0"):
        conn.execute(
            "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        )

    proceeds = quantity * price
    conn.execute(
        "UPDATE users_profile SET cash_balance = cash_balance + ? WHERE id = ?",
        (float(proceeds), user_id),
    )
    # ... trade log insert, same as the buy path, side='sell'
```

### `GET /api/portfolio` — null current price handling

```python
# Pattern extends the existing app.state.price_cache DI, per backend/app/main.py:27-63
# and backend/app/market/cache.py's PriceCache.get_price(ticker) -> float | None (:56-58).
from pydantic import BaseModel

class PositionOut(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None       # None if PriceCache has no entry (ticker removed from watchlist)
    unrealized_pnl: float | None      # None when current_price is None — cannot compute
    change_percent: float | None

class PortfolioResponse(BaseModel):
    cash_balance: float
    total_value: float                # cash + sum(qty * current_price, treating missing price as avg_cost)
    positions: list[PositionOut]

@router.get("/api/portfolio", response_model=PortfolioResponse)
async def get_portfolio(request: Request) -> PortfolioResponse:
    cache = request.app.state.price_cache
    rows = await list_positions()  # raw DB rows: ticker, quantity, avg_cost
    positions_out = []
    total = Decimal(str((await get_cash_balance())))
    for row in rows:
        qty = Decimal(str(row["quantity"]))
        avg = Decimal(str(row["avg_cost"]))
        price = cache.get_price(row["ticker"])  # float | None
        if price is None:
            positions_out.append(PositionOut(
                ticker=row["ticker"], quantity=float(qty), avg_cost=float(avg),
                current_price=None, unrealized_pnl=None, change_percent=None,
            ))
            total += qty * avg  # fall back to cost basis when no live price, so total_value stays defined
            continue
        price_dec = Decimal(str(price))
        pnl = (price_dec - avg) * qty
        change_pct = ((price_dec - avg) / avg * 100) if avg != 0 else Decimal("0")
        positions_out.append(PositionOut(
            ticker=row["ticker"], quantity=float(qty), avg_cost=float(avg),
            current_price=float(price_dec), unrealized_pnl=float(pnl),
            change_percent=float(change_pct),
        ))
        total += qty * price_dec
    return PortfolioResponse(
        cash_balance=float(Decimal(str((await get_cash_balance())))),
        total_value=float(total),
        positions=positions_out,
    )
```

### Trade route — request/response shape mirroring `AddTickerRequest`

```python
# Source: pattern verified against backend/app/routes/watchlist.py:33-35 (AddTickerRequest)
# and :46-55 (normalize_ticker), both read this session.
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=10)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)

class TradeResponse(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    cash_balance: float
    position: PositionOut | None   # None if a full sell emptied the position

@router.post("/api/portfolio/trade", response_model=TradeResponse)
async def trade(body: TradeRequest, request: Request) -> TradeResponse:
    ticker = normalize_ticker(body.ticker)  # reused from app.routes.watchlist, not re-implemented
    cache = request.app.state.price_cache
    price = cache.get_price(ticker)
    if price is None:
        raise HTTPException(status_code=400, detail=f"No live price available for {ticker}")
    try:
        result = await execute_trade(ticker, body.side, body.quantity, price=price)
    except InsufficientCashError:
        raise HTTPException(status_code=400, detail=f"Insufficient cash to buy {ticker}") from None
    except InsufficientSharesError:
        raise HTTPException(status_code=400, detail=f"Insufficient shares to sell {ticker}") from None
    return TradeResponse(**result)
```

## State of the Art

No meaningful "old approach vs. new approach" axis applies here — this is a from-scratch feature in an actively-developed codebase, not a migration off a deprecated pattern. The one relevant currency check: Pydantic v2 (2.12.5, confirmed installed) has been the stable major version since mid-2023; its `Decimal`-as-JSON-string default behavior (documented above) has been stable across the v2 line and is not a recent change or something the planner needs to account for version-drift on.

**Deprecated/outdated:** None identified as relevant to this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A light poll interval (~8s) for `GET /api/portfolio` refresh, in addition to trade-completion refetch, is sufficient UX for PORT-05's "updating live" requirement, given total-value recompute itself is truly live (every SSE tick) and only quantity/avg_cost/cash need the slower poll | Architecture Patterns (Pattern 4) | Low — explicitly left to Claude's discretion by CONTEXT.md; if 8s feels sluggish for detecting e.g. a trade made in another tab, tightening the interval is a one-line change with no architectural impact |
| A2 | `backend/app/portfolio/` vs. folding into `backend/app/db/`+`backend/app/routes/` — this research recommends the latter (mirroring existing structure exactly) | Architecture Patterns (Recommended Project Structure) | Low — explicitly left to Claude's discretion by CONTEXT.md; either layout is a straightforward file-organization choice with no functional difference |

**If this table is empty:** N/A — two low-risk discretionary assumptions logged above, both already flagged as Claude's-discretion in CONTEXT.md itself, not novel unverified claims.

## Open Questions

1. **Should `TradeRequest.quantity` be typed `float` (matching `AddTickerRequest`'s existing convention) or `Decimal` directly?**
   - What we know: Typing it `float` matches the one existing Pydantic request-model convention in this codebase (`AddTickerRequest`) and is the simpler, more consistent choice; CONTEXT.md's Decimal-boundary rule ("construct from `str(value)`, never a raw float directly") already anticipates converting a `float` request field to `Decimal` inside `execute_trade()`.
   - What's unclear: Whether typing the request field `Decimal` directly (letting Pydantic-core parse the raw JSON number token) would avoid an intermediate `float` representation entirely for user-supplied quantity — this was not verified this session (would require confirming exactly how FastAPI decodes the request body before Pydantic validation, which was inconclusive from the docs fetched).
   - Recommendation: Use `float` for consistency with the existing codebase convention and CONTEXT.md's explicit boundary rule; the marginal precision difference is not material at this project's scale (simulated trading, fractional shares, no regulatory precision requirement). Do not spend planning time chasing the more "theoretically precise" Decimal-typed-request-field approach — it's an unverified, low-value optimization.

## Environment Availability

**Skipped.** This phase is a pure code/config change against already-running infrastructure (existing FastAPI app, existing SQLite file, existing Next.js dev setup) — no new external tool, service, or runtime dependency is introduced. `uv`, `node`/`npm`, and SQLite are already verified available and in continuous use since Phase 1.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ / pytest-asyncio 0.24+ [VERIFIED: backend/pyproject.toml] |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| Quick run command | `cd backend && uv run --extra dev pytest tests/db/test_portfolio.py -x` |
| Full suite command | `cd backend && uv run --extra dev pytest -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PORT-02 | Fractional-share buy succeeds, cash debited exactly | unit | `pytest tests/db/test_portfolio.py::test_buy_fractional_shares -x` | ❌ Wave 0 |
| PORT-02 | Exact-balance buy spends exactly all cash (boundary) | unit | `pytest tests/db/test_portfolio.py::test_buy_exact_balance -x` | ❌ Wave 0 |
| PORT-04 | Insufficient-cash buy is rejected, state untouched | unit | `pytest tests/db/test_portfolio.py::test_buy_rejected_insufficient_cash -x` | ❌ Wave 0 |
| PORT-03 | Full-position sell deletes the `positions` row | unit | `pytest tests/db/test_portfolio.py::test_sell_full_position_deletes_row -x` | ❌ Wave 0 |
| PORT-03 | Partial sell reduces quantity, keeps avg_cost unchanged | unit | `pytest tests/db/test_portfolio.py::test_sell_partial_reduces_quantity -x` | ❌ Wave 0 |
| PORT-04 | Insufficient-shares sell is rejected, state untouched | unit | `pytest tests/db/test_portfolio.py::test_sell_rejected_insufficient_shares -x` | ❌ Wave 0 |
| PORT-04 | Concurrency proof: N simultaneous buys against fixed cash never overspend | unit | `pytest tests/db/test_portfolio.py::test_concurrent_buys_never_exceed_cash -x` | ❌ Wave 0 |
| PORT-01 | `GET /api/portfolio` returns correct P&L/% for a known position+price | unit | `pytest tests/routes/test_portfolio.py::test_get_portfolio_computes_pnl -x` | ❌ Wave 0 |
| PORT-01 | Position with no cached price returns null current_price, not a crash | unit | `pytest tests/routes/test_portfolio.py::test_get_portfolio_missing_price_returns_null -x` | ❌ Wave 0 |
| UI-05, UI-03 | Trade bar buy/sell flow, header live update | manual-only | N/A — visual/live-tick behavior; justification: same category of gap Phase 1 deferred to `/gsd-verify-work` (flash animation, live rendering require a real browser session) | ❌ N/A |

### Sampling Rate

- **Per task commit:** `cd backend && uv run --extra dev pytest tests/db/test_portfolio.py tests/routes/test_portfolio.py -x`
- **Per wave merge:** `cd backend && uv run --extra dev pytest -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/db/test_portfolio.py` — covers PORT-02, PORT-03, PORT-04 (data-access-layer tests, mirroring `test_watchlist.py`'s `temp_db` fixture + `asyncio.gather` concurrency style)
- [ ] `backend/tests/routes/test_portfolio.py` — covers PORT-01, PORT-05 (route-level status codes/shapes, mirroring existing route test conventions)
- [ ] No new fixtures needed — `temp_db` (`backend/tests/conftest.py:14-20`) and `client` (`backend/tests/conftest.py:23-33`) already cover this phase's needs, verified this session. [VERIFIED: backend/tests/conftest.py:14-33]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth in v1 (single hardcoded `user_id="default"`, per PLAN.md/REQUIREMENTS.md Out of Scope) — out of this phase's scope entirely |
| V3 Session Management | no | Same reason as V2 |
| V4 Access Control | no | Single-user, no resource ownership boundary to enforce this phase |
| V5 Input Validation | yes | `quantity: float = Field(gt=0)` on `TradeRequest` (rejects zero/negative at the Pydantic layer, before any DB call); `side: Literal["buy", "sell"]` (rejects any other string at the Pydantic layer, matching the `trades.side CHECK (side IN ('buy', 'sell'))` DB constraint already in `schema.sql:33`); ticker reuses `normalize_ticker`/`TICKER_PATTERN` from the watchlist route |
| V6 Cryptography | no | No secrets/crypto touched by this phase |
| V11 Business Logic | yes | Atomic `UPDATE ... WHERE <guard>` pattern is itself the ASVS V11 "business logic limits are enforced" control — the sufficiency check cannot be bypassed by racing concurrent requests, per PORT-04 |
| V13 API / Web Service | yes | Trade route returns appropriate 4xx status codes for rejected trades (mirroring the watchlist route's existing 400/404/409 conventions) rather than leaking a 500 or a raw exception message |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Check-then-act race on cash/shares (two concurrent trades both pass a stale check) | Tampering (double-spend of simulated cash) | Atomic `UPDATE ... WHERE <sufficiency guard>` + `cursor.rowcount`, per PORT-04 and Pattern 1 above |
| Negative or zero quantity trade request | Tampering (manufacture cash via a "negative buy") | `Field(gt=0)` on the Pydantic request model — rejected before reaching `execute_trade()` |
| Float-precision drift accumulating across many trades (misreported balances) | Tampering / Repudiation (balance silently diverges from the true sum of trade history) | `Decimal` arithmetic constructed via `str(value)`, per CONTEXT.md's locked rule and Pattern 2 above |
| SQL injection via ticker/side/quantity fields | Tampering | Parameterized `?` placeholders throughout — same discipline already documented and enforced in `backend/app/db/watchlist.py:1-7`'s module docstring, applied identically in the new `portfolio.py` module |
| Trading a ticker with no live price (stale/missing cache entry) | Tampering (fill at a fabricated or zero price) | Explicit `if price is None: reject` guard before any arithmetic — locked in CONTEXT.md ("if the ticker has no cached price yet, reject the trade rather than trading at a stale/missing price") |

## Sources

### Primary (HIGH confidence)
- `backend/app/db/watchlist.py`, `backend/app/db/connection.py`, `backend/app/db/schema.sql`, `backend/app/routes/watchlist.py`, `backend/tests/db/test_watchlist.py`, `backend/tests/conftest.py`, `backend/app/main.py`, `backend/app/market/cache.py`, `backend/app/market/models.py`, `frontend/lib/api.ts`, `frontend/lib/types.ts`, `frontend/lib/useSseStream.ts`, `frontend/components/PriceStreamProvider.tsx`, `frontend/components/AppHeader.tsx`, `frontend/components/AddTickerForm.tsx` — all read directly this session (file paths and line ranges cited inline above where a discrete value is quoted).
- `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json` — read directly this session for version verification.

### Secondary (MEDIUM confidence)
- Context7 `/pydantic/pydantic` (official Pydantic GitHub docs source) — Decimal JSON-mode serialization behavior (string, not float, by default) and the `PlainSerializer(float, when_used='json')` override pattern.
- Context7 `/websites/fastapi_tiangolo` (official FastAPI docs) — `jsonable_encoder` implementation, confirming it delegates to `model_dump(mode="json", ...)` for `BaseModel` instances with no Decimal special-case of its own.
- WebSearch — Python `sqlite3` `cursor.rowcount` semantics for conditional `UPDATE ... WHERE` statements, cross-checked against this project's own working, tested `add_watchlist_ticker` implementation (which already relies on this exact mechanism, proven race-free by `test_concurrent_adds_never_exceed_cap`).

### Tertiary (LOW confidence)
- None — every finding above was either read directly from this repository or cross-checked against an official documentation source.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; versions confirmed directly against the committed lockfiles this session
- Architecture: HIGH — the core atomicity pattern is a direct, verified copy of an already-shipped, already-tested pattern in this exact codebase
- Pitfalls: HIGH — the Decimal/Pydantic serialization pitfall is confirmed against official Pydantic documentation (Context7), not training-data recall

**Research date:** 2026-08-03
**Valid until:** 2026-09-02 (30 days — stable stdlib/FastAPI/Pydantic behavior, no fast-moving dependency in scope)
