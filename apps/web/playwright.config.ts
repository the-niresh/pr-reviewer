import path from "path";
import { defineConfig, devices } from "@playwright/test";

const repoRoot = path.join(__dirname, "../..");
const localApi = process.env.NEXT_PUBLIC_LOCAL_API_ORIGIN ?? "http://127.0.0.1:8741";
const dashboardApi = process.env.NEXT_PUBLIC_DASHBOARD_API_ORIGIN ?? "http://127.0.0.1:8742";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: "bun run dev",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command:
        "uv run reviewer start --host 127.0.0.1 --port 8741 --hosted-origin https://control.example.test",
      cwd: repoRoot,
      url: `${localApi}/onboarding/mode`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "uv run python apps/web/tests/dashboard_api_server.py",
      cwd: repoRoot,
      url: `${dashboardApi}/dashboard/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
