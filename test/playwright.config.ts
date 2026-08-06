import { defineConfig, devices } from "@playwright/test";

// Paths here are resolved relative to THIS file, so they stay inside test/.
export default defineConfig({
  testDir: "./e2e",

  // Every spec shares one SQLite database inside one app container. Parallel
  // workers would race on cash and positions and produce failures that look
  // like application bugs.
  fullyParallel: false,
  workers: 1,

  // One retry for genuine infrastructure noise — but treat a test that only
  // passes on retry as a BUG REPORT, not a pass. This retry masked a
  // deterministic assertion error for the whole of Plan 05-04: the first
  // chat test failed on attempt 1 in every single run and passed on retry,
  // which read as flakiness and was recorded as such. It was not flaky. See
  // the sendChat comment in e2e/helpers.ts.
  retries: process.env.CI ? 1 : 0,
  reporter: [["html", { outputFolder: "artifacts/report", open: "never" }]],
  outputDir: "artifacts/results",

  use: {
    // Compose sets this to the app service's DNS name; the fallback lets a
    // developer point the same config at a container started by
    // scripts/start_mac.sh.
    baseURL: process.env.BASE_URL ?? "http://localhost:8000",
    trace: "on-first-retry",
  },

  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
