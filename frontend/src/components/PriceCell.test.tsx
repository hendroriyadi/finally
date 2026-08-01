import { render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PriceCell } from "./PriceCell";

describe("PriceCell flash animation", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  const cell = () => screen.getByTestId("price-cell");

  it("does not flash on first render", () => {
    render(<PriceCell price={190.12} />);
    expect(cell()).not.toHaveClass("flash-up");
    expect(cell()).not.toHaveClass("flash-down");
  });

  it("flashes green on an uptick and clears after 500ms", () => {
    const { rerender } = render(<PriceCell price={190.0} />);
    rerender(<PriceCell price={191.5} />);

    expect(cell()).toHaveClass("flash-up");

    act(() => vi.advanceTimersByTime(500));
    expect(cell()).not.toHaveClass("flash-up");
  });

  it("flashes red on a downtick", () => {
    const { rerender } = render(<PriceCell price={190.0} />);
    rerender(<PriceCell price={188.25} />);

    expect(cell()).toHaveClass("flash-down");
    expect(cell()).not.toHaveClass("flash-up");
  });

  it("does not flash when the price is unchanged", () => {
    const { rerender } = render(<PriceCell price={190.0} />);
    rerender(<PriceCell price={190.0} />);

    expect(cell()).not.toHaveClass("flash-up");
    expect(cell()).not.toHaveClass("flash-down");
  });

  it("renders the formatted price", () => {
    render(<PriceCell price={1234.5} />);
    expect(cell()).toHaveTextContent("1,234.50");
  });
});
