import { expect, test } from "@playwright/test";
import {
  openTerminal,
  parseMoney,
  positionRow,
  readCash,
  readTotalValue,
  submitTrade,
  watchRow,
} from "./helpers";

/** Reserved by this spec so other specs can't perturb its position math. */
const BUY_TICKER = "NVDA";
const ROUNDTRIP_TICKER = "MSFT";

test.describe("manual trading", () => {
  test("buying decreases cash and opens a position", async ({ page }) => {
    await openTerminal(page);

    const cashBefore = await readCash(page);
    const totalBefore = await readTotalValue(page);
    const fillPrice = parseMoney(
      await watchRow(page, BUY_TICKER).getByTestId("price-cell").innerText(),
    );
    expect(fillPrice).toBeGreaterThan(0);

    const status = await submitTrade(page, BUY_TICKER, 2, "buy");
    expect(status).toMatch(/BUY 2 NVDA filled/i);

    const row = positionRow(page, BUY_TICKER);
    await expect(row).toBeVisible();
    await expect(row.locator("td").nth(1)).toHaveText("2");

    const cashAfter = await readCash(page);
    expect(cashAfter).toBeLessThan(cashBefore);
    // Prices tick ~500ms, so the fill is near — not exactly — the quoted price.
    expect(cashBefore - cashAfter).toBeGreaterThan(fillPrice * 2 * 0.9);
    expect(cashBefore - cashAfter).toBeLessThan(fillPrice * 2 * 1.1);

    // Buying moves cash into positions; total value stays in the same ballpark.
    expect(Math.abs((await readTotalValue(page)) - totalBefore)).toBeLessThan(
      totalBefore * 0.05,
    );
  });

  test("selling part of a position increases cash and reduces quantity", async ({
    page,
  }) => {
    await openTerminal(page);

    await submitTrade(page, ROUNDTRIP_TICKER, 3, "buy");
    const row = positionRow(page, ROUNDTRIP_TICKER);
    await expect(row).toBeVisible();
    await expect(row.locator("td").nth(1)).toHaveText("3");

    const cashBefore = await readCash(page);

    const status = await submitTrade(page, ROUNDTRIP_TICKER, 1, "sell");
    expect(status).toMatch(/SELL 1 MSFT filled/i);

    await expect(row.locator("td").nth(1)).toHaveText("2");
    expect(await readCash(page)).toBeGreaterThan(cashBefore);
  });

  test("selling the full position removes the row", async ({ page }) => {
    await openTerminal(page);

    await expect(positionRow(page, ROUNDTRIP_TICKER)).toBeVisible();
    const cashBefore = await readCash(page);

    await submitTrade(page, ROUNDTRIP_TICKER, 2, "sell");

    await expect(positionRow(page, ROUNDTRIP_TICKER)).toHaveCount(0);
    expect(await readCash(page)).toBeGreaterThan(cashBefore);
  });

  test("rejects a sell with no shares held and leaves the portfolio untouched", async ({
    page,
  }) => {
    await openTerminal(page);

    const cashBefore = await readCash(page);

    const status = await submitTrade(page, "NFLX", 5, "sell");
    expect(status).toMatch(/insufficient shares/i);

    await expect(positionRow(page, "NFLX")).toHaveCount(0);
    expect(await readCash(page)).toBeCloseTo(cashBefore, 2);
  });

  test("rejects a buy that exceeds available cash", async ({ page }) => {
    await openTerminal(page);

    const cashBefore = await readCash(page);

    const status = await submitTrade(page, "AMZN", 100_000, "buy");
    expect(status).toMatch(/insufficient cash/i);

    await expect(positionRow(page, "AMZN")).toHaveCount(0);
    expect(await readCash(page)).toBeCloseTo(cashBefore, 2);
  });
});
