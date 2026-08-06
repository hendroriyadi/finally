---
phase: 02-manual-trading
reviewed: 2026-08-03T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - backend/app/db/portfolio.py
  - backend/app/main.py
  - backend/app/routes/portfolio.py
  - backend/tests/db/test_portfolio.py
  - backend/tests/routes/test_portfolio.py
  - frontend/app/layout.tsx
  - frontend/app/page.tsx
  - frontend/components/AppHeader.tsx
  - frontend/components/PortfolioProvider.tsx
  - frontend/components/PositionsTable.tsx
  - frontend/components/TradeBar.tsx
  - frontend/lib/api.ts
  - frontend/lib/types.ts
findings:
  critical: 2
  warning: 3
  info: 2
  total: 7
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-08-03T00:00:00Z
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

The atomic-guard pattern this phase was explicitly built to get right — single `UPDATE ... WHERE <sufficiency check>` + `cursor.rowcount`, no separate SELECT-then-UPDATE — is implemented correctly for both `_apply_buy` and `_apply_sell` in `backend/app/db/portfolio.py`, and the concurrency test suite (`test_concurrent_buys_never_overdraw_balance`, `test_concurrent_full_sells_never_oversell`, `test_concurrent_partial_sells_fill_exactly_what_position_affords`) genuinely exercises that guard with 20 concurrent callers. All SQL statements use `?` placeholders — no injection surface. Full-position-sell-deletes-the-row is implemented and tested for round-number quantities.

However, two concrete, reproducible defects were found in exactly the areas flagged for scrutiny:

1. The full-position-sell "delete the row, don't leave `quantity == 0`" guarantee (D-05) silently fails — or wrongly rejects a legitimate sell — whenever a position's true quantity carries more decimal precision than the UI's 6-decimal display, which is a routine, not exotic, consequence of the weighted-average-cost buy path the engine itself implements. Concrete repro included below.
2. `execute_trade()` — the function the codebase's own docstring designates as "the single entry point for every mutation of cash, positions, and trade history" for both the manual trade bar *and* Phase 4's forthcoming AI copilot — performs no defense against a non-positive `quantity`. The only guard against a negative-quantity buy/sell (which manufactures cash or shares) lives in the HTTP route's Pydantic schema, a layer the documented future caller bypasses entirely.

## Critical Issues

### CR-01: Full-position sell can leave a "dust" position or wrongly reject a legitimate full sell, for any holding whose quantity has more than 6 decimal digits of precision

**File:** `backend/app/db/portfolio.py:212-216` (compared against `frontend/components/PositionsTable.tsx:11-15`)

**Issue:**
`_apply_sell` deletes the position row only when the post-subtraction remaining quantity is `Decimal("0")` **exactly** (line 213: `if remaining == Decimal("0")`), with the module's own comment acknowledging this "no tolerance window" design relies on the subtrahend being "bit-identical to the stored value when the caller sells exactly what is held."

That bit-identical assumption breaks down whenever the true stored quantity has more decimal digits than the frontend can display. `_upsert_position_on_buy` (lines 145-178) computes a new weighted-average quantity via exact Decimal addition and stores it as a raw `float` with full precision — nothing rounds it to a "nice" number of decimals. But `PositionsTable.tsx`'s `formatQuantity()` (lines 11-15) always truncates the on-screen value to 6 decimals via `toFixed(6)` before trimming trailing zeros. A user closing a position necessarily types back the *displayed* (rounded) value, not the true stored value, since there is no "Sell Max" affordance and the API never exposes a "sell everything" primitive.

I reproduced this end-to-end with the exact algorithm in `_upsert_position_on_buy`/`_apply_sell` (buys with realistic fractional share sizes and prices, exactly what real weighted-average accumulation over several trades produces):

```
buy 16.9 @ 315.72   -> stored qty 39.1
buy 17.9289 @ 149.2 -> stored qty 70.6289
buy 4.0755 @ 203.11 -> stored qty 89.5044   (this example rounds cleanly)
```

Running the same buy sequence with 20,000 randomized realistic fractional trials (share sizes/prices with 2-8 decimal digits, matching what fractional-share buys and weighted averaging naturally produce) showed **78% of trials** produced a stored quantity whose 6-decimal-rounded display differs from the true stored value, e.g.:

```
stored quantity = 74.1457117
UI displays      = 74.145712   (toFixed(6) rounds UP)
```

Two distinct failure modes result when the user types the displayed value into `TradeBar` to sell everything:

- **Displayed value rounds down** (stored value's 7th+ digit < 5, e.g. `85.97758124` → displays `85.977581`): the sell succeeds (guard passes since displayed < stored) but leaves a "dust" position of `2.4e-07` shares that can never again be closed by typing a whole number of shares, and will never satisfy the exact-zero check on any future sell of the same size — this position row lives in the database, and in the UI, forever.
- **Displayed value rounds up** (stored value's 7th+ digit ≥ 5, e.g. `74.1457117` → displays `74.145712`): the sell is flat-out **rejected with 409 Insufficient Shares**, even though the user is trying to sell their entire, real, legitimately-held position — there is no way to close this position through the UI at all without knowing the exact unrounded float.

This directly contradicts the module's own documented invariant (D-05, "Full-position sell deletes the row rather than leaving `quantity == 0`") for a realistic, easily-reached class of holdings — any position built from more than one weighted-average buy with fractional share counts, which is an explicitly supported feature (`positions.quantity REAL` / "fractional shares supported" per `planning/PLAN.md`).

**Fix:** Do not compare the remaining quantity to `Decimal("0")` with zero tolerance. Round the *stored* quantity itself to a fixed, UI-compatible precision at every write (e.g. quantize to 6-8 decimal places in `_upsert_position_on_buy` and `_apply_sell` before persisting), and/or treat any remaining quantity below a small absolute threshold as zero:

```python
# in _apply_sell, after computing `remaining`:
if remaining <= Decimal("0.000001"):
    conn.execute(
        "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker)
    )
```
Additionally, expose a way to sell an exact full position without the user re-typing a rounded number (e.g. a "Sell Max" control in `TradeBar` that sources the quantity from the server's own position record rather than a hand-typed value) — see WR-03 below.

---

### CR-02: `execute_trade()` has no guard against a non-positive, NaN, or infinite quantity — the only defense lives in the HTTP layer, which the documented future caller (Phase 4's AI copilot) bypasses

**File:** `backend/app/db/portfolio.py:44-129` (guard is instead only in `backend/app/routes/portfolio.py:43`)

**Issue:**
The module docstring states plainly: "`execute_trade()` is the single entry point for every mutation of cash, positions, and trade history (the CHAT-03 contract: **Phase 4's AI copilot must call this exact function, unchanged**)." The *only* place `quantity > 0` (and non-NaN, non-infinite) is enforced today is `TradeRequest.quantity: float = Field(gt=0, le=1_000_000_000)` in the HTTP route (`routes/portfolio.py:43`) — a Pydantic validator that a direct Python call to `execute_trade()` (exactly the call pattern Phase 4 is contractually committed to using) never passes through.

Nothing inside `execute_trade`, `_apply_buy`, `_upsert_position_on_buy`, or `_apply_sell` checks the sign or finiteness of `quantity`. Concretely, a direct call with a negative quantity manufactures value in both directions:

- **`execute_trade(ticker, "buy", -5, ...)`**: `cost = quantity_dec * price_dec` is negative. `_apply_buy`'s guard SQL (`portfolio.py:138`) computes `cash_balance - (-cost)`, i.e. it **increases** the cash balance on a "buy" — free money — while the sufficiency check `cash_balance >= (negative cost)` is trivially satisfied for any starting balance.
- **`execute_trade(ticker, "sell", -5, ...)`**: `_apply_sell`'s guard SQL (`portfolio.py:202`) computes `quantity - (-5) = quantity + 5`, **increasing** the held share count on a "sell" (manufacturing shares from nothing), while `proceeds = quantity_dec * price_dec` is negative, so the subsequent cash credit (`portfolio.py:219`) actually **debits** cash — an internally-consistent-looking but entirely fabricated trade.

This is exactly the class of bug the route-layer comment on `TradeRequest.quantity` warns about ("a negative buy would manufacture cash") — but that comment's protection is architecturally scoped to one caller only, while the module's own docstring commits this function to a second caller that skips it entirely. Since `execute_trade` is explicitly the trust boundary for the highest-risk logic in the project, quantity validation belongs inside it, not solely in a caller three files away.

**Fix:** Add an explicit guard at the top of `execute_trade`, alongside the existing `side` validation, before `quantity_dec` is used in any arithmetic:

```python
quantity_dec = Decimal(str(quantity))
if not quantity_dec.is_finite() or quantity_dec <= 0:
    raise TradeRejectedError(f"Invalid trade quantity: {quantity!r}")
```

## Warnings

### WR-01: Module docstring claims "all arithmetic is Decimal," but the actual cash/quantity mutations run as raw SQLite float arithmetic

**File:** `backend/app/db/portfolio.py:6-12, 138, 202, 219`
**Issue:** The docstring states arithmetic is Decimal "with `float` appearing only at the SQLite `REAL` write boundary and the dict-return boundary." In fact the mutating operations themselves — `cash_balance - ?` (line 138), `quantity - ?` (line 202), `cash_balance + ?` (line 219) — are evaluated by SQLite as native double-precision float subtraction/addition, not Decimal arithmetic; Decimal is only used to *derive* the operands beforehand and to *re-check* the result afterward. This is the root mechanism behind CR-01: the "operands are float, and the same connection re-reads a float back through Decimal(str(...))" pattern is safe only when the round trip is exact, and it silently isn't once accumulated quantities exceed the display's precision.
**Fix:** Either perform the full mutation arithmetic in Python/Decimal and write the already-computed final value (rather than delegating the subtraction to SQL), or correct the docstring to describe the actual boundary and add the quantization/tolerance fix from CR-01 so the documented invariant and the implementation agree.

### WR-02: `AppHeader` shows "$0.00"-equivalent figures on a failed portfolio fetch instead of an error/placeholder state

**File:** `frontend/components/AppHeader.tsx:16-40`
**Issue:** `AppHeader` reads `{ totalValue, cashBalance, loading }` from `usePortfolioContext()` but never reads `error`. On a failed initial fetch, `PortfolioProvider` sets `loading = false` and `error = true` while `cashBalance`/`positions` remain at their unset defaults (`0`, `[]`), so the header renders `totalValue.toFixed(2)` → `"0.00"` and `cashBalance.toFixed(2)` → `"0.00"`, presenting a load failure as "you have zero dollars" rather than surfacing the error — inconsistent with `PositionsTable`, which correctly branches on `error` (lines 60-63) to show a dedicated failure message.
**Fix:**
```tsx
const { totalValue, cashBalance, loading, error } = usePortfolioContext();
...
{loading ? "—" : error ? "—" : totalValue.toFixed(2)}
```

### WR-03: No "Sell Max" affordance — closing a position always requires hand-typing a quantity that may not round-trip against the stored value

**File:** `frontend/components/TradeBar.tsx:20-126`
**Issue:** The trade bar's quantity field is always free text; there is no way to source a sell quantity directly from the user's actual held position (`usePortfolioContext().positions`). Combined with CR-01, this means the *only* way to attempt a full-position sell is to retype a value read off a truncated display, which routinely does not match the stored quantity bit-for-bit.
**Fix:** Add a "Max"/"Sell All" control next to the sell button, for the currently-entered ticker, that populates the input from the exact `position.quantity` value already in `PortfolioProvider`'s state rather than from any rounded/reformatted string.

## Info

### IN-01: No test exercises a full-position sell where the accumulated quantity has more than 6 decimal digits

**File:** `backend/tests/db/test_portfolio.py`, `backend/tests/routes/test_portfolio.py`
**Issue:** Every weighted-average / full-sell test in both suites uses round inputs (10, 5, 15.0, 0.5, 0.25, 200.0, 100.0, 130.0) that happen to produce quantities with ≤2 decimal digits, so CR-01 has no regression coverage. `test_second_buy_produces_exact_weighted_average_cost` and `test_full_position_sell_leaves_no_row` are the natural home for this case.
**Fix:** Add a case such as: buy `17.9289 @ 149.2`, buy `4.0755 @ 203.11`, then sell the *server-reported* `position.quantity` in full and assert the row is deleted — and a second case asserting that selling the *UI-displayed* (6-decimal-rounded) quantity for the same setup does not silently leave a dust row or spuriously 409.

### IN-02: `TradeBar` has no `<form>` wrapper, so Enter does not submit — unlike the sibling `AddTickerForm`

**File:** `frontend/components/TradeBar.tsx:74-125` (contrast `frontend/components/AddTickerForm.tsx:63`)
**Issue:** `AddTickerForm` wraps its input/button in `<form onSubmit={handleSubmit}>`, giving Enter-to-submit for free. `TradeBar`'s inputs and buttons are bare, unwrapped elements with only `onClick` handlers, so pressing Enter after typing a quantity does nothing — a minor keyboard-UX inconsistency between two closely related, adjacent input patterns in the same app.
**Fix:** Wrap the ticker/quantity inputs in a `<form>` with an `onSubmit` that defaults to one side (or is disabled until a side is chosen), matching `AddTickerForm`'s pattern.

---

_Reviewed: 2026-08-03T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
