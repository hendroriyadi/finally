"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkline } from "./Sparkline";

interface WatchlistRowProps {
  ticker: string;
  price?: number;
  changePercent?: number;
  points: number[];
  removeControl?: React.ReactNode;
  selected: boolean;
  onSelect: () => void;
}

/**
 * A single watchlist row: ticker, live price (with flash), change %, and a
 * progressively-drawn sparkline. Column widths never shift once price/
 * change/sparkline data arrives, because the em-dash and empty-cell
 * fallbacks below occupy the same layout the populated state does.
 *
 * The ticker/price/change/sparkline region is its own `<button>` (loads
 * `ticker` into the detail chart) as a sibling of the remove control, not
 * an ancestor of it — nesting the remove `<button>` inside a row-level
 * `role="button"` element would be an invalid/confusing interactive-in-
 * interactive nesting for screen readers and keyboard `Tab` order.
 */
export function WatchlistRow({
  ticker,
  price,
  changePercent,
  points,
  removeControl,
  selected,
  onSelect,
}: WatchlistRowProps) {
  const [flash, setFlash] = useState<"up" | "down" | null>(null);
  const previousPriceRef = useRef<number | undefined>(undefined);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (price === undefined) {
      return;
    }

    const previous = previousPriceRef.current;
    previousPriceRef.current = price;

    if (previous !== undefined && price !== previous) {
      // Clear any in-flight fade timer first so rapid consecutive ticks
      // restart the fade instead of stacking overlapping timers.
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
      setFlash(price > previous ? "up" : "down");
      timerRef.current = setTimeout(() => {
        setFlash(null);
        timerRef.current = null;
      }, 500);
    }

    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [price]);

  // CHG% is coloured by the sign of the session-baseline change percent
  // itself (not the tick-to-tick `direction`), per the plan's operative
  // definition — 0.00% on the very first tick renders as neutral text.
  const changeColor =
    changePercent === undefined || changePercent === 0
      ? "text-[#e6edf3]"
      : changePercent > 0
        ? "text-positive"
        : "text-destructive";

  const flashClass = flash === "up" ? "bg-positive/20" : flash === "down" ? "bg-destructive/20" : "";

  return (
    <div
      className={`group flex h-9 items-center border-b border-edge border-l-2 px-2 hover:bg-panel ${
        selected ? "border-l-accent" : "border-l-transparent hover:border-l-accent"
      }`}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected ? "true" : undefined}
        className="flex flex-1 cursor-pointer items-center text-left"
      >
        <div className="flex-1 text-xs font-semibold leading-tight text-primary">{ticker}</div>
        <div
          className={`w-24 text-right text-base font-semibold leading-tight tabular-nums transition-colors duration-500 ${flashClass}`}
        >
          {price !== undefined ? price.toFixed(2) : "—"}
        </div>
        <div className={`w-20 text-right text-sm font-normal leading-normal ${changeColor}`}>
          {changePercent !== undefined ? `${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%` : ""}
        </div>
        <div className="flex h-5 w-[60px] items-center justify-end">
          <Sparkline points={points} />
        </div>
      </button>
      <div className="flex w-[60px] items-center justify-end">{removeControl}</div>
    </div>
  );
}
