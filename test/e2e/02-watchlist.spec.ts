import { expect, test } from "@playwright/test";
import { addTickerInput, clickLive, watchlistPanel } from "./helpers";

test("a ticker can be added and removed, and the added one streams a price", async ({ page }) => {
  await page.goto("/");
  const panel = watchlistPanel(page);
  await expect(panel.getByText("AAPL", { exact: true })).toBeVisible();

  await addTickerInput(page).fill("PYPL");
  await clickLive(panel.getByRole("button", { name: "Add Ticker" }));

  await expect(panel.getByText("PYPL", { exact: true })).toBeVisible();

  // A ticker that appears in the grid but never gets a price is the exact
  // failure the shared apply_watchlist_add helper exists to prevent.
  await expect
    .poll(
      async () => {
        const row = panel.locator("div.group").filter({ hasText: "PYPL" });
        return (await row.locator("div.tabular-nums").first().textContent())?.trim() ?? "—";
      },
      { timeout: 30_000 },
    )
    .not.toBe("—");

  await clickLive(panel.getByRole("button", { name: "Remove PYPL" }));
  await expect(panel.getByText("PYPL", { exact: true })).toHaveCount(0);
});
