import { expect, test } from "@playwright/test";
import {
  DEFAULT_TICKERS,
  collectPageErrors,
  connectionDot,
  expectTextToChange,
  headerStat,
  openTerminal,
  panel,
  readCash,
  watchRow,
} from "./helpers";

/**
 * Runs first against a freshly seeded database, so it is the only spec allowed
 * to assert the untouched $10,000 starting balance.
 */
test.describe("fresh start", () => {
  test("seeds the default watchlist, $10,000 cash, and a live stream", async ({
    page,
  }) => {
    const errors = collectPageErrors(page);

    await page.goto("/");

    await expect(connectionDot(page)).toHaveAttribute(
      "data-state",
      "connected",
    );

    for (const ticker of DEFAULT_TICKERS) {
      await expect(watchRow(page, ticker)).toBeVisible();
    }
    await expect(page.locator('[data-testid^="watch-row-"]')).toHaveCount(
      DEFAULT_TICKERS.length,
    );

    expect(await readCash(page)).toBeCloseTo(10_000, 2);
    await expect(headerStat(page, "Total Value")).toHaveText(/^\$10,000\.00$/);

    await expect(page.locator('[data-testid^="position-row-"]')).toHaveCount(0);
    await expect(
      panel(page, /^Positions/i).getByText("No open positions"),
    ).toBeVisible();

    expect(errors, `console errors on fresh load: ${errors.join(" | ")}`).toEqual(
      [],
    );
  });

  test("keeps pushing SSE ticks after the stream opens", async ({ page }) => {
    await openTerminal(page);

    const price = watchRow(page, "AAPL").getByTestId("price-cell");
    await expect(price).not.toHaveText("—");

    // Three consecutive changes: a stream that connects and then stalls (the
    // GZip-buffering failure mode) passes a single-change check by luck.
    for (let i = 0; i < 3; i += 1) {
      await expectTextToChange(price);
    }

    await expect(connectionDot(page)).toHaveAttribute(
      "data-state",
      "connected",
    );
  });

  test("loads the dark theme and flashes prices on tick", async ({ page }) => {
    await openTerminal(page);

    // A stylesheet that failed to load still satisfies every DOM assertion.
    await expect(page.locator("body")).toHaveCSS(
      "background-color",
      "rgb(13, 17, 23)",
    );

    const cell = watchRow(page, "AAPL").getByTestId("price-cell");
    await expect
      .poll(() => cell.getAttribute("class"), {
        timeout: 20_000,
        intervals: [100],
      })
      .toMatch(/flash-(up|down)/);
  });

  test("accumulates sparklines from the stream", async ({ page }) => {
    await openTerminal(page);

    // The placeholder is labelled "sparkline pending" until two ticks land.
    const drawn = watchRow(page, "NVDA").locator('svg[aria-label="sparkline"] path');
    await expect(drawn).toBeVisible({ timeout: 30_000 });
    await expect(drawn).toHaveAttribute("d", /L/);
  });
});
