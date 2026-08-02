"use client";

import { useEffect, useState } from "react";
import { fetchWatchlist } from "@/lib/api";
import type { WatchlistItem } from "@/lib/types";
import { usePriceStreamContext } from "./PriceStreamProvider";
import { AddTickerForm } from "./AddTickerForm";
import { WatchlistRow } from "./WatchlistRow";

const SKELETON_ROW_COUNT = 10;

/**
 * Watchlist grid: owns the fetch-on-mount lifecycle and every grid state
 * (loading skeleton, error, empty, populated, bounded-overflow scroll). Price,
 * change %, and sparkline data come from the shared SSE stream context, not a
 * re-fetch of the watchlist — the REST list and the price stream are separate
 * concerns, and a ticker present in the stream but not in the watchlist is
 * never rendered.
 */
export function WatchlistPanel() {
  const [items, setItems] = useState<WatchlistItem[] | null>(null);
  const [error, setError] = useState(false);
  const { prices, history, baselines } = usePriceStreamContext();

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

  function addItem(item: WatchlistItem) {
    setItems((current) => [...(current ?? []), item]);
  }

  return (
    <section className="rounded-md border border-edge bg-panel">
      <div className="border-b border-edge px-4 py-3">
        <h2 className="text-xl font-semibold leading-tight">Watchlist</h2>
        <div className="mt-2">
          <AddTickerForm onAdded={addItem} />
        </div>
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
          items.map((item) => {
            const baseline = baselines[item.ticker];
            const price = prices[item.ticker]?.price;
            const changePercent =
              baseline !== undefined && price !== undefined ? ((price - baseline) / baseline) * 100 : undefined;

            return (
              <WatchlistRow
                key={item.ticker}
                ticker={item.ticker}
                price={price}
                changePercent={changePercent}
                direction={prices[item.ticker]?.direction}
                points={history[item.ticker] ?? []}
              />
            );
          })
        )}
      </div>
    </section>
  );
}
