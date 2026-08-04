"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatCurrency } from "@/lib/format";
import { usePriceStreamContext } from "@/components/PriceStreamProvider";

/**
 * Full-width per-ticker price-history panel. Reads the shared per-ticker
 * accumulator `usePriceStream` already maintains for the watchlist
 * sparklines (`history[ticker]`) — opens no `EventSource` and issues no
 * request of its own; the provider owns the one connection, and this panel
 * is simply its second, larger reader.
 */
export function DetailChart({ ticker }: { ticker: string | null }) {
  const { history } = usePriceStreamContext();
  const points = ticker ? (history[ticker] ?? []) : [];
  const chartData = points.map((price, index) => ({ index, price }));

  return (
    <section className="rounded-md border border-edge bg-panel">
      <div className="border-b border-edge px-4 py-3">
        <h2 className="text-xl font-semibold leading-tight">
          {ticker ? `${ticker} Price History` : "No ticker selected"}
        </h2>
      </div>

      <div className="p-4">
        {ticker === null ? (
          <div className="py-6">
            <p className="mt-1 text-sm font-normal leading-normal text-[#8b949e]">
              Click a ticker in the watchlist to load its price history here.
            </p>
          </div>
        ) : points.length < 2 ? (
          <div className="flex h-[320px] w-full items-center">
            <div className="h-px w-full bg-[#209dd7] opacity-40" />
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="#30363d" strokeDasharray="0" vertical={false} />
              <XAxis dataKey="index" hide />
              <YAxis
                stroke="#8b949e"
                fontSize={12}
                tickLine={false}
                domain={["auto", "auto"]}
                tickFormatter={formatCurrency}
              />
              <Tooltip
                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #30363d" }}
                labelFormatter={() => ""}
                formatter={(value) => formatCurrency(Number(value))}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke="#209dd7"
                strokeWidth={2}
                fill="#209dd7"
                fillOpacity={0.1}
                dot={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
