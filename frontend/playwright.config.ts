import { defineConfig } from "@playwright/test";

/**
 * Browser end-to-end tests. Run with:  npm run e2e
 *
 * - Uses the Microsoft Edge already installed on Windows (no browser download).
 * - Starts its OWN API (port 8001, database inventory_e2e) and frontend (port 5174),
 *   so the main app and database are never touched.
 * - Tests run one after another because they share one database.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e-report" }]],
  use: {
    baseURL: "http://localhost:5174",
    channel: "msedge",
    headless: true,
    actionTimeout: 20_000,                  // a click that cannot happen fails quickly instead of hanging
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "..\\.venv\\Scripts\\python.exe ..\\backend\\scripts\\e2e_server.py --port 8001",
      url: "http://127.0.0.1:8001/api/v1/health",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npx vite --port 5174 --strictPort",
      url: "http://localhost:5174",
      env: { API_PROXY_TARGET: "http://127.0.0.1:8001" },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
