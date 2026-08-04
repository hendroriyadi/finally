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

/**
 * Portfolio wire types mirroring the backend contract documented in
 * `02-01-PLAN.md`'s `<interfaces>` block.
 */

export interface Holding {
  ticker: string;
  quantity: number;
  avg_cost: number;
}

export interface Position extends Holding {
  current_price: number | null;
  unrealized_pnl: number | null;
  change_percent: number | null;
}

export interface PortfolioSnapshot {
  cash_balance: number;
  total_value: number;
  positions: Position[];
}

export type TradeSide = "buy" | "sell";

export interface TradeResult {
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number;
  cash_balance: number;
  position: Holding | null;
}

/**
 * One point of `GET /api/portfolio/history`. Mirrors Plan 03-01's
 * `SnapshotOut`. Deliberately not named `PortfolioSnapshot` — that
 * identifier is already the `GET /api/portfolio` response type above.
 */
export interface PortfolioHistoryPoint {
  total_value: number;
  recorded_at: string;
}
