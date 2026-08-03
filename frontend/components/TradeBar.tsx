"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { executeTrade, ApiError } from "@/lib/api";
import type { TradeSide } from "@/lib/types";
import { usePortfolioContext } from "@/components/PortfolioProvider";
import { MAX_TICKER_LENGTH } from "@/components/AddTickerForm";

const QUANTITY_PATTERN = /^\d*\.?\d*$/;

/**
 * Ticker + quantity inputs with Buy/Sell buttons. Instant fill, no
 * confirmation dialog (PLAN.md §9's zero-confirmation philosophy, matching
 * Phase 1's watchlist remove-control precedent). Every fill is
 * non-optimistic: `refresh()` is only awaited on the success path, so the
 * displayed cash/position figures always originate from a server response,
 * never a local guess (T-02-23).
 */
export function TradeBar() {
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [pendingSide, setPendingSide] = useState<TradeSide | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { refresh } = usePortfolioContext();

  const parsedQuantity = Number(quantity);
  const isDisabled =
    pendingSide !== null ||
    ticker.trim() === "" ||
    !Number.isFinite(parsedQuantity) ||
    parsedQuantity <= 0;

  async function submit(side: TradeSide) {
    const symbol = ticker.trim().toUpperCase();
    if (isDisabled) {
      return;
    }

    setPendingSide(side);
    setErrorMessage(null);

    try {
      await executeTrade(symbol, side, Number(quantity));
      setQuantity("");
      setErrorMessage(null);
      // Non-optimistic: the header and positions table only reflect this
      // fill once the server's own state is re-fetched.
      await refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409 && side === "buy") {
          setErrorMessage(`Couldn't buy ${symbol} — insufficient cash.`);
        } else if (err.status === 409 && side === "sell") {
          setErrorMessage(`Couldn't sell ${symbol} — you don't own that many shares.`);
        } else {
          setErrorMessage("Couldn't complete the trade — try again.");
        }
      } else {
        // A non-ApiError failure (e.g. a bare network error while offline)
        // must still surface to the user — re-throwing here would become an
        // unhandled promise rejection from this async click handler, with
        // no feedback beyond the button silently stopping its spinner
        // (WR-06, matching AddTickerForm's established discipline).
        console.error("TradeBar: unexpected error executing trade", err);
        setErrorMessage("Couldn't complete the trade — try again.");
      }
    } finally {
      setPendingSide(null);
    }
  }

  return (
    <div className="flex flex-col gap-1 rounded-md border border-edge bg-panel p-4">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase().slice(0, MAX_TICKER_LENGTH))}
          maxLength={MAX_TICKER_LENGTH}
          autoCapitalize="characters"
          spellCheck={false}
          placeholder="e.g. AAPL"
          className="rounded border border-edge bg-canvas px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
        />
        <input
          type="text"
          inputMode="decimal"
          value={quantity}
          onChange={(e) => {
            const next = e.target.value;
            if (next === "" || QUANTITY_PATTERN.test(next)) {
              setQuantity(next);
            }
          }}
          placeholder='Qty'
          className="rounded border border-edge bg-canvas px-2 py-1 text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-accent"
        />
        <button
          type="button"
          disabled={isDisabled}
          onClick={() => submit("buy")}
          className="flex items-center gap-1.5 rounded bg-positive px-4 py-1 text-sm text-[#e6edf3] focus:outline-none focus:ring-2 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pendingSide === "buy" ? <Loader2 size={14} className="animate-spin" /> : null}
          Buy
        </button>
        <button
          type="button"
          disabled={isDisabled}
          onClick={() => submit("sell")}
          className="flex items-center gap-1.5 rounded bg-destructive px-4 py-1 text-sm text-[#e6edf3] focus:outline-none focus:ring-2 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pendingSide === "sell" ? <Loader2 size={14} className="animate-spin" /> : null}
          Sell
        </button>
      </div>
      {errorMessage ? (
        <p role="alert" className="text-xs font-semibold leading-tight text-destructive">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}
