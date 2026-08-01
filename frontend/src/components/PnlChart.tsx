"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Panel } from "./Panel";
import { money } from "@/lib/format";
import type { Snapshot } from "@/lib/types";

interface PnlChartProps {
  history: Snapshot[];
  liveValue: number;
}

const timeLabel = (t: number) =>
  new Date(t).toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  });

export function PnlChart({ history, liveValue }: PnlChartProps) {
  const data = history
    .map((snap) => ({ t: snap.recorded_at, v: snap.total_value }))
    .sort((a, b) => a.t - b.t);

  if (data.length > 0 && liveValue > 0) {
    data.push({ t: Date.now(), v: liveValue });
  }

  const first = data[0]?.v ?? 0;
  const last = data[data.length - 1]?.v ?? 0;
  const stroke = last >= first ? "var(--color-up)" : "var(--color-down)";

  return (
    <Panel title="Portfolio Value" bodyClassName="p-1">
      {data.length < 2 ? (
        <div className="flex h-full items-center justify-center text-slate">
          Awaiting portfolio snapshots…
        </div>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--color-edge-soft)" vertical={false} />
            <XAxis
              dataKey="t"
              tickFormatter={timeLabel}
              stroke="var(--color-slate)"
              tick={{ fontSize: 10 }}
              minTickGap={40}
            />
            <YAxis
              orientation="right"
              width={62}
              domain={["auto", "auto"]}
              stroke="var(--color-slate)"
              tick={{ fontSize: 10 }}
              tickFormatter={(v: number) => v.toFixed(0)}
            />
            <Tooltip
              contentStyle={{
                background: "var(--color-raised)",
                border: "1px solid var(--color-edge)",
                fontSize: 11,
              }}
              labelFormatter={(t: number) => timeLabel(t)}
              formatter={(v: number) => [money(v), "Total"]}
            />
            <Line
              type="monotone"
              dataKey="v"
              stroke={stroke}
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
}
