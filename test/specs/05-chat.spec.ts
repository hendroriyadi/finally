import { expect, test } from "@playwright/test";
import {
  lastAssistantMessage,
  openTerminal,
  positionRow,
  readCash,
  sendChat,
  watchRow,
} from "./helpers";

/**
 * Runs against LLM_MOCK=true. The mock's triggers are keyword-based and
 * first-match-wins: "watchlist" beats "buy"/"sell", which beat the plain
 * informational reply.
 */
test.describe("AI chat (mocked LLM)", () => {
  test("answers an informational question with no side effects", async ({
    page,
  }) => {
    await openTerminal(page);
    const cashBefore = await readCash(page);

    await sendChat(page, "How is my portfolio doing?");

    await expect(page.getByTestId("chat-user").last()).toContainText(
      "How is my portfolio doing?",
    );
    await expect(lastAssistantMessage(page)).toContainText(/You are holding/i);
    await expect(page.getByTestId("chat-loading")).toHaveCount(0);
    await expect(page.getByTestId("trade-chip")).toHaveCount(0);

    expect(await readCash(page)).toBeCloseTo(cashBefore, 2);
  });

  test("shows a loading indicator while the assistant works", async ({
    page,
  }) => {
    await openTerminal(page);

    // Hold the response open so the pending state is observable.
    await page.route("**/api/chat", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.continue();
    });

    await sendChat(page, "What should I know about my holdings?");
    await expect(page.getByTestId("chat-loading")).toBeVisible();
    await expect(page.getByTestId("chat-loading")).toHaveCount(0, {
      timeout: 30_000,
    });

    await page.unroute("**/api/chat");
  });

  test("executes a requested trade and confirms it inline", async ({ page }) => {
    await openTerminal(page);
    const cashBefore = await readCash(page);

    await sendChat(page, "Buy 5 shares of AAPL");

    await expect(lastAssistantMessage(page)).toContainText(/buy 5 .*AAPL/i);

    const chip = page.getByTestId("trade-chip").last();
    await expect(chip).toBeVisible();
    await expect(chip).toContainText("BUY");
    await expect(chip).toContainText("5");
    await expect(chip).toContainText("AAPL");

    // The chat flow must also refresh the portfolio, not just render a chip.
    await expect(positionRow(page, "AAPL")).toBeVisible();
    await expect(positionRow(page, "AAPL").locator("td").nth(1)).toHaveText("5");
    expect(await readCash(page)).toBeLessThan(cashBefore);
  });

  test("renders a rejected trade as a failed chip with the reason", async ({
    page,
  }) => {
    await openTerminal(page);
    await expect(positionRow(page, "TSLA")).toHaveCount(0);
    const cashBefore = await readCash(page);

    await sendChat(page, "sell 2 TSLA");

    const chip = page.getByTestId("trade-chip").last();
    await expect(chip).toBeVisible();
    await expect(chip).toContainText(/insufficient shares/i);
    // Failed chips carry the down/red treatment.
    await expect(chip).toHaveClass(/text-down/);

    // The failure also reaches the prose so the next turn's history carries it.
    await expect(lastAssistantMessage(page)).toContainText(/insufficient shares/i);

    await expect(positionRow(page, "TSLA")).toHaveCount(0);
    expect(await readCash(page)).toBeCloseTo(cashBefore, 2);
  });

  test("adds and removes a watchlist ticker through chat", async ({ page }) => {
    await openTerminal(page);
    await expect(watchRow(page, "SNOW")).toHaveCount(0);

    await sendChat(page, "Add SNOW to my watchlist");

    const addChip = page.getByTestId("watchlist-chip").last();
    await expect(addChip).toContainText("SNOW");
    await expect(addChip).toContainText("WATCH");
    await expect(watchRow(page, "SNOW")).toBeVisible();
    await expect(watchRow(page, "SNOW").getByTestId("price-cell")).not.toHaveText(
      "—",
    );

    await sendChat(page, "remove SNOW from the watchlist");

    await expect(page.getByTestId("watchlist-chip").last()).toContainText("SNOW");
    await expect(watchRow(page, "SNOW")).toHaveCount(0);
  });
});
