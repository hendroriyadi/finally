"use client";

import { AlertCircle, CheckCircle2 } from "lucide-react";
import type { ChatActionResult } from "@/lib/types";

// Module-local by convention, matching PositionsTable's own formatters —
// these figures must READ identically to that table's, which is a matter of
// copying the behaviour, not importing the symbol.
function formatQuantity(quantity: number): string {
  return quantity.toFixed(6).replace(/\.?0+$/, "");
}

function formatCurrency(value: number): string {
  return `$${value.toFixed(2)}`;
}

/**
 * One executed action, rendered inline beneath the assistant reply that
 * caused it. This project executes AI-initiated trades with no confirmation
 * dialog on purpose (planning/PLAN.md §9); this card is the entire
 * transparency mitigation for that choice, which is why a reply that
 * executed nothing renders no card at all — a card's presence is always
 * meaningful.
 *
 * A successful sell is styled exactly like a successful buy. Whether the
 * trade made money is a different question with its own surfaces; conflating
 * "this instruction executed" with "this was profitable" would make one
 * colour mean two things.
 */
export function ChatActionCard({ action }: { action: ChatActionResult }) {
  const failed = action.status === "error";

  const label = failed
    ? // The backend's own sentence, verbatim — already worded identically to
      // the trade bar's and add-ticker form's rejections. Re-wording it here
      // would create a second copy free to drift from those.
      (action.error ?? "")
    : buildSuccessLabel(action);

  const Icon = failed ? AlertCircle : CheckCircle2;
  const toneClasses = failed
    ? "border-destructive/40 bg-destructive/10 text-destructive"
    : "border-positive/40 bg-positive/10 text-positive";

  return (
    <div
      className={`flex items-start gap-2 rounded-md border px-3 py-2 text-xs font-semibold leading-tight ${toneClasses}`}
    >
      <Icon className="mt-px h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="min-w-0 break-words text-base font-semibold leading-tight tabular-nums">
        {label}
      </span>
    </div>
  );
}

function buildSuccessLabel(action: ChatActionResult): string {
  if (action.kind === "trade") {
    // `!= null` (not `!== undefined`) is deliberate: these arrive as an
    // explicit null when they don't apply, and a `!== undefined` guard would
    // pass a null straight into `.toFixed()`.
    const qty = action.quantity != null ? formatQuantity(action.quantity) : "";
    const price = action.price != null ? formatCurrency(action.price) : "";
    const verb = action.side === "sell" ? "Sold" : "Bought";
    return `${verb} ${qty} ${action.ticker} at ${price}`;
  }
  return action.action === "remove"
    ? `Removed ${action.ticker} from your watchlist.`
    : `Added ${action.ticker} to your watchlist.`;
}
