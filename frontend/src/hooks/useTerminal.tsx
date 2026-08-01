"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "@/lib/api";
import { derivePortfolio, type LivePortfolio } from "@/lib/portfolio";
import { useMarketStream, type SparkPoint } from "@/hooks/useMarketStream";
import type {
  ConnectionState,
  Portfolio,
  PriceTick,
  Side,
  Snapshot,
  WatchlistEntry,
} from "@/lib/types";

interface TerminalValue {
  prices: Record<string, PriceTick>;
  sparklines: Record<string, SparkPoint[]>;
  connection: ConnectionState;
  watchlist: WatchlistEntry[];
  portfolio: LivePortfolio;
  history: Snapshot[];
  selected: string | null;
  ready: boolean;
  error: string | null;
  select: (ticker: string) => void;
  refresh: () => Promise<void>;
  trade: (ticker: string, quantity: number, side: Side) => Promise<void>;
  addTicker: (ticker: string) => Promise<void>;
  removeTicker: (ticker: string) => Promise<void>;
}

const TerminalContext = createContext<TerminalValue | null>(null);

const HISTORY_POLL_MS = 30_000;

export function TerminalProvider({ children }: { children: ReactNode }) {
  const { prices, sparklines, connection } = useMarketStream();
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [raw, setRaw] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [wl, pf, hist] = await Promise.all([
        api.getWatchlist(),
        api.getPortfolio(),
        api.getHistory(),
      ]);
      setWatchlist(wl);
      setRaw(pf);
      setHistory(hist);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backend unavailable");
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), HISTORY_POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!selected && watchlist.length > 0) setSelected(watchlist[0].ticker);
  }, [watchlist, selected]);

  const portfolio = useMemo(() => derivePortfolio(raw, prices), [raw, prices]);

  const trade = useCallback(
    async (ticker: string, quantity: number, side: Side) => {
      await api.trade(ticker.trim().toUpperCase(), quantity, side);
      await refresh();
    },
    [refresh],
  );

  const addTicker = useCallback(
    async (ticker: string) => {
      await api.addTicker(ticker.trim().toUpperCase());
      await refresh();
    },
    [refresh],
  );

  const removeTicker = useCallback(
    async (ticker: string) => {
      await api.removeTicker(ticker);
      setSelected((current) => (current === ticker ? null : current));
      await refresh();
    },
    [refresh],
  );

  const value: TerminalValue = {
    prices,
    sparklines,
    connection,
    watchlist,
    portfolio,
    history,
    selected,
    ready,
    error,
    select: setSelected,
    refresh,
    trade,
    addTicker,
    removeTicker,
  };

  return (
    <TerminalContext.Provider value={value}>{children}</TerminalContext.Provider>
  );
}

export function useTerminal(): TerminalValue {
  const ctx = useContext(TerminalContext);
  if (!ctx) throw new Error("useTerminal must be used inside TerminalProvider");
  return ctx;
}
