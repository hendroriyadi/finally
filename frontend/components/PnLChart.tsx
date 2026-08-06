"use client";

import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchPortfolioHistory } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import type { PortfolioHistoryPoint } from "@/lib/types";
import { usePortfolioContext } from "@/components/PortfolioProvider";

// The backend records a snapshot every 30 seconds (Plan 03-01). Polling at
// half that interval means a displayed series is never more than one
// recording behind, and a slower poll would visibly lag the header's live
// total sitting above this chart.
export const PNL_POLL_INTERVAL_MS = 15000;

function formatClockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/**
 * Portfolio value over time, drawn from `GET /api/portfolio/history`. The
 * only new fetch this phase adds — the treemap beside it reads shared
 * context instead. Polls on an interval keyed on `cashBalance` rather than
 * subscribing to the SSE price stream: a trade always moves cash, and
 * `PortfolioProvider` already refetches after every fill, so re-running this
 * effect on a `cashBalance` change is what picks up the point the trade
 * route just recorded, without waiting for the next poll tick.
 */
export function PnLChart() {
  const [points, setPoints] = useState<PortfolioHistoryPoint[] | null>(null);
  const [error, setError] = useState(false);
  const { cashBalance } = usePortfolioContext();

  useEffect(() => {
    let cancelled = false;

    function load() {
      fetchPortfolioHistory()
        .then((history) => {
          if (!cancelled) {
            setPoints(history);
            setError(false);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            console.error("PnLChart: failed to load portfolio history", err);
            setError(true);
          }
        });
    }

    // Fires once on mount, then again shortly after when PortfolioProvider's
    // own fetch resolves and cashBalance updates from its 0 default to the
    // real value — a harmless extra GET on every page load, accepted rather
    // than added complexity to distinguish "provider's initial settle" from
    // "a real trade changed cash" (both cases legitimately want a refetch).
    load();
    const interval = setInterval(load, PNL_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [cashBalance]);

  return (
    <section className="rounded-md border border-edge bg-panel">
      <div className="border-b border-edge px-4 py-3">
        <h2 className="text-xl font-semibold leading-tight">Portfolio Value</h2>
      </div>

      <div className="p-4">
        {error ? (
          <div className="text-sm font-normal leading-normal text-destructive">
            {"Couldn't load portfolio history — check your connection and reload."}
          </div>
        ) : points === null ? (
          <div className="h-[220px] w-full animate-pulse rounded bg-edge" />
        ) : points.length === 0 ? (
          <div className="py-6">
            <h3 className="text-xl font-semibold leading-tight">No portfolio history yet</h3>
            <p className="mt-1 text-sm font-normal leading-normal text-[#8b949e]">
              Value snapshots are recorded every 30 seconds — check back shortly, or make a trade to
              record one immediately.
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={points} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="#30363d" strokeDasharray="0" vertical={false} />
              <XAxis
                dataKey="recorded_at"
                stroke="#8b949e"
                fontSize={12}
                tickLine={false}
                tickFormatter={formatClockTime}
              />
              <YAxis
                stroke="#8b949e"
                fontSize={12}
                tickLine={false}
                domain={["auto", "auto"]}
                tickFormatter={formatCurrency}
              />
              <Tooltip
                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #30363d" }}
                labelFormatter={(label) => formatClockTime(String(label))}
                formatter={(value) => formatCurrency(Number(value))}
              />
              <Area
                type="monotone"
                dataKey="total_value"
                stroke="#209dd7"
                strokeWidth={2}
                fill="#209dd7"
                fillOpacity={0.1}
                isAnimationActive={false}
                dot={points.length === 1 ? { r: 3, fill: "#209dd7", strokeWidth: 0 } : false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
