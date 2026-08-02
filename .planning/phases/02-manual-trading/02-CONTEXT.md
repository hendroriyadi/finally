# Phase 2: Manual Trading - Context

**Gathered:** 2026-08-03
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run — grey areas resolved directly from PLAN.md/REQUIREMENTS.md/codebase state rather than interactive discussion, per explicit user direction to build the full project without interactive check-ins)

<domain>
## Phase Boundary

This phase delivers the second vertical slice: a user can buy and sell shares at live prices from the trade bar, watch the positions table and header update live, and have over-cash/over-sell attempts atomically rejected. It builds the single, validated `execute_trade()` engine that this phase's manual trade bar calls — and that Phase 4's AI copilot must reuse unchanged (CHAT-03) — plus the read side (positions view, portfolio valuation) both the positions table and header consume.

`positions` and `trades` tables already exist in the schema (Phase 1 created the full six-table schema even though only `users_profile`/`watchlist` were exercised then). This phase is the first writer to `positions`/`trades` and the first reader of `users_profile.cash_balance` beyond the initial seed.

Out of scope: portfolio snapshots/history/heatmap/P&L chart (Phase 3 — `portfolio_snapshots` stays unwritten this phase), AI chat (Phase 4, but must reuse this phase's `execute_trade()` exactly), Docker packaging (Phase 5).

</domain>

<decisions>
## Implementation Decisions

### Atomic trade execution (PORT-04 — the highest-risk area in this project per STATE.md)
- **Money math:** Use Python `Decimal` for all arithmetic inside `execute_trade()` — cash debit/credit, weighted-average cost recompute, proceeds calculation. Construct `Decimal` from `str(value)`, never from a raw float directly (float→Decimal directly imports the float's binary imprecision). Convert to `float` only at the two boundaries: writing to the `REAL` columns (`cash_balance`, `quantity`, `avg_cost`, `price`), and JSON-serializing for the API response. This mirrors the Decimal/float boundary discipline already established in this project's design; no fixed rounding/quantization scheme is imposed beyond what full `Decimal` precision naturally gives — fractional shares and prices carry full precision.
- **Atomicity pattern:** Follow the established idiom this codebase already uses for the watchlist size-cap race (see `backend/app/db/watchlist.py`'s `add_watchlist_ticker(..., max_size=...)`, fixed in the Phase 1 code review as WR-01): a single atomic `UPDATE ... WHERE <sufficiency condition>` statement checked via `cursor.rowcount`, never a separate `SELECT` followed by a conditional `UPDATE`. For a buy: `UPDATE users_profile SET cash_balance = cash_balance - ? WHERE id = ? AND cash_balance >= ?`; if `rowcount == 0`, the buy is rejected as insufficient cash — no other row was read-then-compared in Python. For a sell: the equivalent atomic guard against `positions.quantity`. This is what makes PORT-04's "atomically... preventing check-then-deduct races" true under concurrent requests, exactly as `backend/tests/db/test_watchlist.py`'s `test_concurrent_adds_never_exceed_cap` already proves the pattern for the cap.
- **Single entry point:** `execute_trade(ticker, side, quantity, user_id=DEFAULT_USER_ID)` (or equivalent single function/class method) is the ONLY way any code — this phase's trade-bar route, and Phase 4's AI copilot later — is allowed to mutate cash, positions, or trades. No parallel/duplicate validation logic. Reads the current price from the existing, frozen `PriceCache` (via `app.state.price_cache`, the same DI pattern the watchlist route already uses for `app.state.market_source`); if the ticker has no cached price yet, reject the trade rather than trading at a stale/missing price.
- **Position upsert on buy:** Weighted-average cost recompute: `new_avg_cost = (old_qty * old_avg_cost + trade_qty * price) / (old_qty + trade_qty)`, all in `Decimal`. First buy of a ticker inserts a new `positions` row; subsequent buys update the existing row via the `(user_id, ticker)` UNIQUE constraint already in the schema.
- **Position handling on sell:** Full-position sell (selling exactly `quantity`) deletes the `positions` row rather than leaving a `quantity=0` row — this was flagged as a requirement in the (superseded) earlier planning pass and remains correct: a phantom zero-quantity position would render oddly in Phase 3's positions table/heatmap. Partial sell reduces `quantity` in place; `avg_cost` is unchanged by a sell (average cost only moves on buys, standard portfolio accounting).
- **Trade log:** Every successful buy/sell appends one row to `trades` (ticker, side, quantity, price, executed_at) in the same atomic unit of work as the cash/position mutation — trade history and state must never diverge.
- **Rejection is silent-safe:** Per REQUIREMENTS.md and PLAN.md, a rejected trade (insufficient cash/shares) leaves cash, positions, and trade history byte-identical — verify this the same way Phase 1's `01-02-PLAN.md` proved rejections leave state untouched (fresh-connection assertions, not trusting the in-process return value).

### Routes and Read Side (PORT-01, PORT-02, PORT-03, PORT-05)
- `POST /api/portfolio/trade` — body `{ticker, side: "buy"|"sell", quantity}`, calls `execute_trade()`, returns the updated position (or its absence, if the sell emptied it) plus new cash balance. No confirmation step, no fees — instant fill at the current cached price (PLAN.md §9 auto-execution philosophy, extended here to manual trades too since PLAN.md explicitly says manual trades also have zero confirmation).
- `GET /api/portfolio` — returns cash balance, computed total portfolio value (cash + sum of position market values at current cached prices), and every position with quantity, avg_cost, current_price, unrealized P&L, and % change. Positions with no current cached price (edge case: a position exists for a ticker no longer in the watchlist, so the market source stopped tracking it) should surface a null/absent current price rather than crashing — same "assume the cache can be missing" discipline already established in this codebase's ARCHITECTURE.md anti-patterns list.
- Ticker validation on the trade route reuses the same normalization/shape-check discipline established in Phase 1's watchlist route (`normalize_ticker`, `TICKER_PATTERN`) — do not invent a second validation path.

### Frontend (UI-03, UI-05)
- **Trade bar:** ticker input + quantity input + Buy button + Sell button. Instant fill, no confirmation dialog (matches the watchlist remove-control's no-confirmation precedent already established in Phase 1). Disabled/spinner state while in flight (same in-flight-disable pattern as `AddTickerForm`/`RemoveTickerButton`). On rejection (insufficient cash/shares), show the server's rejection reason inline — do not silently fail.
- **Positions table:** ticker, quantity, avg cost, current price, unrealized P&L, % change — one row per open position, updating live as `GET /api/portfolio` values change. Given the trade bar and header both need portfolio state, and Phase 1 already established a single shared `EventSource`/context pattern (`PriceStreamProvider`) for prices, this phase should introduce an equivalent shared portfolio-state fetch (poll or refetch after a trade) so the trade bar, positions table, and header all read one consistent portfolio state rather than each fetching independently — but there is no portfolio SSE stream in this phase's scope (that's not a requirement here); a refetch-on-trade-completion plus a light polling interval is sufficient. Exact polling interval is Claude's discretion.
- **Header (UI-03):** total portfolio value, cash balance, connection-status dot — the dot already exists from Phase 1 (`ConnectionStatusDot`/`PriceStreamProvider`); this phase adds the live value/cash display alongside it. Total portfolio value must update as prices tick (not just after a trade), since it's `cash + sum(qty * current_price)` and `current_price` changes every SSE frame — this likely means the header (or a shared portfolio-context) needs to combine the existing price stream with the fetched position quantities/avg costs to recompute value client-side on every tick, rather than re-fetching `GET /api/portfolio` on every SSE frame (500ms cadence — that would hammer the backend). Recommended: fetch positions/cash from the backend (source of truth for quantity/avg_cost/cash), then compute live current-price-driven value/P&L entirely client-side from the existing price stream, refetching positions/cash only after a trade completes or on a light interval.

### Testing (TEST-01)
- Backend unit tests must cover: fractional-share buys/sells, exact-balance buy (spend exactly all cash), full-position sell (position row deleted, not zeroed), insufficient-cash rejection, insufficient-shares rejection, and a concurrency proof (two simultaneous trades against the same cash/position racing) modeled on `backend/tests/db/test_watchlist.py`'s existing `test_concurrent_adds_never_exceed_cap` pattern.

### Claude's Discretion
- Exact module/file layout for the new trade engine and portfolio read-side (e.g. `backend/app/portfolio/` mirroring the `backend/app/db/`+`backend/app/routes/` split already established, or folding into `backend/app/db/`) — planner's call, following existing `snake_case`/`PascalCase` conventions.
- Exact polling interval (if any) for refreshing portfolio state beyond trade-completion refetch.
- Whether `execute_trade()` is a free function or a small class — match whatever shape reads most naturally alongside the existing `add_watchlist_ticker`-style free-function pattern in `backend/app/db/watchlist.py`, unless the planner has a specific reason to prefer a class (e.g. bundling read+write helpers).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/app/db/connection.py` — `run_db(fn)`, `connect()` (WAL + busy_timeout already configured, reissued per connection). The trade engine's atomic UPDATE...WHERE pattern runs inside a single `fn` passed to `run_db`, exactly like `watchlist.py`'s `add_watchlist_ticker` does.
- `backend/app/db/watchlist.py` — `add_watchlist_ticker(..., max_size=...)` is the canonical reference implementation of the atomic-check-via-WHERE-clause-and-rowcount pattern this phase's `execute_trade()` must follow for PORT-04.
- `backend/app/market/cache.py` — `PriceCache.get_price(ticker) -> float | None`, already injected into `app.state.price_cache` by `backend/app/main.py`'s `create_app()`.
- Frontend: `frontend/lib/api.ts` (`API_BASE`, `ApiError` class, `fetchWatchlist`-style typed fetch pattern) — add `fetchPortfolio()`/`executeTrade()` following the identical pattern. `frontend/components/PriceStreamProvider.tsx` (shared `EventSource` via context) — the pattern to follow if a shared portfolio-state context is introduced. `frontend/lib/useSseStream.ts` — same accumulator-ref-then-publish-to-state shape if any client-side derived state (e.g. live portfolio value) needs it.

### Established Patterns
- `from __future__ import annotations`, full type hints, `snake_case`/`PascalCase`, module-level `logger = logging.getLogger(__name__)`, prose docstrings, specific exception handling (no bare `except:`), `asyncio.to_thread()` for blocking I/O (already the case via `run_db`).
- Compensation-on-failure pattern (Phase 1 WR-02): if a downstream call after a DB mutation can fail, wrap it and compensate rather than leaving state diverged. Likely not needed for trade execution itself (no downstream call after the cash/position/trade write — the whole thing is one DB transaction), but worth keeping in mind if the route layer adds anything after `execute_trade()` returns.
- Non-optimistic frontend mutations (Phase 1 `AddTickerForm`/`RemoveTickerButton`): UI state only updates after the server confirms success, never before.
- Error handling for non-`ApiError` failures (Phase 1 WR-06 fix): any thrown error, not just `ApiError`, must produce user-facing feedback — apply the same discipline to the new trade bar.

### Integration Points
- Trade route needs `app.state.price_cache` (already available) — no new market-data wiring needed, this phase only reads prices, never writes them.
- `backend/tests/` mirrors `backend/app/` — new tests belong in `backend/tests/portfolio/` (or wherever the planner places the new package) mirroring its structure, following `backend/tests/db/test_watchlist.py`'s established test style (temp_db fixture, concurrency proofs via `asyncio.gather`).

</code_context>

<specifics>
## Specific Ideas

- The full-position-sell-deletes-the-row decision is explicitly carried forward from earlier planning discussion and should not be re-litigated — it exists specifically to avoid a phantom `quantity=0` row rendering oddly in Phase 3's positions table and heatmap.
- Total portfolio value recompute must be driven by the live price stream, not a slow poll, since "updating live" (success criterion 3 and 4) is an explicit phase requirement — reuse the existing SSE infrastructure rather than inventing a new one.

</specifics>

<deferred>
## Deferred Ideas

- Portfolio snapshots (30s interval + post-trade) and portfolio value history — Phase 3 (PORT-06/07).
- Heatmap and P&L chart — Phase 3.
- AI-initiated trades — Phase 4 (must call this phase's `execute_trade()` unchanged, per CHAT-03).
- Docker packaging — Phase 5.

</deferred>
