import type { Locator, Page } from "@playwright/test";
import { expect } from "@playwright/test";

// Not a spec: Playwright only collects files whose names carry a .spec/.test
// segment, so this module is imported and never run as a suite.
//
// Panels are scoped by their visible heading rather than by class name or DOM
// position, so restyling does not break the suite.

export function panel(page: Page, heading: string): Locator {
  // exact:true is load-bearing. Playwright's `name` option is a SUBSTRING,
  // case-insensitive match by default, so name:"Positions" also matches the
  // heatmap's "No open positions" heading — resolving to two sections and
  // failing strict mode.
  return page
    .locator("section, aside")
    .filter({ has: page.getByRole("heading", { name: heading, exact: true }) });
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
  watchlistPanel(page).getByRole("button", { name: new RegExp(`^${ticker}`) });

/**
 * Click a control on this page.
 *
 * `dispatchEvent("click")` rather than `.click()` is not a shortcut — it is
 * required here. The whole page re-renders on every SSE frame (~500ms), so
 * Playwright's actionability check never observes the two consecutive stable
 * animation frames it requires and a plain click times out after 30s.
 * Measured: plain click fails at 12s, dispatchEvent succeeds in 29ms.
 *
 * dispatchEvent bypasses the disabled check too, so callers assert
 * toBeEnabled() first — otherwise a test could "click" a disabled control
 * and silently pass.
 */
export async function clickLive(locator: Locator) {
  await expect(locator).toBeEnabled();
  await locator.dispatchEvent("click");
}

/** Fill the trade bar and click a side. */
export async function trade(page: Page, ticker: string, quantity: string, side: "Buy" | "Sell") {
  await tradeTickerInput(page).fill(ticker);
  await tradeQuantityInput(page).fill(quantity);
  await clickLive(tradeBar(page).getByRole("button", { name: side, exact: true }));
}

/** Send a chat message and wait for an assistant reply to appear. */
export async function sendChat(page: Page, message: string) {
  // Wait for the mount history fetch to settle BEFORE counting. Without
  // this the baseline is read while the skeleton is still up, history then
  // lands and adds its own assistant rows, and the +1 assertion never
  // matches — a race that shows up as an intermittent 30s timeout rather
  // than as anything resembling a chat bug.
  await expect(chatPanel(page).locator(".animate-pulse")).toHaveCount(0, { timeout: 30_000 });

  // exact:true is load-bearing. Playwright's getByText(string) is a
  // CASE-INSENSITIVE SUBSTRING match, so a bare "FINALLY" also matches the
  // empty-state copy "Start chatting with FinAlly". On an empty conversation
  // that made `before` 1 instead of 0; the send then replaced the empty state
  // with one assistant label, leaving the count at 1 while the assertion
  // waited for 2. It passed on retry only because the history was no longer
  // empty by then — which is exactly what made it look like a flake.
  const before = await chatPanel(page).getByText("FINALLY", { exact: true }).count();
  await chatInput(page).fill(message);
  // Proof that React has hydrated and owns this input: the controlled value
  // only reads back if the change handler ran. dispatchEvent bypasses
  // actionability, so without this gate a click can land before hydration
  // and silently do nothing — which surfaced as the first chat test failing
  // on a cold page and passing on retry.
  await expect(chatInput(page)).toHaveValue(message);
  // Enter, not a click on the send button. The send control is
  // type="submit", and submission is its DEFAULT ACTION — which
  // dispatchEvent deliberately does not perform, so a dispatched click can
  // fire the event and still never submit the form. Enter is both the real
  // user gesture (ChatPanel handles it explicitly) and the reliable one.
  await chatInput(page).press("Enter");
  await expect(chatPanel(page).getByText("FINALLY", { exact: true })).toHaveCount(before + 1, {
    timeout: 30_000,
  });
}
