import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  use: {
    baseURL: process.env.ASHANA_E2E_URL ?? "http://127.0.0.1:8080",
    trace: "retain-on-failure",
  },
  reporter: "list",
  // Routine runs use Chromium. The suite creates fixed-name data and uses login limits,
  // so each other browser runs on its own fresh stand: ASHANA_E2E_BROWSERS=webkit.
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ].filter(
    (p) =>
      process.env.ASHANA_E2E_BROWSERS === "all" ||
      (process.env.ASHANA_E2E_BROWSERS ?? "chromium")
        .split(",")
        .includes(p.name),
  ),
});
