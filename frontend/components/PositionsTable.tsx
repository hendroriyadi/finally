"use client";

import { usePortfolioContext } from "@/components/PortfolioProvider";
import { usePriceStreamContext } from "@/components/PriceStreamProvider";

// Fewer than the watchlist's 10 skeleton rows — an empty portfolio is the
// common first-run case, and ten skeleton rows would promise content that is
// usually not coming.
const SKELETON_ROW_COUNT = 4;

function formatQuantity(quantity: number): string {
  // Trim trailing zeros so a whole-share position reads as "10", not
  // "10.000000", while still showing fractional-share precision (e.g. "0.5").
  return quantity.toFixed(6).replace(/\.?0+$/, "");
}

function formatCurrency(value: number): string {
  return value.toFixed(2);
}

function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

/**
 * Positions table: one row per open position. Every price-derived cell
 * (current price, unrealized P&L, percent change) is recomputed in the
 * render body from the shared SSE price map, never rendered from the
 * server's `unrealized_pnl`/`change_percent` snapshot fields, which can lag
 * the live price by up to one poll interval — showing a fresh price next to
 * a stale P&L would read as a bug even though both values were individually
 * correct.
 *
 * Structured as a near-mirror of `WatchlistPanel` — same panel shell, same
 * pinned column-header row, same bounded scroll container, same
 * error/loading/empty/populated branch ordering — so the two grids read as
 * one system. Issues no fetch of its own: `positions`/`loading`/`error` come
 * from `usePortfolioContext()` and live prices from `usePriceStreamContext()`.
 */
export function PositionsTable() {
  const { positions, loading, error } = usePortfolioContext();
  const { prices } = usePriceStreamContext();

  return (
    <section className="rounded-md border border-edge bg-panel">
      <div className="border-b border-edge px-4 py-3">
        <h2 className="text-xl font-semibold leading-tight">Positions</h2>
      </div>

      <div className="flex items-center border-b border-edge px-2 py-2 text-xs font-semibold leading-tight text-[#8b949e]">
        <div className="flex-1">TICKER</div>
        <div className="w-20 text-right">QTY</div>
        <div className="w-24 text-right">AVG COST</div>
        <div className="w-24 text-right">PRICE</div>
        <div className="w-24 text-right">P&L</div>
        <div className="w-20 text-right">CHG%</div>
      </div>

      <div className="max-h-[28rem] overflow-y-auto">
        {error ? (
          <div className="px-4 py-6 text-sm font-normal leading-normal text-destructive">
            {"Couldn't load your positions — check your connection and reload."}
          </div>
        ) : loading ? (
          <div>
            {Array.from({ length: SKELETON_ROW_COUNT }).map((_, index) => (
              <div key={index} className="flex h-9 items-center border-b border-edge px-2">
                <div className="h-4 w-32 flex-1 animate-pulse rounded bg-edge" />
              </div>
            ))}
          </div>
        ) : positions.length === 0 ? (
          <div className="px-4 py-6">
            <h3 className="text-xl font-semibold leading-tight">No open positions</h3>
            <p className="mt-1 text-sm font-normal leading-normal text-[#8b949e]">
              Buy shares from the trade bar above to get started.
            </p>
          </div>
        ) : (
          // Never filter zero-quantity rows out here — the trade engine
          // deletes a fully-sold position rather than zeroing it, so a
          // zero-quantity row arriving would be a real backend regression
          // that a defensive filter would hide instead of surface.
          positions.map((p) => {
            const livePrice = prices[p.ticker]?.price ?? p.current_price ?? null;
            const pnl = livePrice === null ? null : (livePrice - p.avg_cost) * p.quantity;
            const changePercent =
              livePrice === null || p.avg_cost === 0 ? null : ((livePrice - p.avg_cost) / p.avg_cost) * 100;

            const pnlColorClass =
              pnl === null || pnl === 0 ? "text-[#e6edf3]" : pnl > 0 ? "text-positive" : "text-destructive";

            return (
              <div key={p.ticker} className="flex h-9 items-center border-b border-edge px-2">
                <div className="flex-1 text-xs font-semibold leading-tight text-primary">{p.ticker}</div>
                <div className="w-20 text-right text-base font-semibold leading-tight tabular-nums">
                  {formatQuantity(p.quantity)}
                </div>
                <div className="w-24 text-right text-base font-semibold leading-tight tabular-nums">
                  {formatCurrency(p.avg_cost)}
                </div>
                <div className="w-24 text-right text-base font-semibold leading-tight tabular-nums">
                  {livePrice !== null ? formatCurrency(livePrice) : "—"}
                </div>
                <div
                  className={`w-24 text-right text-base font-semibold leading-tight tabular-nums ${pnlColorClass}`}
                >
                  {pnl !== null ? formatCurrency(pnl) : "—"}
                </div>
                <div
                  className={`w-20 text-right text-base font-semibold leading-tight tabular-nums ${pnlColorClass}`}
                >
                  {changePercent !== null ? formatPercent(changePercent) : "—"}
                </div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
