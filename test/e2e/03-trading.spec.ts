import { expect, test } from "@playwright/test";
import { headerCash, positionsPanel, trade } from "./helpers";

test("buying moves cash and creates a position; selling reverses it", async ({ page }) => {
  await page.goto("/");
  await expect(headerCash(page)).not.toHaveText("—");
  const before = Number((await headerCash(page).textContent())!);

  await trade(page, "AAPL", "2", "Buy");

  await expect(positionsPanel(page).getByText("AAPL", { exact: true })).toBeVisible();
  await expect.poll(async () => Number((await headerCash(page).textContent())!)).toBeLessThan(before);

  const afterBuy = Number((await headerCash(page).textContent())!);

  await trade(page, "AAPL", "2", "Sell");

  await expect(positionsPanel(page).getByText("No open positions")).toBeVisible();
  await expect
    .poll(async () => Number((await headerCash(page).textContent())!))
    .toBeGreaterThan(afterBuy);
});

test("a buy beyond available cash is rejected and leaves cash unchanged", async ({ page }) => {
  await page.goto("/");
  await expect(headerCash(page)).not.toHaveText("—");
  const before = await headerCash(page).textContent();

  await trade(page, "AAPL", "100000", "Buy");

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(headerCash(page)).toHaveText(before!);
});
