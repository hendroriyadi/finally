import type { ReactNode } from "react";

interface WatchlistRowProps {
  ticker: string;
  price?: number;
  changePercent?: number;
  direction?: "up" | "down" | "flat";
  sparkline?: ReactNode;
}

/**
 * A single watchlist row: ticker, price, change %, and a sparkline slot.
 * Purely presentational — price/changePercent/sparkline are wired by the SSE
 * stream in Plan 03. Column widths never shift once those props are filled,
 * because the em-dash and empty-cell fallbacks below occupy the same layout.
 */
export function WatchlistRow({ ticker, price, changePercent, direction, sparkline }: WatchlistRowProps) {
  const changeColor =
    direction === "up" ? "text-positive" : direction === "down" ? "text-destructive" : "text-[#e6edf3]";

  return (
    <div className="group flex h-9 items-center border-b border-edge px-2 hover:border-l-2 hover:border-l-accent hover:bg-panel">
      <div className="flex-1 text-xs font-semibold leading-tight text-primary">{ticker}</div>
      <div className="w-24 text-right text-base font-semibold leading-tight tabular-nums">
        {price !== undefined ? price.toFixed(2) : "—"}
      </div>
      <div className={`w-20 text-right text-sm font-normal leading-normal ${changeColor}`}>
        {changePercent !== undefined ? `${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%` : ""}
      </div>
      <div className="flex h-5 w-[60px] items-center justify-end">{sparkline ?? null}</div>
    </div>
  );
}
