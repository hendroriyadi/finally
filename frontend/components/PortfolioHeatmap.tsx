"use client";

import { ResponsiveContainer, Tooltip, Treemap } from "recharts";
import { usePortfolioContext } from "@/components/PortfolioProvider";
import { usePriceStreamContext } from "@/components/PriceStreamProvider";

const SKELETON_HEIGHT = 280;

interface HeatmapEntry {
  name: string;
  marketValue: number;
  pnlPercent: number;
  maxAbsPnlPercent: number;
}

interface HeatmapCellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  pnlPercent?: number;
  maxAbsPnlPercent?: number;
}

interface HeatmapTooltipPayloadItem {
  payload?: { name?: string; marketValue?: number; pnlPercent?: number };
}

// A cell too small for its on-cell label (HeatmapCell's showLabel/showPnl
// thresholds below) would otherwise expose zero information — no name, no
// value — with color as the only signal. This tooltip makes every cell's
// ticker/market value/P&L discoverable on hover regardless of rendered size.
function HeatmapTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: HeatmapTooltipPayloadItem[];
}) {
  if (!active || !payload || payload.length === 0) {
    return null;
  }
  const node = payload[0]?.payload;
  if (!node || node.name === undefined) {
    return null;
  }
  const pnlPercent = node.pnlPercent ?? 0;
  return (
    <div className="rounded border border-edge bg-panel px-3 py-2 text-sm">
      <div className="font-semibold text-primary">{node.name}</div>
      <div className="tabular-nums">${(node.marketValue ?? 0).toFixed(2)}</div>
      <div className={`tabular-nums ${pnlPercent > 0 ? "text-positive" : pnlPercent < 0 ? "text-destructive" : ""}`}>
        {`${pnlPercent >= 0 ? "+" : ""}${pnlPercent.toFixed(2)}%`}
      </div>
    </div>
  );
}

function HeatmapCell({ x = 0, y = 0, width = 0, height = 0, name = "", pnlPercent = 0, maxAbsPnlPercent = 1 }: HeatmapCellProps) {
  const isNeutral = pnlPercent === 0;
  const fill = isNeutral ? "#30363d" : pnlPercent > 0 ? "#22c55e" : "#ef4444";
  const fillOpacity = isNeutral
    ? 1
    : 0.45 + Math.min(1, Math.abs(pnlPercent) / maxAbsPnlPercent) * 0.55;
  const labelColor = isNeutral ? "#e6edf3" : "#ffffff";
  const showLabel = width >= 44 && height >= 20;
  const showPnl = height >= 38;

  return (
    <g>
      <rect
        x={x + 1}
        y={y + 1}
        width={Math.max(0, width - 2)}
        height={Math.max(0, height - 2)}
        fill={fill}
        fillOpacity={fillOpacity}
      />
      {showLabel && (
        <text x={x + 5} y={y + 16} fontSize={12} fontWeight={600} fill={labelColor}>
          {name}
        </text>
      )}
      {showLabel && showPnl && (
        <text x={x + 5} y={y + 30} fontSize={12} fontWeight={600} fill={labelColor}>
          {`${pnlPercent >= 0 ? "+" : ""}${pnlPercent.toFixed(2)}%`}
        </text>
      )}
    </g>
  );
}

/**
 * Portfolio heatmap: one rectangle per open position, sized by share of total
 * position market value and coloured by unrealized P&L sign/magnitude. Issues
 * no request of its own — it reads `positions`/`loading`/`error` from
 * `PortfolioProvider` and live prices from `PriceStreamProvider`, the same
 * two sources `PositionsTable` reads, so the two surfaces can never disagree.
 */
export function PortfolioHeatmap() {
  const { positions, loading, error } = usePortfolioContext();
  const { prices } = usePriceStreamContext();

  const entries: HeatmapEntry[] = positions
    .map((p) => {
      // A treemap cell must have a strictly positive size or Recharts'
      // squarify layout degenerates — unlike PositionsTable (which shows an
      // em-dash on a missing price), the fallback chain here ends at
      // avg_cost, never at null or zero.
      const livePrice = prices[p.ticker]?.price ?? p.current_price ?? p.avg_cost;
      const marketValue = p.quantity * livePrice;
      const pnlPercent = p.avg_cost === 0 ? 0 : ((livePrice - p.avg_cost) / p.avg_cost) * 100;
      return { name: p.ticker, marketValue, pnlPercent, maxAbsPnlPercent: 1 };
    })
    .filter((entry) => Number.isFinite(entry.marketValue) && entry.marketValue > 0);

  // Several positions bought moments ago can all sit at exactly 0% P&L,
  // which would otherwise divide by zero and produce NaN opacities across
  // every cell — the same guard Sparkline carries for a flat series.
  const maxAbsPnlPercent = Math.max(0, ...entries.map((e) => Math.abs(e.pnlPercent))) || 1;
  const data = entries.map((entry) => ({ ...entry, maxAbsPnlPercent }));

  return (
    <section className="rounded-md border border-edge bg-panel">
      <div className="border-b border-edge px-4 py-3">
        <h2 className="text-xl font-semibold leading-tight">Portfolio Heatmap</h2>
      </div>

      <div className="p-4">
        {error ? (
          <div className="text-sm font-normal leading-normal text-destructive">
            {"Couldn't load your positions — check your connection and reload."}
          </div>
        ) : loading ? (
          <div className="w-full animate-pulse rounded bg-edge" style={{ height: SKELETON_HEIGHT }} />
        ) : data.length === 0 ? (
          <div className="py-6">
            <h3 className="text-xl font-semibold leading-tight">No open positions</h3>
            <p className="mt-1 text-sm font-normal leading-normal text-[#8b949e]">
              Your portfolio heatmap will appear once you hold a position.
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={SKELETON_HEIGHT}>
            <Treemap
              data={data}
              dataKey="marketValue"
              stroke="none"
              isAnimationActive={false}
              content={<HeatmapCell />}
            >
              <Tooltip content={<HeatmapTooltip />} />
            </Treemap>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
