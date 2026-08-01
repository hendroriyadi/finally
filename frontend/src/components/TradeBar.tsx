"use client";

import { useEffect, useState } from "react";
import { money } from "@/lib/format";
import type { Side } from "@/lib/types";

interface TradeBarProps {
  defaultTicker: string | null;
  price: number | null;
  onTrade: (ticker: string, quantity: number, side: Side) => Promise<void>;
}

export function TradeBar({ defaultTicker, price, onTrade }: TradeBarProps) {
  const [ticker, setTicker] = useState(defaultTicker ?? "");
  const [quantity, setQuantity] = useState("1");
  const [pending, setPending] = useState<Side | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(
    null,
  );

  useEffect(() => {
    if (defaultTicker) setTicker(defaultTicker);
  }, [defaultTicker]);

  const submit = async (side: Side) => {
    const symbol = ticker.trim().toUpperCase();
    const qty = Number(quantity);
    if (!symbol || !Number.isFinite(qty) || qty <= 0) {
      setStatus({ ok: false, text: "Enter a ticker and a positive quantity" });
      return;
    }
    setPending(side);
    setStatus(null);
    try {
      await onTrade(symbol, qty, side);
      setStatus({ ok: true, text: `${side.toUpperCase()} ${qty} ${symbol} filled` });
    } catch (err) {
      setStatus({
        ok: false,
        text: err instanceof Error ? err.message : "Trade rejected",
      });
    } finally {
      setPending(null);
    }
  };

  const notional = Number(quantity) * (price ?? 0);

  return (
    <div className="flex flex-wrap items-center gap-2 border border-edge bg-panel px-2 py-2">
      <span className="panel-title">Ticket</span>
      <input
        aria-label="Trade ticker"
        value={ticker}
        onChange={(event) => setTicker(event.target.value.toUpperCase())}
        placeholder="SYM"
        className="w-24 border border-edge bg-base px-2 py-1 uppercase tracking-wider outline-none focus:border-primary"
      />
      <input
        aria-label="Trade quantity"
        value={quantity}
        onChange={(event) => setQuantity(event.target.value)}
        inputMode="decimal"
        placeholder="QTY"
        className="w-20 border border-edge bg-base px-2 py-1 text-right tabular-nums outline-none focus:border-primary"
      />
      <span className="tabular-nums text-slate">
        @ {price != null ? money(price) : "mkt"}
        {price != null && notional > 0 && (
          <span className="ml-2 text-ink">≈ {money(notional)}</span>
        )}
      </span>

      <div className="ml-auto flex gap-2">
        <button
          onClick={() => void submit("buy")}
          disabled={pending !== null}
          className="border border-up/60 bg-up/15 px-4 py-1 font-semibold tracking-widest text-up transition hover:bg-up/25 disabled:opacity-40"
        >
          {pending === "buy" ? "…" : "BUY"}
        </button>
        <button
          onClick={() => void submit("sell")}
          disabled={pending !== null}
          className="border border-down/60 bg-down/15 px-4 py-1 font-semibold tracking-widest text-down transition hover:bg-down/25 disabled:opacity-40"
        >
          {pending === "sell" ? "…" : "SELL"}
        </button>
      </div>

      {status && (
        <span
          role="status"
          className={`w-full ${status.ok ? "text-up" : "text-down"}`}
        >
          {status.text}
        </span>
      )}
    </div>
  );
}
