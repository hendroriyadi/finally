"use client";

import { Panel } from "./Panel";
import { PriceCell } from "./PriceCell";
import { money, pct, shares, signedMoney, toneClass } from "@/lib/format";
import type { LivePosition } from "@/lib/portfolio";

interface PositionsTableProps {
  positions: LivePosition[];
  onSelect: (ticker: string) => void;
}

export function PositionsTable({ positions, onSelect }: PositionsTableProps) {
  return (
    <Panel
      title={`Positions · ${positions.length}`}
      bodyClassName="overflow-auto"
    >
      <table className="w-full border-collapse">
        <thead className="sticky top-0 z-10 bg-panel">
          <tr className="panel-title border-b border-edge">
            <th className="px-2 py-1 text-left font-normal">Symbol</th>
            <th className="px-2 py-1 text-right font-normal">Qty</th>
            <th className="px-2 py-1 text-right font-normal">Avg Cost</th>
            <th className="px-2 py-1 text-right font-normal">Last</th>
            <th className="px-2 py-1 text-right font-normal">Mkt Value</th>
            <th className="px-2 py-1 text-right font-normal">Unrl P&L</th>
            <th className="px-2 py-1 text-right font-normal">%</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => (
            <tr
              key={position.ticker}
              data-testid={`position-row-${position.ticker}`}
              onClick={() => onSelect(position.ticker)}
              className="cursor-pointer border-b border-edge-soft hover:bg-raised/70"
            >
              <td className="px-2 py-1 font-semibold text-ink">
                {position.ticker}
              </td>
              <td className="px-2 py-1 text-right tabular-nums">
                {shares(position.quantity)}
              </td>
              <td className="px-2 py-1 text-right tabular-nums text-slate">
                {money(position.avg_cost)}
              </td>
              <td className="py-1 text-right">
                <PriceCell price={position.current_price} />
              </td>
              <td className="px-2 py-1 text-right tabular-nums">
                {money(position.market_value)}
              </td>
              <td
                className={`px-2 py-1 text-right tabular-nums ${toneClass(
                  position.unrealized_pnl,
                )}`}
              >
                {signedMoney(position.unrealized_pnl)}
              </td>
              <td
                className={`px-2 py-1 text-right tabular-nums ${toneClass(
                  position.unrealized_pnl_pct,
                )}`}
              >
                {pct(position.unrealized_pnl_pct)}
              </td>
            </tr>
          ))}
          {positions.length === 0 && (
            <tr>
              <td colSpan={7} className="px-2 py-8 text-center text-slate">
                No open positions — use the ticket below to buy
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Panel>
  );
}
