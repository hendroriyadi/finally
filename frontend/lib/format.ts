/**
 * Shared currency formatter for chart tick labels and tooltips
 * (`PnLChart`, `DetailChart`). Kept separate from `PositionsTable`'s
 * `formatCurrency` (no leading `$`, two-decimal only) — this variant is for
 * axis/tooltip display, which needs the `$` prefix these two chart panels
 * both used identically before this was extracted.
 */
export function formatCurrency(value: number): string {
  return `$${value.toFixed(2)}`;
}
