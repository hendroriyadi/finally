"use client";

import { useState, type FormEvent } from "react";
import { Panel } from "./Panel";
import { PriceCell } from "./PriceCell";
import { Sparkline } from "./Sparkline";
import type { SparkPoint } from "@/hooks/useMarketStream";
import { pct, toneClass } from "@/lib/format";

export interface WatchRow {
  ticker: string;
  price: number | null;
  changePct: number | null;
  spark: SparkPoint[];
}

interface WatchlistProps {
  rows: WatchRow[];
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => void | Promise<void>;
  onRemove: (ticker: string) => void | Promise<void>;
}

export function Watchlist({
  rows,
  selected,
  onSelect,
  onAdd,
  onRemove,
}: WatchlistProps) {
  const [draft, setDraft] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const ticker = draft.trim().toUpperCase();
    if (!ticker) return;
    setDraft("");
    await onAdd(ticker);
  };

  return (
    <Panel title={`Watchlist · ${rows.length}`} bodyClassName="flex flex-col">
      <form onSubmit={submit} className="flex gap-1 border-b border-edge p-1.5">
        <input
          aria-label="Add ticker"
          placeholder="ADD TICKER"
          value={draft}
          onChange={(event) => setDraft(event.target.value.toUpperCase())}
          className="min-w-0 flex-1 border border-edge bg-base px-1.5 py-1 uppercase tracking-wider text-ink outline-none placeholder:text-slate/60 focus:border-primary"
        />
        <button
          type="submit"
          className="border border-edge bg-raised px-2 text-accent hover:border-accent"
        >
          +
        </button>
      </form>

      <div className="flex-1 overflow-y-auto">
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10 bg-panel">
            <tr className="panel-title border-b border-edge">
              <th className="px-2 py-1 text-left font-normal">Sym</th>
              <th className="px-1 py-1 text-right font-normal">Last</th>
              <th className="px-1 py-1 text-right font-normal">Chg%</th>
              <th className="px-1 py-1 text-right font-normal">Trend</th>
              <th className="w-5" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const active = row.ticker === selected;
              return (
                <tr
                  key={row.ticker}
                  data-testid={`watch-row-${row.ticker}`}
                  data-selected={active || undefined}
                  onClick={() => onSelect(row.ticker)}
                  className={`group cursor-pointer border-b border-edge-soft hover:bg-raised/70 ${
                    active ? "bg-raised" : ""
                  }`}
                >
                  <td
                    className={`px-2 py-1 font-semibold ${
                      active ? "text-accent" : "text-ink"
                    }`}
                  >
                    {active && (
                      <span className="mr-1 text-accent" aria-hidden>
                        ▸
                      </span>
                    )}
                    {row.ticker}
                  </td>
                  <td className="py-1 text-right">
                    <PriceCell price={row.price} />
                  </td>
                  <td
                    className={`px-1 py-1 text-right tabular-nums ${toneClass(
                      row.changePct,
                    )}`}
                  >
                    {pct(row.changePct)}
                  </td>
                  <td className="px-1 py-1 text-right align-middle">
                    <div className="flex justify-end">
                      <Sparkline
                        points={row.spark}
                        positive={(row.changePct ?? 0) >= 0}
                      />
                    </div>
                  </td>
                  <td className="pr-1">
                    <button
                      aria-label={`Remove ${row.ticker}`}
                      onClick={(event) => {
                        event.stopPropagation();
                        void onRemove(row.ticker);
                      }}
                      className="text-slate opacity-0 transition hover:text-down group-hover:opacity-100"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-2 py-6 text-center text-slate">
                  No tickers watched
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
