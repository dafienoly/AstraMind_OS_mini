import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  globalSetup: "./tests/e2e/global-setup.ts",
  timeout: 15_000,
  use: {
    baseURL: process.env.ASTRAMIND_E2E_BASE_URL ?? "http://127.0.0.1:5174",
    browserName: "chromium",
    trace: "retain-on-failure",
  },
  reporter: [["list"]],
});
