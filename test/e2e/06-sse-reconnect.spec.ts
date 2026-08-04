import { expect, test } from "@playwright/test";
import { connectionStatus } from "./helpers";

// Two mechanisms were tried and rejected before this one, both recorded so
// nobody re-attempts them:
//
//   context.route(...).abort()  — only intercepts NEW requests. The
//     EventSource is already open by the time it is installed, so the live
//     stream is untouched and the status never changes.
//   context.setOffline(true)    — does not tear down an already-established
//     EventSource in this Chromium build. Measured: the status still read
//     "Connected" after 10s offline.
//
// So the stream is broken BEFORE the page opens it, then released. That
// exercises the same property the requirement cares about — the app recovers
// on its own, with no reload and no user action — because this app has no
// custom reconnect code at all: recovery is EventSource's native retry,
// driven by the server's `retry:` directive.

test("the stream recovers on its own after failing, with no reload", async ({ page, context }) => {
  let blocked = true;
  await context.route("**/api/stream/prices", async (route) => {
    if (blocked) {
      await route.abort();
    } else {
      await route.fallback();
    }
  });

  await page.goto("/");

  // The stream cannot connect, and the app says so rather than lying.
  await expect(connectionStatus(page)).not.toHaveAttribute("aria-label", "Connected", {
    timeout: 30_000,
  });

  // Release it. No reload, no click.
  blocked = false;

  await expect(connectionStatus(page)).toHaveAttribute("aria-label", "Connected", {
    timeout: 60_000,
  });

  // And it is genuinely streaming again, not merely reporting a status: a
  // price cell leaves its placeholder.
  await expect
    .poll(
      async () => {
        const cells = await page.locator("div.tabular-nums").allTextContents();
        return cells.filter((t) => t.trim() !== "—" && t.trim() !== "").length;
      },
      { timeout: 30_000 },
    )
    .toBeGreaterThan(0);
});
