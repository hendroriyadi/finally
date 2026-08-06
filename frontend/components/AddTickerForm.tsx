"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { addWatchlistTicker, ApiError } from "@/lib/api";
import type { WatchlistItem } from "@/lib/types";

export const MAX_TICKER_LENGTH = 10;

interface AddTickerFormProps {
  onAdded: (item: WatchlistItem) => void;
  disabled?: boolean;
}

/**
 * Add-ticker input + submit button. Client-side uppercase/cap match what the
 * server's shape check accepts, so the user sees the constraint rather than
 * discovering it in an error — but the server's `normalize_ticker` check is
 * the authoritative control (see 01-04-PLAN.md threat T-01-14).
 */
export function AddTickerForm({ onAdded, disabled }: AddTickerFormProps) {
  const [value, setValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalized = value.trim().toUpperCase();
    if (normalized === "") {
      return;
    }

    setSubmitting(true);
    setErrorMessage(null);

    try {
      const item = await addWatchlistTicker(normalized);
      onAdded(item);
      setValue("");
      setErrorMessage(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(`Couldn't add ${normalized} — check the symbol and try again.`);
      } else {
        // A non-ApiError failure (e.g. a bare network error while offline)
        // must still surface to the user — re-throwing here would become an
        // unhandled promise rejection from this async event handler, with
        // no feedback beyond the button silently stopping its spinner
        // (WR-06). Log the original error for diagnostics and show the same
        // user-facing copy as a normal add failure.
        console.error("AddTickerForm: unexpected error adding ticker", err);
        setErrorMessage(`Couldn't add ${normalized} — check the symbol and try again.`);
      }
    } finally {
      setSubmitting(false);
    }
  }

  const isSubmitDisabled = disabled || submitting || value.trim() === "";

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value.toUpperCase().slice(0, MAX_TICKER_LENGTH))}
          maxLength={MAX_TICKER_LENGTH}
          autoCapitalize="characters"
          spellCheck={false}
          placeholder="e.g. AAPL"
          disabled={disabled}
          className="rounded border border-edge bg-canvas px-2 py-1 text-sm font-normal leading-normal text-[#e6edf3] placeholder:text-[#8b949e] focus:outline-none focus:ring-2 focus:ring-accent"
        />
        <button
          type="submit"
          disabled={isSubmitDisabled}
          className="flex items-center gap-1.5 rounded bg-submit px-4 py-1 text-sm font-normal leading-normal text-[#e6edf3] focus:outline-none focus:ring-2 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? <Loader2 size={14} className="animate-spin" /> : null}
          Add Ticker
        </button>
      </div>
      {errorMessage ? (
        <p role="alert" className="text-xs font-normal leading-normal text-destructive">
          {errorMessage}
        </p>
      ) : null}
    </form>
  );
}
