"use client";

import { useEffect, useRef, useState } from "react";
import { normalizeTicks } from "@/lib/normalize";
import type { ConnectionState, PriceTick } from "@/lib/types";

export interface SparkPoint {
  t: number;
  p: number;
}

const MAX_POINTS = 240;
const FLUSH_MS = 200;

export interface MarketStream {
  prices: Record<string, PriceTick>;
  sparklines: Record<string, SparkPoint[]>;
  connection: ConnectionState;
}

export function useMarketStream(url = "/api/stream/prices"): MarketStream {
  const [prices, setPrices] = useState<Record<string, PriceTick>>({});
  const [sparklines, setSparklines] = useState<Record<string, SparkPoint[]>>({});
  const [connection, setConnection] = useState<ConnectionState>("reconnecting");
  const buffer = useRef<PriceTick[]>([]);

  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      setConnection("disconnected");
      return;
    }

    const source = new EventSource(url);

    source.onopen = () => setConnection("connected");
    source.onerror = () =>
      setConnection(
        source.readyState === EventSource.CLOSED
          ? "disconnected"
          : "reconnecting",
      );
    source.onmessage = (event: MessageEvent<string>) => {
      try {
        buffer.current.push(...normalizeTicks(JSON.parse(event.data)));
      } catch {
        // A malformed frame should not tear down the stream.
      }
    };

    const flush = window.setInterval(() => {
      const batch = buffer.current;
      if (batch.length === 0) return;
      buffer.current = [];

      setPrices((prev) => {
        const next = { ...prev };
        for (const tick of batch) next[tick.ticker] = tick;
        return next;
      });
      setSparklines((prev) => {
        const next = { ...prev };
        for (const tick of batch) {
          const series = next[tick.ticker] ?? [];
          const point = { t: tick.timestamp, p: tick.price };
          next[tick.ticker] = [...series, point].slice(-MAX_POINTS);
        }
        return next;
      });
    }, FLUSH_MS);

    return () => {
      window.clearInterval(flush);
      source.close();
    };
  }, [url]);

  return { prices, sparklines, connection };
}
