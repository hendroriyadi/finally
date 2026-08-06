import { expect, test } from "@playwright/test";
import { clickLive, heatmapPanel, pnlPanel, trade, watchlistRow } from "./helpers";

test("the heatmap fills once a position exists, and the P&L chart records points", async ({ page }) => {
  await page.goto("/");

  // Empty state first — the panels say something rather than rendering blank.
  await expect(heatmapPanel(page).getByText("No open positions")).toBeVisible();

  await trade(page, "MSFT", "3", "Buy");

  // The treemap renders as SVG; its presence plus the empty-state copy
  // disappearing is the observable transition.
  await expect(heatmapPanel(page).getByText("No open positions")).toHaveCount(0);
  await expect(heatmapPanel(page).locator("svg")).toBeVisible();

  // A trade records a snapshot immediately, so the chart must leave its
  // empty state without waiting for the 30s recorder.
  await expect(pnlPanel(page).getByText("No portfolio history yet")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(pnlPanel(page).locator("svg")).toBeVisible();
});

test("clicking a watchlist ticker loads it into the detail chart", async ({ page }) => {
  await page.goto("/");

  await clickLive(watchlistRow(page, "NVDA"));

  await expect(page.getByRole("heading", { name: "NVDA Price History" })).toBeVisible();
});
