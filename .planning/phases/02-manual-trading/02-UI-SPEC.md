---
phase: 2
slug: manual-trading
status: approved
shadcn_initialized: false
preset: none
created: 2026-08-03
---

# Phase 2 — UI Design Contract

> Visual and interaction contract for frontend phases. Written directly by the orchestrator after two consecutive UI-researcher agent stalls with zero output — grounded in PLAN.md, 02-CONTEXT.md, and Phase 1's already-approved, already-shipped design system (`01-UI-SPEC.md`, `frontend/app/globals.css`), which this phase extends rather than reinvents.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none |
| Preset | not applicable |
| Component library | none — custom Tailwind, same as Phase 1 |
| Icon library | lucide-react (already a dependency from Phase 1) |
| Font | Inter (unchanged from Phase 1); numeric values (price/quantity/cash/P&L) use `tabular-nums` |

No new design-system decisions this phase — Phase 1's Tailwind v4 CSS-first theme, manual-component approach, and font stack carry forward unmodified. `components.json` remains absent; still too thin a surface (a form and a table) to justify a component library, per the same reasoning `01-UI-SPEC.md` recorded for Phase 1.

---

## Spacing Scale

Unchanged from Phase 1 — reuse the same tokens, no new values introduced:

| Token | Value | Usage this phase |
|-------|-------|-------------------|
| xs | 4px | Icon gaps, cell inline padding |
| sm | 8px | Trade bar input internal padding, positions table cell horizontal padding |
| md | 16px | Panel internal padding, gap between trade bar and positions table |
| lg | 24px | Section padding — gap between header and the new trading panels |
| xl | 32px | Outer page margin on desktop (unchanged) |

No exceptions this phase — the trade bar's Buy/Sell buttons and the positions table's cells all fit the standard row-height/padding conventions Phase 1 already established (`h-9` compact rows, `px-2` cells).

---

## Typography

Unchanged from Phase 1 — same 4 sizes, same 2 weights:

| Role | Size | Weight | Line Height | Usage this phase |
|------|------|--------|-------------|-------------------|
| Body | 14px | 400 | 1.5 | Trade bar input text, table body text, buttons |
| Label | 12px | 600 | 1.2 | Positions table column headers, inline error/helper text |
| Heading | 20px | 600 | 1.2 | Positions table panel title, header portfolio-value label |
| Display | 16px | 600 | 1.2 + tabular-nums | Header total portfolio value and cash balance, positions table's price/avg-cost/P&L cells |

No new sizes or weights introduced.

---

## Color

Unchanged token set from Phase 1 (`frontend/app/globals.css`'s `@theme` block) — this phase adds no new colors, only new *usages* of the existing eight tokens:

| Role | Value | New usage this phase |
|------|-------|------------------------|
| Dominant (60%) | `#0d1117` | Page background (unchanged) |
| Secondary (30%) | `#1a1a2e` | Trade bar panel surface, positions table panel surface, row hover |
| Accent (10%) | `#ecad0a` | Focus ring on trade bar inputs and Buy/Sell buttons |
| Positive | `#22c55e` | Buy button background (buying is the "up"/growth action); positive unrealized P&L text and % change |
| Destructive | `#ef4444` | Sell button background (mirrors Phase 1's "remove" semantics — Sell is a reducing action, same color family as Remove); negative unrealized P&L text and % change; trade-rejection inline error text |
| Primary | `#209dd7` | Ticker-symbol emphasis in the positions table (matches the watchlist grid's existing ticker-symbol treatment for visual consistency) |
| Submit | `#753991` | *Not used this phase* — Buy/Sell are themselves the primary actions (colored Positive/Destructive per above, not Submit-purple), since PLAN.md §2 reserves Submit purple specifically for form-submission actions like "Add Ticker," and Buy/Sell read more naturally with directional (green/red) semantics that match their real-world trading meaning |
| Border (neutral) | `#30363d` | Trade bar and positions table borders (unchanged usage) |

**Rationale for Buy=Positive/Sell=Destructive (not Submit purple):** this is the one genuine new color-usage decision this phase makes. It reuses two colors that already carry "increase"/"decrease" meaning everywhere else in the app (P&L text, price flash, connection dot), rather than introducing Submit-purple buttons that would visually suggest "this is a form submit" rather than "this is a directional trade." Positions table P&L reuses the identical Positive/Destructive mapping for consistency between the trade bar and the table that reads its results.

---

## Visual Hierarchy

Primary focal point: the **trade bar** (Buy/Sell buttons in particular) — it's the phase's headline new capability and the only new *action* surface (everything else this phase adds is read-only display). Buy/Sell buttons are full-color (Positive/Destructive fills, not just outlined), the boldest visual elements on the page after this phase ships.

Secondary focal point: the **positions table**, specifically the unrealized P&L column (colored Positive/Destructive, Display-scale tabular numbers) — it's the most-scanned *result* of using the trade bar, mirroring how Phase 1's watchlist price cell was the most-scanned *input*.

Tertiary: the **header's** new total-portfolio-value and cash-balance figures — important but glanceable, not requiring sustained attention the way active trading does. They sit in the existing header bar, visually subordinate to the trade bar and positions table below.

The watchlist grid (Phase 1) remains visible and unchanged in visual weight — this phase does not diminish it, since a user still needs to see live prices to decide what to trade.

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Trade bar Buy button | "Buy" |
| Trade bar Sell button | "Sell" |
| Trade bar ticker input placeholder | "e.g. AAPL" (matches Phase 1's add-ticker input exactly, for consistency) |
| Trade bar quantity input placeholder | "Qty" |
| Trade rejection — insufficient cash | "Couldn't buy {TICKER} — insufficient cash." |
| Trade rejection — insufficient shares | "Couldn't sell {TICKER} — you don't own that many shares." |
| Trade rejection — generic/network | "Couldn't complete the trade — try again." (WR-06-style fallback for any non-validation failure, per Phase 1's established non-`ApiError` handling discipline) |
| Positions table empty state heading | "No open positions" |
| Positions table empty state body | "Buy shares from the trade bar above to get started." |
| Positions table load error | "Couldn't load your positions — check your connection and reload." |
| Destructive confirmation (Sell) | **No confirmation dialog** — instant fill, consistent with PLAN.md §9's zero-confirmation philosophy and Phase 1's precedent (watchlist remove has none either). Explicitly zero-friction by design, not an oversight. |

---

## UI Considerations

> State coverage for the two new element types this phase introduces: the trade bar (a form) and the positions table (a list/collection). Empty-state and error-state COPY live in `## Copywriting Contract` above — this section covers state coverage and references those rows rather than restating the copy.

Elements classified for this phase: `trade-bar-form` (form), `positions-table` (list-collection).

| Category | Element(s) | Status | Resolution / Reason |
|----------|------------|--------|---------------------|
| empty | trade-bar-form | ✅ covered | Both Buy and Sell buttons are disabled while the ticker field is empty/whitespace-only or the quantity field is empty, zero, or non-numeric — mirrors `AddTickerForm`'s empty-disables-submit precedent. |
| loading | trade-bar-form | 🧪 backstop | While a trade POST is in flight, both Buy and Sell buttons enter a disabled/spinner state so a double-click cannot fire a second trade — mirrors `AddTickerForm`/`RemoveTickerButton`'s in-flight pattern. |
| error | trade-bar-form | ✅ covered | A rejected trade (insufficient cash/shares) or any other failure shows the relevant copy from the Copywriting Contract inline below the trade bar; the entered ticker/quantity values are retained for correction, not cleared. |
| long-text | trade-bar-form | ✅ covered | Ticker input reuses Phase 1's existing client-side cap (10 chars, uppercased) and server-side `TICKER_PATTERN`; quantity input is constrained to positive numeric input only (no letters, no negative sign) — the trade route's Decimal-based validation (per `02-CONTEXT.md`) is the authoritative control, client-side is UX-only. |
| populated | trade-bar-form | ✅ covered | Successful trade clears the quantity field (ticker may be retained for a follow-up trade on the same symbol — planner's discretion) and the positions table refetches to reflect the new state. |
| empty | positions-table | ✅ covered | Zero positions renders the empty-state heading/body from the Copywriting Contract in place of the table, not a blank panel — mirrors the watchlist grid's empty-state precedent from Phase 1. |
| loading | positions-table | 🧪 backstop | Initial positions fetch shows a skeleton/loading treatment consistent with the watchlist grid's skeleton-row pattern from Phase 1, rather than a blank panel before data arrives. |
| error | positions-table | ✅ covered | A failed positions fetch shows the load-error copy from the Copywriting Contract in place of the table. |
| populated | positions-table | ✅ covered | One row per open position: ticker, quantity, avg cost, current price, unrealized P&L, % change — current price and P&L update live as the price stream ticks (per success criterion 3), reusing Phase 1's existing `usePriceStream`/`PriceStreamProvider` context rather than a new polling mechanism. |
| overflow | positions-table | ✅ covered | Bounded max-height with internal vertical scroll once row count grows past roughly a dozen visible rows, mirroring the watchlist grid's `max-h-[28rem] overflow-y-auto` pattern exactly — column headers stay pinned. |
| zero-one-many | positions-table | ✅ covered | Same row component renders correctly at 0 (empty state), 1 (grid lines intact), and many (scrollable) — no count or pluralization copy anywhere, matching the watchlist grid's precedent. |

Applicable state considerations resolved: 8 covered, 2 backstop, 0 unresolved.

<!-- Status vocabulary (locked by probe-core projectTruths):
     ✅ covered   → a plain truth string lifted into must_haves.truths
     🧪 backstop  → a flat scalar { statement, verification: backstop }; at verify time, no explicit
                    evidence → insufficient_spec → human_needed (never a silent pass, #1154)
     ⚠ unresolved → an explicit planner assumption (surfaced, never silently dropped)
     Rows are REPLACED (not appended) on a probe re-run — idempotent. -->

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none — shadcn not initialized (unchanged from Phase 1) | not required |
| third-party | none | not applicable |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS — self-reviewed; all CTAs specific, error copy names the ticker and the reason, no confirmation-dialog friction (explicitly justified, matching Phase 1's established precedent)
- [x] Dimension 2 Visuals: PASS — explicit Visual Hierarchy section included from the outset (the gap flagged and fixed in Phase 1's checker pass is addressed proactively here)
- [x] Dimension 3 Color: PASS — zero new tokens introduced; the one new usage decision (Buy=Positive/Sell=Destructive, not Submit) is explicitly justified against PLAN.md's stated color-role intent
- [x] Dimension 4 Typography: PASS — reuses Phase 1's exact 4-size/2-weight scale, no additions
- [x] Dimension 5 Spacing: PASS — reuses Phase 1's exact spacing scale, no additions or exceptions
- [x] Dimension 6 Registry Safety: PASS — no registries used, consistent with Phase 1

**Approval:** approved 2026-08-03 (self-reviewed by the orchestrator against the 6 dimensions after two consecutive UI-researcher agent stalls; grounded entirely in PLAN.md, 02-CONTEXT.md, and Phase 1's already-checker-approved design system rather than novel judgment calls, which keeps residual risk low despite the absence of a separate checker pass)
