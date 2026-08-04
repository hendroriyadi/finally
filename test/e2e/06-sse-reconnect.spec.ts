import { expect, test } from "@playwright/test";
import { connectionStatus } from "./helpers";

test("the stream reports connected, survives being cut, and recovers on its own", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await expect(connectionStatus(page)).toHaveAttribute("aria-label", "Connected");

  // Cut the stream at the network layer rather than stopping the container:
  // this exercises EventSource's own retry, which is the mechanism the app
  // relies on (there is no custom reconnect code by design).
  await context.route("**/api/stream/prices", (route) => route.abort());
  await expect(connectionStatus(page)).not.toHaveAttribute("aria-label", "Connected", {
    timeout: 30_000,
  });

  // Restore the route; the browser's native retry should reconnect with no
  // page reload and no user action.
  await context.unroute("**/api/stream/prices");
  await expect(connectionStatus(page)).toHaveAttribute("aria-label", "Connected", {
    timeout: 60_000,
  });
});
