import { expect, test } from "@playwright/test";
import {
  connectionStatus,
  headerCash,
  headerPortfolioValue,
  positionsPanel,
  watchlistPanel,
} from "./helpers";

// MUST RUN FIRST. This is the only spec that depends on ordering: it asserts
// the untouched $10,000 starting balance, which every later spec spends.
// Playwright collects files alphabetically, so the numeric prefix is the
// mechanism enforcing it — renaming this file without a prefix would let a
// later spec trade first and break these assertions.

const SEEDED = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"];

test("a fresh container serves the seeded terminal with a live stream", async ({ page }) => {
  await page.goto("/");

  for (const ticker of SEEDED) {
    await expect(watchlistPanel(page).getByText(ticker, { exact: true })).toBeVisible();
  }

  // Auto-retrying: the header shows an em-dash until the portfolio fetch
  // settles, so polling until the value appears is both faster and more
  // truthful than sleeping and snapshotting.
  await expect(headerCash(page)).toHaveText("10000.00");
  await expect(headerPortfolioValue(page)).toHaveText("10000.00");

  await expect(positionsPanel(page).getByText("No open positions")).toBeVisible();
  await expect(connectionStatus(page)).toHaveAttribute("aria-label", "Connected");

  // The assertion that proves the STREAM is delivering, not merely that the
  // page rendered: at least one price cell stops showing its placeholder.
  await expect
    .poll(
      async () => {
        const cells = await watchlistPanel(page).locator("div.tabular-nums").allTextContents();
        return cells.filter((t) => t.trim() !== "—" && t.trim() !== "").length;
      },
      { timeout: 30_000 },
    )
    .toBeGreaterThan(0);
});
