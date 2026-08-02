"use client";

import { useEffect, useRef, useState } from "react";
import type { ConnectionStatus, PriceMap } from "./types";

/**
 * Per-ticker sparkline history is capped at this many points so a
 * long-running page tab does not grow memory without bound (T-01-10).
 */
export const MAX_SPARKLINE_POINTS = 60;

export interface PriceStreamState {
  status: ConnectionStatus;
  prices: PriceMap;
  history: Record<string, number[]>;
  baselines: Record<string, number>;
}

/**
 * Opens exactly one `EventSource` against `url` for the lifetime of the
 * mount and accumulates the shared price stream into state.
 *
 * The accumulators (`historyRef`/`baselinesRef`) live in refs so mutating
 * them (push + truncate, or "set once") never itself triggers a render and
 * never gets reset by one. After each frame is folded into the refs, a fresh
 * shallow copy is published into `useState` — this is what both notifies
 * React a render is due *and* gives the render path a plain state value to
 * read instead of `ref.current` (React's `react-hooks/refs` rule forbids
 * reading a ref's `current` during render — only in effects/handlers).
 *
 * The error handler never closes or reopens the connection itself, because
 * that would fight the browser's own native retry (driven by the server's
 * `retry: 1000` directive) and could produce a reconnect storm (T-01-11).
 */
export function usePriceStream(url: string): PriceStreamState {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [prices, setPrices] = useState<PriceMap>({});
  const [history, setHistory] = useState<Record<string, number[]>>({});
  const [baselines, setBaselines] = useState<Record<string, number>>({});

  const historyRef = useRef<Record<string, number[]>>({});
  const baselinesRef = useRef<Record<string, number>>({});

  useEffect(() => {
    const source = new EventSource(url);

    source.onopen = () => {
      setStatus("connected");
    };

    source.onerror = () => {
      // The browser retries on its own per the server's `retry:` directive.
      // Do not close/reopen here — see module doc comment above.
      setStatus("reconnecting");
    };

    source.onmessage = (event) => {
      let parsed: PriceMap;
      try {
        parsed = JSON.parse(event.data) as PriceMap;
      } catch (error) {
        // Malformed frame: skip it without tearing down the connection.
        console.error("usePriceStream: failed to parse SSE frame", error);
        return;
      }

      const historyAccumulator = historyRef.current;
      const baselinesAccumulator = baselinesRef.current;

      // Drop history/baseline entries for tickers no longer present in the
      // frame, so a removed ticker does not leak memory indefinitely.
      for (const ticker of Object.keys(historyAccumulator)) {
        if (!(ticker in parsed)) {
          delete historyAccumulator[ticker];
        }
      }
      for (const ticker of Object.keys(baselinesAccumulator)) {
        if (!(ticker in parsed)) {
          delete baselinesAccumulator[ticker];
        }
      }

      for (const [ticker, update] of Object.entries(parsed)) {
        if (!(ticker in baselinesAccumulator)) {
          baselinesAccumulator[ticker] = update.price;
        }

        const points = historyAccumulator[ticker] ?? [];
        points.push(update.price);
        if (points.length > MAX_SPARKLINE_POINTS) {
          points.splice(0, points.length - MAX_SPARKLINE_POINTS);
        }
        historyAccumulator[ticker] = points;
      }

      setPrices(parsed);
      setHistory({ ...historyAccumulator });
      setBaselines({ ...baselinesAccumulator });
    };

    return () => {
      source.close();
    };
  }, [url]);

  return { status, prices, history, baselines };
}
