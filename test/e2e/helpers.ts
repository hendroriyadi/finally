import type { Locator, Page } from "@playwright/test";
import { expect } from "@playwright/test";

// Not a spec: Playwright only collects files whose names carry a .spec/.test
// segment, so this module is imported and never run as a suite.
//
// Panels are scoped by their visible heading rather than by class name or DOM
// position, so restyling does not break the suite.

export function panel(page: Page, heading: string): Locator {
  return page.locator("section, aside").filter({ has: page.getByRole("heading", { name: heading }) });
}

export const watchlistPanel = (page: Page) => panel(page, "Watchlist");
export const positionsPanel = (page: Page) => panel(page, "Positions");
export const heatmapPanel = (page: Page) => panel(page, "Portfolio Heatmap");
export const pnlPanel = (page: Page) => panel(page, "Portfolio Value");
export const chatPanel = (page: Page) => panel(page, "AI Copilot");

/** The header figure that follows a given uppercase label. */
function headerFigure(page: Page, label: string): Locator {
  // following-sibling rather than a CSS "+ div": class-free and unambiguous.
  return page
    .locator("header")
    .getByText(label, { exact: true })
    .locator("xpath=following-sibling::div[1]");
}

export const headerPortfolioValue = (page: Page) => headerFigure(page, "PORTFOLIO VALUE");
export const headerCash = (page: Page) => headerFigure(page, "CASH");
export const connectionStatus = (page: Page) => page.getByRole("status");

// The trade bar and the add-ticker form share the placeholder "e.g. AAPL", so
// an unscoped query for it matches two elements and fails strict mode. Each
// input is reached through its own container.
// TradeBar's root is a <form> (IN-02 wrapped it to match AddTickerForm).
export const tradeBar = (page: Page) =>
  page.locator("form").filter({ has: page.getByRole("button", { name: "Buy", exact: true }) });

export const tradeTickerInput = (page: Page) => tradeBar(page).getByPlaceholder("e.g. AAPL");
export const tradeQuantityInput = (page: Page) => tradeBar(page).getByPlaceholder("Qty");
export const addTickerInput = (page: Page) => watchlistPanel(page).getByPlaceholder("e.g. AAPL");

// The chat textarea's placeholder ends in a single-character ellipsis, so
// match it with a regex rather than a literal.
export const chatInput = (page: Page) => chatPanel(page).getByPlaceholder(/^Ask FinAlly/);
export const chatSend = (page: Page) => chatPanel(page).getByRole("button", { name: "Send message" });

export const watchlistRow = (page: Page, ticker: string) =>
  watchlistPanel(page).getByRole("button", { name: new RegExp(`^${ticker}\\b`) });

/** Fill the trade bar and click a side. */
export async function trade(page: Page, ticker: string, quantity: string, side: "Buy" | "Sell") {
  await tradeTickerInput(page).fill(ticker);
  await tradeQuantityInput(page).fill(quantity);
  await tradeBar(page).getByRole("button", { name: side, exact: true }).click();
}

/** Send a chat message and wait for an assistant reply to appear. */
export async function sendChat(page: Page, message: string) {
  const before = await chatPanel(page).getByText("FINALLY").count();
  await chatInput(page).fill(message);
  await chatSend(page).click();
  await expect(chatPanel(page).getByText("FINALLY")).toHaveCount(before + 1, { timeout: 30_000 });
}
