import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const E2E_API_TOKEN = "playwright-test-token";
const E2E_API_PORT = process.env.QUANTBENCH_E2E_API_PORT ?? "18000";
const E2E_WEB_PORT = process.env.QUANTBENCH_E2E_WEB_PORT ?? "15173";
const E2E_QUANTBENCH_HOME =
  process.env.QUANTBENCH_E2E_HOME ?? path.resolve(process.cwd(), "..", ".playwright-quantbench-home");
process.env.QUANTBENCH_HOME = E2E_QUANTBENCH_HOME;

// End-to-end tests drive the real FastAPI backend and the real Vite dev
// server together (not mocks) - see e2e/global-setup.ts for how a fixture
// run gets seeded into the actual runs/ directory both processes read from.
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: `http://localhost:${E2E_WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `uv run uvicorn quantbench.api.server:app --port ${E2E_API_PORT}`,
      cwd: "..",
      env: {
        ...process.env,
        QUANTBENCH_HOME: E2E_QUANTBENCH_HOME,
        QUANTBENCH_API_TOKEN: E2E_API_TOKEN,
        QUANTBENCH_ALLOWED_ORIGINS: `http://localhost:${E2E_WEB_PORT},http://127.0.0.1:${E2E_WEB_PORT}`,
      },
      url: `http://localhost:${E2E_API_PORT}/api/runs?token=${E2E_API_TOKEN}`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `npm run dev -- --port ${E2E_WEB_PORT}`,
      env: {
        ...process.env,
        VITE_QUANTBENCH_API_BASE: `http://localhost:${E2E_API_PORT}/api`,
        VITE_QUANTBENCH_API_TOKEN: E2E_API_TOKEN,
      },
      url: `http://localhost:${E2E_WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
});
