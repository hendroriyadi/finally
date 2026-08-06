"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { fetchPortfolio } from "@/lib/api";
import type { PortfolioSnapshot, Position } from "@/lib/types";
import { usePriceStreamContext } from "@/components/PriceStreamProvider";

/**
 * Light poll interval for refreshing cash/positions from the server. Only a
 * trade changes these values this phase, and a trade already triggers an
 * immediate `refresh()` — this interval exists solely to catch a change made
 * in another tab. Exported as a named constant so tuning it is a one-line
 * change.
 */
export const PORTFOLIO_POLL_INTERVAL_MS = 8000;

export interface PortfolioState {
  cashBalance: number;
  positions: Position[];
  totalValue: number;
  loading: boolean;
  error: boolean;
  refresh: () => Promise<void>;
}

const PortfolioContext = createContext<PortfolioState | null>(null);

/**
 * Opens the single shared portfolio fetch/poll loop for the whole page and
 * publishes it through context — mirroring `PriceStreamProvider`'s rationale:
 * the trade bar, the positions table, and the header are siblings, so none of
 * them can own this fetch without the others opening a duplicate.
 *
 * Cash and position quantities come from the server at a low cadence (this
 * poll interval, plus an immediate refresh after every trade). Total
 * portfolio value is deliberately NOT one of those polled/stored values — it
 * is recomputed in the render body below from `positions` and the live price
 * map, so it moves on every SSE tick without ever issuing a network request.
 */
export function PortfolioProvider({ children }: { children: ReactNode }) {
  const { prices } = usePriceStreamContext();

  const [cashBalance, setCashBalance] = useState(0);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const mountedRef = useRef(true);

  const applySnapshot = useCallback((snapshot: PortfolioSnapshot) => {
    setCashBalance(snapshot.cash_balance);
    setPositions(snapshot.positions);
    setError(false);
  }, []);

  // Public re-fetch used by callers outside this effect (e.g. the trade bar
  // after a fill). Awaiting this resolves only after state has been updated.
  const refresh = useCallback(async () => {
    try {
      const snapshot = await fetchPortfolio();
      if (!mountedRef.current) {
        return;
      }
      applySnapshot(snapshot);
    } catch (err) {
      if (!mountedRef.current) {
        return;
      }
      // Leave the last known good cashBalance/positions in place — a
      // transient fetch failure should not blank out what the user was
      // already looking at.
      console.error("PortfolioProvider: failed to refresh portfolio", err);
      setError(true);
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [applySnapshot]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Drive the fetch/poll lifecycle from one effect keyed on `applySnapshot`
  // only. `prices` must NOT appear in this dependency list — its identity
  // changes on every SSE frame (~500ms), so including it would turn this
  // light 8-second poll into roughly two fetches per second, which is
  // exactly the load pattern D-13 exists to avoid.
  //
  // Fetches are wired via `.then()/.catch()/.finally()` (mirroring
  // `WatchlistPanel`'s fetch-on-mount effect) rather than calling the
  // async `refresh()` above directly — calling an async function that
  // awaits before setting state reads, to the React Compiler's effect
  // linter, as "setState synchronously within an effect", even though the
  // actual state update is deferred past a network round trip. Routing the
  // same state update through `applySnapshot` inside a `.then()` callback
  // keeps that state update unambiguously async from the linter's view.
  useEffect(() => {
    let cancelled = false;

    function poll() {
      fetchPortfolio()
        .then((snapshot) => {
          if (!cancelled) {
            applySnapshot(snapshot);
          }
        })
        .catch((err) => {
          if (!cancelled) {
            console.error("PortfolioProvider: failed to refresh portfolio", err);
            setError(true);
          }
        })
        .finally(() => {
          if (!cancelled) {
            setLoading(false);
          }
        });
    }

    poll();
    const interval = setInterval(poll, PORTFOLIO_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [applySnapshot]);

  // Recomputed on every render — including every price-stream tick, since
  // `prices` (from context) gets a fresh object identity on each SSE frame —
  // with no additional network call. This render-body derivation, not a
  // fetch, is the mechanism that satisfies the live-total requirement (D-13).
  // When a held ticker is absent from the price map, its cost basis
  // (avg_cost) is used instead, so the holding keeps contributing to the
  // total rather than dropping out or producing NaN.
  const totalValue =
    cashBalance +
    positions.reduce((sum, p) => sum + p.quantity * (prices[p.ticker]?.price ?? p.avg_cost), 0);

  const value: PortfolioState = {
    cashBalance,
    positions,
    totalValue,
    loading,
    error,
    refresh,
  };

  return <PortfolioContext.Provider value={value}>{children}</PortfolioContext.Provider>;
}

export function usePortfolioContext(): PortfolioState {
  const context = useContext(PortfolioContext);
  if (context === null) {
    throw new Error("usePortfolioContext must be used within a PortfolioProvider");
  }
  return context;
}
