import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TradeBar } from "./TradeBar";

function setup(onTrade = vi.fn().mockResolvedValue(undefined)) {
  render(<TradeBar defaultTicker="AAPL" price={190.5} onTrade={onTrade} />);
  return onTrade;
}

describe("TradeBar", () => {
  it("prefills the selected ticker and shows notional value", () => {
    setup();
    expect(screen.getByLabelText("Trade ticker")).toHaveValue("AAPL");
    expect(screen.getByText(/≈ \$190\.50/)).toBeInTheDocument();
  });

  it("submits a buy at the entered quantity", async () => {
    const user = userEvent.setup();
    const onTrade = setup();

    const qty = screen.getByLabelText("Trade quantity");
    await user.clear(qty);
    await user.type(qty, "3");
    await user.click(screen.getByRole("button", { name: "BUY" }));

    expect(onTrade).toHaveBeenCalledWith("AAPL", 3, "buy");
    expect(await screen.findByRole("status")).toHaveTextContent(
      "BUY 3 AAPL filled",
    );
  });

  it("submits a sell", async () => {
    const user = userEvent.setup();
    const onTrade = setup();
    await user.click(screen.getByRole("button", { name: "SELL" }));
    expect(onTrade).toHaveBeenCalledWith("AAPL", 1, "sell");
  });

  it("rejects a non-positive quantity without calling the API", async () => {
    const user = userEvent.setup();
    const onTrade = setup();

    const qty = screen.getByLabelText("Trade quantity");
    await user.clear(qty);
    await user.type(qty, "0");
    await user.click(screen.getByRole("button", { name: "BUY" }));

    expect(onTrade).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Enter a ticker and a positive quantity",
    );
  });

  it("surfaces a backend rejection", async () => {
    const user = userEvent.setup();
    setup(vi.fn().mockRejectedValue(new Error("Insufficient cash")));

    await user.click(screen.getByRole("button", { name: "BUY" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Insufficient cash",
    );
  });

  it("uppercases a manually typed ticker", async () => {
    const user = userEvent.setup();
    const onTrade = setup();

    const ticker = screen.getByLabelText("Trade ticker");
    await user.clear(ticker);
    await user.type(ticker, "nvda");
    await user.click(screen.getByRole("button", { name: "BUY" }));

    expect(onTrade).toHaveBeenCalledWith("NVDA", 1, "buy");
  });
});
