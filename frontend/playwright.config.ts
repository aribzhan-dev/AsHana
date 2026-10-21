import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  use: {
    baseURL: process.env.ASHANA_E2E_URL ?? "http://127.0.0.1:8080",
    trace: "retain-on-failure",
  },
  reporter: "list",
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
