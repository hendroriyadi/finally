"use client";

import { ResponsiveContainer, Treemap } from "recharts";
import { Panel } from "./Panel";
import { pct } from "@/lib/format";
import type { LivePosition } from "@/lib/portfolio";

interface HeatmapProps {
  positions: LivePosition[];
}

interface TileProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  pnlPct?: number;
}

/** Saturation scales with |P&L%|, capping at 5% so small moves stay readable. */
function tileColor(pnlPct: number): string {
  const intensity = Math.min(Math.abs(pnlPct) / 5, 1);
  const hue = pnlPct >= 0 ? "var(--color-up)" : "var(--color-down)";
  const mix = 14 + intensity * 56;
  return `color-mix(in srgb, ${hue} ${mix}%, var(--color-panel))`;
}

function Tile({ x = 0, y = 0, width = 0, height = 0, name, pnlPct = 0 }: TileProps) {
  const showLabel = width > 44 && height > 24;
  const showPct = width > 54 && height > 40;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={tileColor(pnlPct)}
        stroke="var(--color-base)"
        strokeWidth={2}
      />
      {showLabel && (
        <text
          x={x + width / 2}
          y={y + height / 2 - (showPct ? 6 : 0)}
          textAnchor="middle"
          dominantBaseline="middle"
          fill="var(--color-ink)"
          fontSize={12}
          fontWeight={600}
        >
          {name}
        </text>
      )}
      {showPct && (
        <text
          x={x + width / 2}
          y={y + height / 2 + 10}
          textAnchor="middle"
          dominantBaseline="middle"
          fill={pnlPct >= 0 ? "var(--color-up)" : "var(--color-down)"}
          fontSize={11}
        >
          {pct(pnlPct)}
        </text>
      )}
    </g>
  );
}

export function Heatmap({ positions }: HeatmapProps) {
  const data = positions
    .filter((p) => p.market_value > 0)
    .map((p) => ({
      name: p.ticker,
      size: p.market_value,
      pnlPct: p.unrealized_pnl_pct,
    }));

  return (
    <Panel title="Portfolio Heatmap" bodyClassName="p-1">
      {data.length === 0 ? (
        <div className="flex h-full items-center justify-center text-slate">
          No open positions
        </div>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={data}
            dataKey="size"
            isAnimationActive={false}
            content={<Tile />}
          />
        </ResponsiveContainer>
      )}
    </Panel>
  );
}
