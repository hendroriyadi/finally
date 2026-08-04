import { expect, test } from "@playwright/test";
import { chatPanel, headerCash, positionsPanel, sendChat, watchlistPanel } from "./helpers";

// Every message below uses one of app/llm/mock.py's EXACT trigger shapes:
//   buy N TICKER / sell N TICKER
//   add TICKER to my watchlist / remove TICKER from my watchlist
// Any other phrasing silently returns the mock's no-action reply, and the
// test would fail for a reason that has nothing to do with the feature.

test("the assistant executes a trade and shows an inline confirmation", async ({ page }) => {
  await page.goto("/");
  await expect(headerCash(page)).not.toHaveText("—");
  const before = Number((await headerCash(page).textContent())!);

  await sendChat(page, "buy 1 TSLA");

  await expect(chatPanel(page).getByText(/^Bought 1 TSLA at \$/)).toBeVisible();
  await expect(positionsPanel(page).getByText("TSLA", { exact: true })).toBeVisible();
  await expect.poll(async () => Number((await headerCash(page).textContent())!)).toBeLessThan(before);
});

test("the assistant updates the watchlist and the change is visible in the grid", async ({ page }) => {
  await page.goto("/");

  await sendChat(page, "add SHOP to my watchlist");

  await expect(chatPanel(page).getByText("Added SHOP to your watchlist.")).toBeVisible();
  await expect(watchlistPanel(page).getByText("SHOP", { exact: true })).toBeVisible();

  await sendChat(page, "remove SHOP from my watchlist");

  await expect(chatPanel(page).getByText("Removed SHOP from your watchlist.")).toBeVisible();
  await expect(watchlistPanel(page).getByText("SHOP", { exact: true })).toHaveCount(0);
});

test("the conversation survives a page reload", async ({ page }) => {
  await page.goto("/");
  await sendChat(page, "buy 1 META");
  await expect(chatPanel(page).getByText("buy 1 META")).toBeVisible();

  await page.reload();

  // Replayed from GET /api/chat/history, including the stored action card.
  await expect(chatPanel(page).getByText("buy 1 META")).toBeVisible();
  await expect(chatPanel(page).getByText(/^Bought 1 META at \$/)).toBeVisible();
});
