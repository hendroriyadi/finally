"use client";

import { useMemo, useState } from "react";
import { ChatPanel } from "./ChatPanel";
import { Header } from "./Header";
import { Heatmap } from "./Heatmap";
import { MainChart } from "./MainChart";
import { PnlChart } from "./PnlChart";
import { PositionsTable } from "./PositionsTable";
import { TradeBar } from "./TradeBar";
import { Watchlist, type WatchRow } from "./Watchlist";
import { useChat } from "@/hooks/useChat";
import { useTerminal } from "@/hooks/useTerminal";

export function Terminal() {
  const {
    prices,
    sparklines,
    connection,
    watchlist,
    portfolio,
    history,
    selected,
    error,
    select,
    refresh,
    trade,
    addTicker,
    removeTicker,
  } = useTerminal();
  const chat = useChat(refresh);
  const [chatCollapsed, setChatCollapsed] = useState(false);

  const rows = useMemo<WatchRow[]>(
    () =>
      watchlist.map((entry) => {
        const tick = prices[entry.ticker];
        const spark = sparklines[entry.ticker] ?? [];
        const price = tick?.price ?? entry.price ?? null;
        // The backend's change_percent is tick-over-tick, so it reads ~0.00%.
        // Change since page load is the meaningful number and matches the sparkline.
        const sessionPct =
          spark.length > 1 && spark[0].p !== 0
            ? ((spark[spark.length - 1].p - spark[0].p) / spark[0].p) * 100
            : null;
        return {
          ticker: entry.ticker,
          price,
          changePct: sessionPct ?? entry.change_pct ?? tick?.change_pct ?? null,
          spark,
        };
      }),
    [watchlist, prices, sparklines],
  );

  const selectedRow = rows.find((row) => row.ticker === selected) ?? null;
  const selectedPrice =
    selectedRow?.price ??
    (selected ? (prices[selected]?.price ?? null) : null);

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Header
        totalValue={portfolio.total_value}
        cash={portfolio.cash_balance}
        pnl={portfolio.unrealized_pnl}
        pnlPct={portfolio.unrealized_pnl_pct}
        connection={connection}
      />

      {error && (
        <div className="border-b border-down/40 bg-down/10 px-4 py-1 text-down">
          {error} — retrying automatically.
        </div>
      )}

      <main className="flex min-h-0 flex-1 gap-1.5 p-1.5">
        <div className="flex w-[300px] shrink-0 flex-col">
          <Watchlist
            rows={rows}
            selected={selected}
            onSelect={select}
            onAdd={addTicker}
            onRemove={removeTicker}
          />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="min-h-0 flex-[5]">
            <MainChart
              ticker={selected}
              points={selected ? (sparklines[selected] ?? []) : []}
              price={selectedPrice}
              changePct={selectedRow?.changePct ?? null}
            />
          </div>

          <div className="flex min-h-0 flex-[3] gap-1.5">
            <div className="min-w-0 flex-1">
              <Heatmap positions={portfolio.positions} />
            </div>
            <div className="min-w-0 flex-1">
              <PnlChart history={history} liveValue={portfolio.total_value} />
            </div>
          </div>

          <div className="min-h-0 flex-[3]">
            <PositionsTable positions={portfolio.positions} onSelect={select} />
          </div>

          <TradeBar
            defaultTicker={selected}
            price={selectedPrice}
            onTrade={trade}
          />
        </div>

        <ChatPanel
          messages={chat.messages}
          pending={chat.pending}
          collapsed={chatCollapsed}
          onToggle={() => setChatCollapsed((value) => !value)}
          onSend={chat.send}
        />
      </main>
    </div>
  );
}
