import { expect, type Locator, type Page } from "@playwright/test";

export const DEFAULT_TICKERS = [
  "AAPL",
  "GOOGL",
  "MSFT",
  "AMZN",
  "TSLA",
  "NVDA",
  "META",
  "JPM",
  "V",
  "NFLX",
];

/** "$9,432.10" / "-$12.34" / "+1.20%" -> number. "—" -> NaN. */
export function parseMoney(text: string): number {
  const cleaned = text.replace(/[$,\s]/g, "").replace(/[^0-9.+-]/g, "");
  return Number(cleaned);
}

/** A header stat's value span, located via its uppercase-transformed label. */
export function headerStat(page: Page, label: string): Locator {
  return page
    .locator("header span.panel-title")
    .filter({ hasText: new RegExp(`^${label}$`, "i") })
    .locator("xpath=following-sibling::span");
}

export async function readCash(page: Page): Promise<number> {
  return parseMoney(await headerStat(page, "Cash").innerText());
}

export async function readTotalValue(page: Page): Promise<number> {
  return parseMoney(await headerStat(page, "Total Value").innerText());
}

/** A titled Panel section, e.g. panel(page, "Portfolio Heatmap"). */
export function panel(page: Page, title: string | RegExp): Locator {
  const matcher = typeof title === "string" ? new RegExp(title, "i") : title;
  return page
    .locator("section")
    .filter({ has: page.locator("h2.panel-title").filter({ hasText: matcher }) })
    .first();
}

export const connectionDot = (page: Page): Locator =>
  page.getByTestId("connection-dot");

export const watchRow = (page: Page, ticker: string): Locator =>
  page.getByTestId(`watch-row-${ticker}`);

export const positionRow = (page: Page, ticker: string): Locator =>
  page.getByTestId(`position-row-${ticker}`);

/** Wait for the app shell plus a live SSE connection and a seeded watchlist. */
export async function openTerminal(page: Page): Promise<void> {
  await page.goto("/");
  await expect(connectionDot(page)).toHaveAttribute("data-state", "connected");
  await expect(watchRow(page, "AAPL")).toBeVisible();
}

/**
 * Assert a locator's text actually changes — used to prove SSE ticks keep
 * arriving rather than merely that the stream opened once.
 */
export async function expectTextToChange(
  locator: Locator,
  timeout = 20_000,
): Promise<void> {
  const initial = await locator.innerText();
  await expect
    .poll(() => locator.innerText(), { timeout, intervals: [200] })
    .not.toBe(initial);
}

export type Side = "buy" | "sell";

/** Drive the trade ticket. Resolves once the ticket reports a terminal status. */
export async function submitTrade(
  page: Page,
  ticker: string,
  quantity: number,
  side: Side,
): Promise<string> {
  await page.getByLabel("Trade ticker").fill(ticker);
  await page.getByLabel("Trade quantity").fill(String(quantity));
  await page
    .getByRole("button", { name: side.toUpperCase(), exact: true })
    .click();

  const status = page.getByRole("status").filter({ hasText: /filled|reject|insufficient|enter a ticker/i });
  await expect(status).toBeVisible();
  return status.innerText();
}

export async function sendChat(page: Page, message: string): Promise<void> {
  await page.getByLabel("Chat message").fill(message);
  await page.getByRole("button", { name: "SEND" }).click();
}

export const lastAssistantMessage = (page: Page): Locator =>
  page.getByTestId("chat-assistant").last();

/** Console + page errors collected from now on, ignoring known-benign noise. */
export function collectPageErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (/favicon|icon\.svg/i.test(text)) return;
    errors.push(text);
  });
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  return errors;
}
