"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Panel } from "./Panel";
import type { SparkPoint } from "@/hooks/useMarketStream";
import { money, num, pct, toneClass } from "@/lib/format";

interface MainChartProps {
  ticker: string | null;
  points: SparkPoint[];
  price: number | null;
  changePct: number | null;
}

const timeLabel = (t: number) =>
  new Date(t).toLocaleTimeString("en-US", {
    hour12: false,
    minute: "2-digit",
    second: "2-digit",
  });

export function MainChart({ ticker, points, price, changePct }: MainChartProps) {
  const up = (changePct ?? 0) >= 0;
  const stroke = up ? "var(--color-up)" : "var(--color-down)";
  const values = points.map((p) => p.p);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;
  const pad = (max - min || max * 0.01 || 1) * 0.12;

  return (
    <Panel
      title={ticker ? `Chart · ${ticker}` : "Chart"}
      actions={
        ticker && (
          <div className="flex items-baseline gap-3">
            <span className="text-[15px] tabular-nums text-ink">
              {num(price)}
            </span>
            <span className={`tabular-nums ${toneClass(changePct)}`}>
              {pct(changePct)}
            </span>
          </div>
        )
      }
      bodyClassName="p-1"
    >
      {points.length < 2 ? (
        <div className="flex h-full items-center justify-center text-slate">
          {ticker
            ? "Accumulating live ticks…"
            : "Select a ticker from the watchlist"}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="mainFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
                <stop offset="100%" stopColor={stroke} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--color-edge-soft)" vertical={false} />
            <XAxis
              dataKey="t"
              tickFormatter={timeLabel}
              stroke="var(--color-slate)"
              tick={{ fontSize: 10 }}
              minTickGap={40}
            />
            <YAxis
              domain={[min - pad, max + pad]}
              orientation="right"
              width={58}
              stroke="var(--color-slate)"
              tick={{ fontSize: 10 }}
              tickFormatter={(v: number) => v.toFixed(2)}
            />
            <Tooltip
              contentStyle={{
                background: "var(--color-raised)",
                border: "1px solid var(--color-edge)",
                fontSize: 11,
              }}
              labelFormatter={(t: number) => timeLabel(t)}
              formatter={(v: number) => [money(v), ticker ?? ""]}
            />
            <Area
              type="monotone"
              dataKey="p"
              stroke={stroke}
              strokeWidth={1.5}
              fill="url(#mainFill)"
              isAnimationActive={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
}
