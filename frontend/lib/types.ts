/**
 * Shared frontend types mirroring the backend JSON contracts documented in
 * `01-02-PLAN.md`'s `<interfaces>` block.
 */

export interface WatchlistItem {
  ticker: string;
  added_at: string;
}

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  timestamp: number;
  change: number;
  change_percent: number;
  direction: "up" | "down" | "flat";
}

export type PriceMap = Record<string, PriceUpdate>;

export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";
