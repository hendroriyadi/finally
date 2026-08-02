"use client";

import { useEffect, useState } from "react";
import { fetchWatchlist } from "@/lib/api";
import type { WatchlistItem } from "@/lib/types";
import { WatchlistRow } from "./WatchlistRow";

const SKELETON_ROW_COUNT = 10;

/**
 * Watchlist grid: owns the fetch-on-mount lifecycle and every grid state
 * (loading skeleton, error, empty, populated, bounded-overflow scroll).
 * Price/change/sparkline are left unwired here — the SSE stream that fills
 * them arrives in Plan 03; until then every row shows the em-dash
 * placeholder specified by the UI-SPEC.
 */
export function WatchlistPanel() {
  const [items, setItems] = useState<WatchlistItem[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    fetchWatchlist()
      .then((tickers) => {
        if (!cancelled) {
          setItems(tickers);
          setError(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="rounded-md border border-edge bg-panel">
      <div className="border-b border-edge px-4 py-3">
        <h2 className="text-xl font-semibold leading-tight">Watchlist</h2>
      </div>

      <div className="flex items-center border-b border-edge px-2 py-2 text-xs font-semibold leading-tight text-[#8b949e]">
        <div className="flex-1">TICKER</div>
        <div className="w-24 text-right">PRICE</div>
        <div className="w-20 text-right">CHG%</div>
        <div className="w-[60px]" />
      </div>

      <div className="max-h-[28rem] overflow-y-auto">
        {error ? (
          <div className="px-4 py-6 text-sm font-normal leading-normal text-destructive">
            {"Couldn't load your watchlist — check your connection and reload."}
          </div>
        ) : items === null ? (
          <div>
            {Array.from({ length: SKELETON_ROW_COUNT }).map((_, index) => (
              <div key={index} className="flex h-9 items-center border-b border-edge px-2">
                <div className="h-4 w-32 flex-1 animate-pulse rounded bg-edge" />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="px-4 py-6">
            <h3 className="text-xl font-semibold leading-tight">Your watchlist is empty</h3>
            <p className="mt-1 text-sm font-normal leading-normal text-[#8b949e]">
              Add a ticker symbol above to start streaming live prices.
            </p>
          </div>
        ) : (
          items.map((item) => <WatchlistRow key={item.ticker} ticker={item.ticker} />)
        )}
      </div>
    </section>
  );
}
