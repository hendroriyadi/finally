"use client";

import { createContext, useContext, type ReactNode } from "react";
import { API_BASE } from "@/lib/api";
import { usePriceStream, type PriceStreamState } from "@/lib/useSseStream";

const PriceStreamContext = createContext<PriceStreamState | null>(null);

/**
 * Opens the single shared `EventSource` for the whole page and publishes it
 * through context. This is the reason exactly one connection exists per page
 * load: the header and the watchlist grid are siblings, so neither can own
 * the stream without the other opening a second one.
 */
export function PriceStreamProvider({ children }: { children: ReactNode }) {
  const stream = usePriceStream(`${API_BASE}/api/stream/prices`);

  return <PriceStreamContext.Provider value={stream}>{children}</PriceStreamContext.Provider>;
}

export function usePriceStreamContext(): PriceStreamState {
  const context = useContext(PriceStreamContext);
  if (context === null) {
    throw new Error("usePriceStreamContext must be used within a PriceStreamProvider");
  }
  return context;
}
