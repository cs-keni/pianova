import { defineConfig, devices } from "@playwright/test";

const apiPort = process.env.PIANOVA_E2E_API_PORT ?? "18080";
const apiURL = `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "node scripts/start-e2e-backend.mjs",
      url: `${apiURL}/api/health`,
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1",
      url: "http://127.0.0.1:3000",
      env: {
        NEXT_PUBLIC_PIANOVA_API_URL: apiURL,
      },
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
