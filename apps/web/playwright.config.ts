import { defineConfig, devices } from "@playwright/test";

const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8001";
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 3001);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  outputDir: "test-results",
  use: {
    launchOptions: { slowMo: 150 },
    baseURL: `http://localhost:${WEB_PORT}`,
    headless: process.env.CI === "true",
    viewport: { width: 1400, height: 900 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    { name: "chromium", use: {
    launchOptions: { slowMo: 150 }, ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: `npx next dev -p ${WEB_PORT}`,
    port: WEB_PORT,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
    env: {
      NEXT_PUBLIC_API_URL: API_URL,
      PORT: String(WEB_PORT),
    },
  },
});