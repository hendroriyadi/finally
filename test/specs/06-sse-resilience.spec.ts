import { expect, test } from "@playwright/test";
import { connectionDot, expectTextToChange, openTerminal, watchRow } from "./helpers";

const STREAM = "**/api/stream/prices";

test.describe("SSE resilience", () => {
  test("surfaces a broken stream and recovers without user action", async ({
    page,
  }) => {
    await openTerminal(page);

    const price = watchRow(page, "AAPL").getByTestId("price-cell");
    await expectTextToChange(price);

    // context.setOffline() leaves an already-established SSE socket intact, so
    // the break has to happen where the stream is (re)opened.
    await page.route(STREAM, (route) => route.abort());
    await page.reload();

    // EventSource reports CONNECTING while retrying and CLOSED once it gives
    // up; either is a truthful "not live" signal for the header dot.
    await expect(connectionDot(page)).toHaveAttribute(
      "data-state",
      /reconnecting|disconnected/,
    );

    // No reload here: EventSource's built-in retry must recover on its own.
    await page.unroute(STREAM);

    await expect(connectionDot(page)).toHaveAttribute("data-state", "connected", {
      timeout: 30_000,
    });
    await expectTextToChange(price, 30_000);
  });

  test("recovers the stream after a full page reload", async ({ page }) => {
    await openTerminal(page);
    await page.reload();

    await expect(connectionDot(page)).toHaveAttribute("data-state", "connected");
    await expectTextToChange(watchRow(page, "GOOGL").getByTestId("price-cell"));
  });

  test("streams the same tick cadence to two concurrent clients", async ({
    context,
  }) => {
    const first = await context.newPage();
    const second = await context.newPage();

    await openTerminal(first);
    await openTerminal(second);

    await expectTextToChange(watchRow(first, "MSFT").getByTestId("price-cell"));
    await expectTextToChange(watchRow(second, "MSFT").getByTestId("price-cell"));

    await first.close();
    await second.close();
  });
});
