import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useMarketStream } from "./useMarketStream";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  readyState = FakeEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }

  open() {
    this.readyState = FakeEventSource.OPEN;
    this.onopen?.();
  }

  emit(payload: unknown) {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(payload) }),
    );
  }

  emitRaw(data: string) {
    this.onmessage?.(new MessageEvent("message", { data }));
  }

  fail(readyState: number) {
    this.readyState = readyState;
    this.onerror?.();
  }

  close() {
    this.closed = true;
    this.readyState = FakeEventSource.CLOSED;
  }
}

const tick = (ticker: string, price: number) => ({
  ticker,
  price,
  previous_price: price - 1,
  timestamp: 1785517560.692627,
  change_percent: 0.5,
  direction: "up" as const,
});

const flush = () => act(() => vi.advanceTimersByTime(250));

describe("useMarketStream", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  const source = () => FakeEventSource.instances[0];

  it("starts reconnecting and reports connected once the stream opens", () => {
    const { result } = renderHook(() => useMarketStream());
    expect(result.current.connection).toBe("reconnecting");

    act(() => source().open());
    expect(result.current.connection).toBe("connected");
  });

  it("reports disconnected when the stream closes and reconnecting otherwise", () => {
    const { result } = renderHook(() => useMarketStream());

    act(() => source().fail(FakeEventSource.CLOSED));
    expect(result.current.connection).toBe("disconnected");

    act(() => source().fail(FakeEventSource.CONNECTING));
    expect(result.current.connection).toBe("reconnecting");
  });

  it("accumulates the latest price and a sparkline series per ticker", () => {
    const { result } = renderHook(() => useMarketStream());

    act(() => {
      source().open();
      source().emit(tick("AAPL", 190));
      source().emit(tick("AAPL", 191));
    });
    flush();

    expect(result.current.prices.AAPL.price).toBe(191);
    expect(result.current.sparklines.AAPL).toHaveLength(2);
    expect(result.current.sparklines.AAPL.map((p) => p.p)).toEqual([190, 191]);
  });

  it("accepts a batched array of ticks", () => {
    const { result } = renderHook(() => useMarketStream());

    act(() => source().emit([tick("AAPL", 190), tick("TSLA", 240)]));
    flush();

    expect(result.current.prices.AAPL.price).toBe(190);
    expect(result.current.prices.TSLA.price).toBe(240);
  });

  it("accepts a {prices: [...]} envelope", () => {
    const { result } = renderHook(() => useMarketStream());

    act(() => source().emit({ prices: [tick("MSFT", 410)] }));
    flush();

    expect(result.current.prices.MSFT.price).toBe(410);
  });

  it("accepts the backend's ticker-keyed map frame", () => {
    const { result } = renderHook(() => useMarketStream());

    act(() =>
      source().emit({ AAPL: tick("AAPL", 190), GOOGL: tick("GOOGL", 175) }),
    );
    flush();

    expect(result.current.prices.AAPL.price).toBe(190);
    expect(result.current.prices.GOOGL.price).toBe(175);
    expect(result.current.sparklines.GOOGL).toHaveLength(1);
  });

  it("survives a malformed frame", () => {
    const { result } = renderHook(() => useMarketStream());

    act(() => {
      source().emitRaw("not json");
      source().emit(tick("NVDA", 880));
    });
    flush();

    expect(result.current.prices.NVDA.price).toBe(880);
  });

  it("closes the stream on unmount", () => {
    const { unmount } = renderHook(() => useMarketStream());
    unmount();
    expect(source().closed).toBe(true);
  });
});
