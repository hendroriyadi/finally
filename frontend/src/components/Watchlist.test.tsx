import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Watchlist, type WatchRow } from "./Watchlist";

const rows: WatchRow[] = [
  { ticker: "AAPL", price: 190.25, changePct: 1.24, spark: [] },
  {
    ticker: "TSLA",
    price: 242.1,
    changePct: -2.05,
    spark: [
      { t: 1, p: 240 },
      { t: 2, p: 242.1 },
    ],
  },
];

function setup(overrides: Partial<React.ComponentProps<typeof Watchlist>> = {}) {
  const props = {
    rows,
    selected: "AAPL" as string | null,
    onSelect: vi.fn(),
    onAdd: vi.fn(),
    onRemove: vi.fn(),
    ...overrides,
  };
  render(<Watchlist {...props} />);
  return props;
}

describe("Watchlist", () => {
  it("renders each ticker with price and change", () => {
    setup();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("+1.24%")).toBeInTheDocument();
    expect(screen.getByText("-2.05%")).toBeInTheDocument();
    expect(screen.getByText("242.10")).toBeInTheDocument();
  });

  it("marks the selected row", () => {
    setup();
    expect(screen.getByTestId("watch-row-AAPL")).toHaveAttribute(
      "data-selected",
      "true",
    );
    expect(screen.getByTestId("watch-row-TSLA")).not.toHaveAttribute(
      "data-selected",
    );
  });

  it("selects a ticker on row click", async () => {
    const user = userEvent.setup();
    const { onSelect } = setup();
    await user.click(screen.getByTestId("watch-row-TSLA"));
    expect(onSelect).toHaveBeenCalledWith("TSLA");
  });

  it("adds an uppercased ticker and clears the input", async () => {
    const user = userEvent.setup();
    const { onAdd } = setup();
    const input = screen.getByLabelText("Add ticker");

    await user.type(input, "pypl");
    await user.click(screen.getByRole("button", { name: "+" }));

    expect(onAdd).toHaveBeenCalledWith("PYPL");
    expect(input).toHaveValue("");
  });

  it("ignores an empty add submission", async () => {
    const user = userEvent.setup();
    const { onAdd } = setup();
    await user.click(screen.getByRole("button", { name: "+" }));
    expect(onAdd).not.toHaveBeenCalled();
  });

  it("removes a ticker without selecting the row", async () => {
    const user = userEvent.setup();
    const { onRemove, onSelect } = setup();
    await user.click(screen.getByLabelText("Remove TSLA"));
    expect(onRemove).toHaveBeenCalledWith("TSLA");
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("shows an empty state with no tickers", () => {
    setup({ rows: [] });
    expect(screen.getByText("No tickers watched")).toBeInTheDocument();
  });
});
