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

/**
 * Chat wire types, mirroring the backend contracts built in Plans 04-01
 * (`ActionResult`, `ChatResponse`) and 04-02 (`ChatMessageOut`).
 */

export type ChatRole = "user" | "assistant";

export interface ChatActionResult {
  kind: "trade" | "watchlist";
  status: "success" | "error";
  ticker: string;
  // Fields that don't apply to a given action arrive as an explicit `null`,
  // not as an absent key — FastAPI serializes the response model's optional
  // fields rather than omitting them (verified against both POST /api/chat
  // and GET /api/chat/history). Typing these `| null` rather than `?` is
  // what makes a `!= null` guard in the consumer correct instead of a
  // `!== undefined` one that would let a null through to `.toFixed()`.
  side: "buy" | "sell" | null;
  action: "add" | "remove" | null;
  quantity: number | null;
  price: number | null;
  error: string | null;
}

export interface ChatMessage {
  role: ChatRole;
  content: string;
  // Nullable here but not on ChatResponse below, and the asymmetry is real:
  // a stored user row has no actions column value, while a live reply always
  // carries a list even when it is empty.
  actions: ChatActionResult[] | null;
  created_at: string;
}

export interface ChatResponse {
  message: string;
  actions: ChatActionResult[];
}
