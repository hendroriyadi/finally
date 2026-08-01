import { expect, test } from "@playwright/test";
import { openTerminal, panel, watchRow } from "./helpers";

const NEW_TICKER = "PYPL";

test.describe("watchlist management", () => {
  test("adds a ticker, streams it, then removes it", async ({ page }) => {
    await openTerminal(page);

    const watchlist = panel(page, "Watchlist");
    await expect(watchRow(page, NEW_TICKER)).toHaveCount(0);

    await watchlist.getByLabel("Add ticker").fill(NEW_TICKER);
    await watchlist.getByRole("button", { name: "+" }).click();

    const added = watchRow(page, NEW_TICKER);
    await expect(added).toBeVisible();
    await expect(page.locator('[data-testid^="watch-row-"]')).toHaveCount(11);

    // A newly watched ticker must also be registered with the market data
    // source, otherwise it is listed but never priced.
    await expect(added.getByTestId("price-cell")).not.toHaveText("—");

    await added.getByRole("button", { name: `Remove ${NEW_TICKER}` }).click();

    await expect(watchRow(page, NEW_TICKER)).toHaveCount(0);
    await expect(page.locator('[data-testid^="watch-row-"]')).toHaveCount(10);

    await page.reload();
    await expect(watchRow(page, "AAPL")).toBeVisible();
    await expect(watchRow(page, NEW_TICKER)).toHaveCount(0);
  });

  test("selects a ticker into the main chart", async ({ page }) => {
    await openTerminal(page);

    await watchRow(page, "TSLA").click();

    await expect(watchRow(page, "TSLA")).toHaveAttribute("data-selected", "true");
    await expect(panel(page, /Chart\s*\S\s*TSLA/i)).toBeVisible();
    await expect(page.getByLabel("Trade ticker")).toHaveValue("TSLA");
  });
});
