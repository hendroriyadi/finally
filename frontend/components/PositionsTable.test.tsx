import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Position, PriceMap } from "@/lib/types";

const portfolio = {
  cashBalance: 10000,
  positions: [] as Position[],
  totalValue: 10000,
  loading: false,
  error: false,
  refresh: vi.fn(),
};
let prices: PriceMap = {};

vi.mock("@/components/PortfolioProvider", () => ({
  usePortfolioContext: () => portfolio,
}));
vi.mock("@/components/PriceStreamProvider", () => ({
  usePriceStreamContext: () => ({
    status: "connected" as const,
    prices,
    history: {},
    baselines: {},
  }),
}));

import { PositionsTable } from "@/components/PositionsTable";

function position(over: Partial<Position> = {}): Position {
  return {
    ticker: "AAPL",
    quantity: 10,
    avg_cost: 100,
    current_price: 100,
    unrealized_pnl: 0,
    change_percent: 0,
    ...over,
  };
}

function priceMap(ticker: string, price: number): PriceMap {
  return {
    [ticker]: {
      ticker,
      price,
      previous_price: price,
      timestamp: 0,
      change: 0,
      change_percent: 0,
      direction: "flat",
    },
  };
}

beforeEach(() => {
  portfolio.positions = [];
  portfolio.loading = false;
  portfolio.error = false;
  prices = {};
});

describe("PositionsTable states", () => {
  it("renders the error copy when the portfolio fetch failed", () => {
    portfolio.error = true;
    render(<PositionsTable />);

    expect(
      screen.getByText("Couldn't load your positions — check your connection and reload."),
    ).toBeInTheDocument();
  });

  it("renders the empty state when there are no positions", () => {
    render(<PositionsTable />);

    expect(screen.getByText("No open positions")).toBeInTheDocument();
  });
});

describe("PositionsTable display calculations", () => {
  it("derives P&L and % change from the LIVE price, not the server snapshot", () => {
    // The server snapshot says break-even; the live stream says +10%. The
    // table must follow the stream — showing a fresh price beside a stale
    // P&L is the bug this derivation exists to prevent.
    // quantity 3 (not 10) so the P&L figure can't collide with the avg-cost
    // cell and make the assertion ambiguous.
    portfolio.positions = [
      position({ quantity: 3, current_price: 100, unrealized_pnl: 0, change_percent: 0 }),
    ];
    prices = priceMap("AAPL", 110);

    render(<PositionsTable />);

    expect(screen.getByText("110.00")).toBeInTheDocument(); // live price wins
    expect(screen.getByText("30.00")).toBeInTheDocument(); // (110-100)*3
    expect(screen.getByText("+10.00%")).toBeInTheDocument();
  });

  it("shows a negative P&L and percent when the live price is below cost", () => {
    portfolio.positions = [position({ quantity: 5, avg_cost: 200 })];
    prices = priceMap("AAPL", 180);

    render(<PositionsTable />);

    expect(screen.getByText("-100.00")).toBeInTheDocument(); // (180-200)*5
    expect(screen.getByText("-10.00%")).toBeInTheDocument();
  });

  it("falls back to the server price when the ticker is absent from the stream", () => {
    portfolio.positions = [position({ current_price: 123 })];
    prices = {}; // nothing streaming yet

    render(<PositionsTable />);

    expect(screen.getByText("123.00")).toBeInTheDocument();
  });

  it("renders em-dashes rather than zeros when no price is available at all", () => {
    portfolio.positions = [position({ current_price: null, unrealized_pnl: null, change_percent: null })];

    render(<PositionsTable />);

    // A zero here would read as "worth nothing" rather than "not known yet".
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });

  it("renders one row per position", () => {
    portfolio.positions = [
      position({ ticker: "AAPL" }),
      position({ ticker: "MSFT", quantity: 2, avg_cost: 300 }),
    ];
    prices = { ...priceMap("AAPL", 100), ...priceMap("MSFT", 300) };

    render(<PositionsTable />);

    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });
});
