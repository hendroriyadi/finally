---
phase: 02-manual-trading
fixed_at: 2026-08-03T00:00:00Z
review_path: .planning/phases/02-manual-trading/02-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-08-03T00:00:00Z
**Source review:** .planning/phases/02-manual-trading/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (2 critical, 3 warning, 2 info)
- Fixed: 7
- Skipped: 0

## Fixed Issues

### CR-01: Full-position sell can leave a "dust" position or wrongly reject a legitimate full sell

**Files modified:** `backend/app/db/portfolio.py`
**Commit:** `eb385e2`
**Applied fix:** Root-caused rather than patched around. Added `_QUANTITY_SCALE` (6 decimal places, matching `PositionsTable.formatQuantity()`'s `toFixed(6)`) and `_quantize_quantity()`. `_upsert_position_on_buy` now quantizes the stored quantity at every write (first insert and weighted-average update), so the stored value is always bit-identical to what the frontend displays — there is no longer a "rounded display" vs. "true stored value" distinction to reconcile. `_apply_sell` compares the post-sell remainder against `_DUST_TOLERANCE` (half of `_QUANTITY_SCALE`, deliberately smaller than any legitimate quantized position so it can only absorb genuine float-subtraction noise from the SQL layer, never a real minimal holding) instead of exact `Decimal("0")`, and re-quantizes any non-dust remainder before writing it back so quantization never regresses across a chain of partial sells.

**Verification methodology:** Before writing the fix, ran a 500-trial integration repro calling `execute_trade()` directly against a real temp SQLite DB (1-4 randomized fractional buys per trial, 2-8 decimal digits, mirroring the review's own methodology), then both selling the server-reported quantity and separately selling the UI-displayed (`toFixed(6)`-rounded) quantity. Pre-fix: 128/500 trials left a dust row, 107/500 trials were falsely rejected with `InsufficientSharesError`. Post-fix (same script, same seed): 0/500 dust, 0/500 false rejections — both failure modes described in CR-01 are closed, not just one. The repro script was thrown away after verification, per instructions.

### CR-02: `execute_trade()` had no guard against a non-positive, NaN, or infinite quantity

**Files modified:** `backend/app/db/portfolio.py`
**Commit:** `eb385e2`
**Applied fix:** Added an explicit `if not quantity_dec.is_finite() or quantity_dec <= 0: raise TradeRejectedError(...)` guard inside `execute_trade()`, immediately after constructing `quantity_dec` and before any arithmetic touches cash or shares. This closes the gap for the documented CHAT-03 direct-call caller (Phase 4's AI copilot), which bypasses the HTTP route's Pydantic `Field(gt=0, ...)` entirely. Checked the route layer (`backend/app/routes/portfolio.py`): its existing `except TradeRejectedError as exc: raise HTTPException(status_code=400, ...)` clause already catches this new error generically (it runs after the more specific `InsufficientCashError`/`InsufficientSharesError` handlers), so no route change was needed.

### WR-01: Module docstring overclaimed "all arithmetic is Decimal"

**Files modified:** `backend/app/db/portfolio.py`
**Commit:** `eb385e2`
**Applied fix:** Rewrote the module docstring to describe the actual boundary accurately: every operand is *derived* via `Decimal(str(value))` and every result is *re-checked* the same way, but the mutating arithmetic itself (`cash_balance - ?`, `quantity - ?`, `cash_balance + ?`) runs as native SQLite float arithmetic inside the UPDATE statements — Decimal never touches the database layer directly. Also explains why `positions.quantity` is now quantized at every write (ties WR-01 directly to the CR-01 fix, as the review requested). Updated `_apply_sell`'s docstring similarly (it previously claimed "no tolerance window... bit-identical... no tolerance window" — now describes the tolerance/quantization approach and why it's safe).

### WR-02: `AppHeader` showed "$0.00" on a failed portfolio fetch instead of an error state

**Files modified:** `frontend/components/AppHeader.tsx`
**Commit:** `7f359d9`
**Applied fix:** `AppHeader` now destructures `error` from `usePortfolioContext()` and renders `"—"` when `loading || error` is true (previously only checked `loading`), matching `PositionsTable`'s existing error-branch precedent (`Couldn't load your positions...`). A failed fetch no longer reads as "you have zero dollars."

### WR-03: No "Sell Max" affordance

**Files modified:** `frontend/components/TradeBar.tsx`
**Commit:** `0ffb349`
**Applied fix:** Added a "Max" button next to the quantity input. It looks up the held position for whatever ticker is currently typed (`positions.find(...)` from `usePortfolioContext()`) and, when found, sets the quantity input to `String(heldPosition.quantity)` — the exact stored value, never passed through `.toFixed()` or any other rounding/reformatting. This gives users a way to close a position without retyping a display-truncated number, which is also a practical mitigation for CR-01 (though CR-01 is now fixed at the root regardless). The button is disabled when there's no position for the currently-entered ticker.

### IN-01: No test coverage for full-position sells with >6-decimal-precision quantities

**Files modified:** `backend/tests/db/test_portfolio.py`
**Commit:** `eb385e2`
**Applied fix:** Added `test_full_position_sell_with_high_precision_quantity_leaves_no_row` (buys a single 7-decimal-digit quantity, asserts the stored value is quantized to 6 decimals, then sells the server-reported quantity in full and asserts the row is deleted) and `test_full_position_sell_with_ui_rounded_quantity_leaves_no_row` (same setup, but sells the value produced by mirroring the frontend's `formatQuantity()` — `toFixed(6)` plus trailing-zero trim — and asserts no dust row and no spurious rejection). Also added `test_execute_trade_rejects_negative_quantity_bypassing_pydantic` and `test_execute_trade_rejects_zero_nan_and_infinite_quantity` as direct regression coverage for CR-02, since a critical money-math guard warranted a companion test even though IN-01 didn't explicitly request it.

### IN-02: `TradeBar` had no `<form>` wrapper

**Files modified:** `frontend/components/TradeBar.tsx`
**Commit:** `0ffb349`
**Applied fix:** Wrapped the ticker/quantity inputs and Buy/Sell/Max buttons in a `<form onSubmit={handleSubmit}>`, matching `AddTickerForm`'s pattern. `handleSubmit` calls `event.preventDefault()` and, if the existing `isDisabled` guard passes, submits a "buy" — Enter defaults to the additive, non-destructive action, while Sell still requires an explicit button click (documented in a code comment). Buy/Sell/Max buttons remain `type="button"` so they aren't double-triggered by the form's native submit.

## Skipped Issues

None — all 7 in-scope findings were fixed.

## Verification Summary

- **Backend:** `uv run --extra dev pytest -q` → 128 passed. `uv run --extra dev ruff check app/ tests/` → all checks passed. Both run clean after all three backend-touching commits (CR-01/CR-02/WR-01/IN-01).
- **Frontend:** `npx tsc --noEmit` → clean. `npx eslint app components lib` → clean. `npm run build` → compiled and prerendered successfully. Both run clean after the WR-02 and WR-03/IN-02 commits.
- **CR-01 specifically:** verified with a throwaway 500-trial integration repro (described above) showing the fix closes both the "dust position" and "false rejection" failure modes, not just one — confirmed by re-running the identical script against the pre-fix code via `git stash`, which reproduced 128 dust + 107 false-rejection failures in the same 500 trials.
- All commits were created with hooks enabled (no `--no-verify`).

---

_Fixed: 2026-08-03T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
