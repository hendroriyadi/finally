"use client";

import { ConnectionStatusDot } from "@/components/ConnectionStatusDot";
import { usePriceStreamContext } from "@/components/PriceStreamProvider";
import { usePortfolioContext } from "@/components/PortfolioProvider";

/**
 * Terminal header bar: app title on the left; total portfolio value and cash
 * balance (both read straight from the shared `PortfolioProvider` context,
 * never recomputed or fetched here) alongside the connection-status dot on
 * the right. `totalValue` is already derived in the provider's render body
 * from the live SSE price map, so it re-renders on every frame for free —
 * computing it a second time here would let this header and the positions
 * table disagree during a refresh.
 */
export function AppHeader() {
  const { status } = usePriceStreamContext();
  const { totalValue, cashBalance, loading, error } = usePortfolioContext();

  return (
    <header className="flex items-center justify-between border-b border-edge bg-panel px-8 py-4">
      <h1 className="text-xl font-semibold leading-tight">FinAlly</h1>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="text-xs font-semibold leading-tight text-[#8b949e]">PORTFOLIO VALUE</div>
          <div className="text-base font-semibold leading-tight tabular-nums">
            {loading || error ? "—" : totalValue.toFixed(2)}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs font-semibold leading-tight text-[#8b949e]">CASH</div>
          <div className="text-base font-semibold leading-tight tabular-nums">
            {loading || error ? "—" : cashBalance.toFixed(2)}
          </div>
        </div>
        <ConnectionStatusDot status={status} />
      </div>
    </header>
  );
}
