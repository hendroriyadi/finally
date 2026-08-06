import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Spread the original so the real ApiError class survives — the add/remove
// children branch on `instanceof ApiError`.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchWatchlist: vi.fn(),
    addWatchlistTicker: vi.fn(),
    removeWatchlistTicker: vi.fn(),
  };
});

vi.mock("@/components/PriceStreamProvider", () => ({
  usePriceStreamContext: () => ({
    status: "connected" as const,
    prices: {},
    history: {},
    baselines: {},
  }),
}));

import { addWatchlistTicker, fetchWatchlist, removeWatchlistTicker } from "@/lib/api";
import { WatchlistPanel } from "@/components/WatchlistPanel";

const mockFetch = vi.mocked(fetchWatchlist);
const mockAdd = vi.mocked(addWatchlistTicker);
const mockRemove = vi.mocked(removeWatchlistTicker);

function panel() {
  return <WatchlistPanel selectedTicker={null} onSelectTicker={() => {}} />;
}

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => {
  vi.resetAllMocks();
});

describe("WatchlistPanel states", () => {
  it("renders a row per ticker once the mount fetch resolves", async () => {
    mockFetch.mockResolvedValue([
      { ticker: "AAPL", added_at: "2026-08-04T00:00:00Z" },
      { ticker: "MSFT", added_at: "2026-08-04T00:00:01Z" },
    ]);

    render(panel());

    // Async finder, never a synchronous getter: the fetch settles after the
    // first paint, so a sync assertion would test the pre-fetch UI and emit
    // an act warning.
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });

  it("renders the error copy and no rows when the mount fetch rejects", async () => {
    mockFetch.mockRejectedValue(new Error("network"));

    render(panel());

    expect(
      await screen.findByText("Couldn't load your watchlist — check your connection and reload."),
    ).toBeInTheDocument();
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
  });

  it("distinguishes empty from broken", async () => {
    mockFetch.mockResolvedValue([]);

    render(panel());

    expect(await screen.findByText("Your watchlist is empty")).toBeInTheDocument();
    expect(
      screen.queryByText("Couldn't load your watchlist — check your connection and reload."),
    ).not.toBeInTheDocument();
  });
});

describe("WatchlistPanel CRUD", () => {
  it("adds a ticker to the grid on a successful submit", async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([{ ticker: "AAPL", added_at: "2026-08-04T00:00:00Z" }]);
    mockAdd.mockResolvedValue({ ticker: "PYPL", added_at: "2026-08-04T00:00:02Z" });

    render(panel());
    await screen.findByText("AAPL");

    await user.type(screen.getByPlaceholderText("e.g. AAPL"), "PYPL");
    await user.click(screen.getByRole("button", { name: /add/i }));

    expect(await screen.findByText("PYPL")).toBeInTheDocument();
  });

  it("removes a ticker from the grid on a successful remove", async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([
      { ticker: "AAPL", added_at: "2026-08-04T00:00:00Z" },
      { ticker: "MSFT", added_at: "2026-08-04T00:00:01Z" },
    ]);
    mockRemove.mockResolvedValue(undefined);

    render(panel());
    await screen.findByText("MSFT");

    await user.click(screen.getByRole("button", { name: "Remove MSFT" }));

    await waitFor(() => {
      expect(screen.queryByText("MSFT")).not.toBeInTheDocument();
    });
    // The non-removed row is untouched.
    expect(screen.getByText("AAPL")).toBeInTheDocument();
  });

  it("leaves the grid unchanged when a remove fails", async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([{ ticker: "AAPL", added_at: "2026-08-04T00:00:00Z" }]);
    mockRemove.mockRejectedValue(new Error("boom"));

    render(panel());
    await screen.findByText("AAPL");

    await user.click(screen.getByRole("button", { name: "Remove AAPL" }));

    // Non-optimistic: the row only disappears once the server confirms.
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
  });
});
