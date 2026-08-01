import { defineConfig, devices } from "@playwright/test";

/**
 * The suite drives one shared, stateful backend (one portfolio, one watchlist),
 * so it runs serially and never retries — a retried mutating test would replay
 * against state its first attempt already changed.
 */
export default defineConfig({
  testDir: "./specs",
  outputDir: "./artifacts/results",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 20_000 },
  forbidOnly: Boolean(process.env.CI),
  reporter: [
    ["list"],
    ["html", { outputFolder: "artifacts/report", open: "never" }],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8100",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    viewport: { width: 1600, height: 1000 },
    actionTimeout: 15_000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          // Chromium silently upgrades http:// on a single-label host (the
          // compose service name "app") to https, which uvicorn rejects.
          args: [
            "--disable-features=HttpsUpgrades,HttpsFirstBalancedModeAutoEnable",
          ],
        },
      },
    },
  ],
});
