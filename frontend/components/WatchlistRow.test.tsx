import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { WatchlistRow } from "@/components/WatchlistRow";

const FADE_MS = 500;
const UP = "bg-positive/20";
const DOWN = "bg-destructive/20";

function renderRow(price: number | undefined) {
  const view = render(
    <WatchlistRow
      ticker="AAPL"
      price={price}
      changePercent={0}
      points={[]}
      selected={false}
      onSelect={() => {}}
    />,
  );
  return (next: number | undefined) =>
    view.rerender(
      <WatchlistRow
        ticker="AAPL"
        price={next}
        changePercent={0}
        points={[]}
        selected={false}
        onSelect={() => {}}
      />,
    );
}

// The price cell's text is the price at two decimals, so querying for that
// string returns the exact element carrying the flash class.
function priceCell(price: number) {
  return screen.getByText(price.toFixed(2));
}

describe("WatchlistRow price flash", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    // Leaking fake timers into a later file is a debugging session nobody
    // enjoys.
    vi.useRealTimers();
  });

  it("does not flash on the very first price", () => {
    renderRow(190);

    // A row that flashed on arrival would light up the whole grid on load.
    expect(priceCell(190).className).not.toContain(UP);
    expect(priceCell(190).className).not.toContain(DOWN);
  });

  it("flashes green on an uptick", () => {
    const rerender = renderRow(190);
    act(() => rerender(191));

    expect(priceCell(191).className).toContain(UP);
  });

  it("flashes red on a downtick", () => {
    const rerender = renderRow(190);
    act(() => rerender(189));

    expect(priceCell(189).className).toContain(DOWN);
  });

  it("stops flashing once the fade window elapses", () => {
    const rerender = renderRow(190);
    act(() => rerender(191));
    expect(priceCell(191).className).toContain(UP);

    // Advancing inside act(): outside it the timer's state update happens
    // outside React's batching and emits an act warning that buries real
    // failures later in the suite.
    act(() => {
      vi.advanceTimersByTime(FADE_MS);
    });

    expect(priceCell(191).className).not.toContain(UP);
    expect(priceCell(191).className).not.toContain(DOWN);
  });

  it("restarts the fade on a second tick rather than letting the first timer clear it", () => {
    const rerender = renderRow(190);
    act(() => rerender(191));

    // Most of the way through the first fade window...
    act(() => {
      vi.advanceTimersByTime(FADE_MS - 100);
    });
    // ...a second tick arrives.
    act(() => rerender(192));
    // Past the moment the FIRST tick's timer would have fired.
    act(() => {
      vi.advanceTimersByTime(150);
    });

    // Still flashing: the second tick restarted the window. A naive
    // implementation lets the stale timer clear the fresh flash here — the
    // one behavior in this component that is easy to get wrong.
    expect(priceCell(192).className).toContain(UP);
  });

  it("does not flash when a frame repeats the same price", () => {
    const rerender = renderRow(190);
    act(() => rerender(190));

    // An SSE frame that repeats a price is not a tick.
    expect(priceCell(190).className).not.toContain(UP);
    expect(priceCell(190).className).not.toContain(DOWN);
  });

  it("renders the placeholder and no flash when no price is available", () => {
    renderRow(undefined);

    const cell = screen.getByText("—");
    expect(cell.className).not.toContain(UP);
    expect(cell.className).not.toContain(DOWN);
  });
});
