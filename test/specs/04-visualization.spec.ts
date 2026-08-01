import { expect, test } from "@playwright/test";
import { openTerminal, panel, positionRow, submitTrade } from "./helpers";

const VIZ_TICKER = "META";

test.describe("portfolio visualization", () => {
  test.beforeEach(async ({ page }) => {
    await openTerminal(page);
    if ((await positionRow(page, VIZ_TICKER).count()) === 0) {
      await submitTrade(page, VIZ_TICKER, 1, "buy");
      await expect(positionRow(page, VIZ_TICKER)).toBeVisible();
    }
  });

  test("heatmap tiles every position and colors them by P&L sign", async ({
    page,
  }) => {
    const heatmap = panel(page, "Portfolio Heatmap");
    await expect(heatmap.getByText("No open positions")).toHaveCount(0);

    const rows = page.locator('[data-testid^="position-row-"]');
    const positionCount = await rows.count();
    expect(positionCount).toBeGreaterThan(0);

    // Recharts also paints the treemap's root node through the custom tile
    // renderer, so there is one more rect than there are positions.
    const tiles = heatmap.locator('svg g rect[fill^="color-mix"]');
    await expect
      .poll(() => tiles.count())
      .toBeGreaterThanOrEqual(positionCount);

    for (let i = 0; i < positionCount; i += 1) {
      const ticker = (await rows.nth(i).locator("td").first().innerText()).trim();
      const pnlPct = Number(
        (await rows.nth(i).locator("td").nth(6).innerText()).replace(/[+%]/g, ""),
      );

      const tile = heatmap
        .locator("svg g")
        .filter({ hasText: new RegExp(`^${ticker}`) })
        .locator('rect[fill^="color-mix"]')
        .first();
      const fill = await tile.getAttribute("fill");

      expect(fill, `${ticker} tile fill (pnl ${pnlPct}%)`).toContain(
        pnlPct >= 0 ? "--color-up" : "--color-down",
      );
    }
  });

  test("P&L chart plots the snapshot series", async ({ page }) => {
    const chart = panel(page, "Portfolio Value");

    await expect(chart.getByText("Awaiting portfolio snapshots")).toHaveCount(0);

    const line = chart.locator("path.recharts-curve.recharts-line-curve");
    await expect(line).toBeVisible();

    const d = await line.getAttribute("d");
    expect(d, "P&L line path data").toBeTruthy();
    // At least two plotted points -> a move plus one or more line segments.
    expect((d ?? "").split(/[LC]/).length).toBeGreaterThan(1);
  });

  test("main chart renders live ticks for the selected ticker", async ({
    page,
  }) => {
    const chart = panel(page, /^Chart/i);
    await expect(chart.getByText("Accumulating live ticks")).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(chart.locator("path.recharts-area-area")).toBeVisible();
  });
});
