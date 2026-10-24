import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  use: {
    baseURL: process.env.ASHANA_E2E_URL ?? "http://127.0.0.1:8080",
    trace: "retain-on-failure",
  },
  reporter: "list",
  // Routine runs use Chromium; "chrome" is the installed Google Chrome the demo is shown in.
  // The suite creates fixed-name data and uses login limits, so each browser runs on its
  // own fresh stand: ASHANA_E2E_BROWSERS=chrome (or webkit). Firefox is not supported.
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    {
      name: "chrome",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ].filter((p) =>
    (process.env.ASHANA_E2E_BROWSERS ?? "chromium").split(",").includes(p.name),
  ),
});
