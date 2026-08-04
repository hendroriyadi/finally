import type { PortfolioHistoryPoint, PortfolioSnapshot, TradeResult, TradeSide, WatchlistItem } from "./types";

/**
 * Base URL for API requests. Empty string resolves to same-origin relative
 * paths — exactly what Phase 5's single-origin container needs with no code
 * change. Set NEXT_PUBLIC_API_URL to point at a separate backend origin
 * during local development (see .env.local.example).
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

/**
 * Thrown for any non-ok HTTP response from the watchlist API, carrying the
 * response status so callers can distinguish e.g. a 409 duplicate from a
 * 400 shape rejection without parsing error strings.
 */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (body && typeof body.detail === "string") {
      return body.detail;
    }
    return JSON.stringify(body);
  } catch {
    return response.statusText || `Request failed with status ${response.status}`;
  }
}

export async function fetchWatchlist(): Promise<WatchlistItem[]> {
  const response = await fetch(`${API_BASE}/api/watchlist`);
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  const body = (await response.json()) as { tickers: WatchlistItem[] };
  return body.tickers;
}

export async function addWatchlistTicker(ticker: string): Promise<WatchlistItem> {
  const response = await fetch(`${API_BASE}/api/watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as WatchlistItem;
}

export async function removeWatchlistTicker(ticker: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/watchlist/${encodeURIComponent(ticker)}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
}

export async function fetchPortfolio(): Promise<PortfolioSnapshot> {
  const response = await fetch(`${API_BASE}/api/portfolio`);
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as PortfolioSnapshot;
}

export async function fetchPortfolioHistory(): Promise<PortfolioHistoryPoint[]> {
  const response = await fetch(`${API_BASE}/api/portfolio/history`);
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  const body = (await response.json()) as { snapshots: PortfolioHistoryPoint[] };
  return body.snapshots;
}

export async function executeTrade(
  ticker: string,
  side: TradeSide,
  quantity: number,
): Promise<TradeResult> {
  const response = await fetch(`${API_BASE}/api/portfolio/trade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, side, quantity }),
  });
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorMessage(response));
  }
  return (await response.json()) as TradeResult;
}
