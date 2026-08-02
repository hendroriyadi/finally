"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkline } from "./Sparkline";

interface WatchlistRowProps {
  ticker: string;
  price?: number;
  changePercent?: number;
  points: number[];
  removeControl?: React.ReactNode;
}

/**
 * A single watchlist row: ticker, live price (with flash), change %, and a
 * progressively-drawn sparkline. Column widths never shift once price/
 * change/sparkline data arrives, because the em-dash and empty-cell
 * fallbacks below occupy the same layout the populated state does.
 */
export function WatchlistRow({ ticker, price, changePercent, points, removeControl }: WatchlistRowProps) {
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
    <div className="group flex h-9 items-center border-b border-edge px-2 hover:border-l-2 hover:border-l-accent hover:bg-panel">
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
      <div className="flex w-[60px] items-center justify-end">{removeControl}</div>
    </div>
  );
}
