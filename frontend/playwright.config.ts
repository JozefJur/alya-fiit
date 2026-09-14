import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";

/**
 * E2E configuration.
 *
 * Playwright starts both processes itself: the backend on a dedicated E2E
 * SQLite database (reset + seeded before the run) and a Vite dev server
 * proxying /api to it. That makes `npm run test:e2e` work identically on a
 * developer machine and in CI.
 *
 * Dedicated ports (8001 / 5174) and `reuseExistingServer: false` keep the run
 * isolated from a developer's own servers on 8000 / 5173 — reusing those would
 * silently test against the development database.
 */

const repoRoot = path.resolve(import.meta.dirname, "..");
const backendDir = path.join(repoRoot, "backend");
const e2eDatabase = path.join(backendDir, "data", "e2e.db");

// Prefer the project virtualenv; fall back to whatever python is on PATH.
const venvPython = path.join(
  backendDir,
  ".venv",
  process.platform === "win32" ? "Scripts" : "bin",
  process.platform === "win32" ? "python.exe" : "python"
);
const python = existsSync(venvPython) ? venvPython : "python3";

const backendEnv = {
  ...process.env,
  ALYA_DATABASE_URL: `sqlite:///${e2eDatabase.split(path.sep).join("/")}`,
  ALYA_JWT_SECRET: "e2e-secret-long-enough-for-hs256-hmac-keys",
};

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // one shared database — keep scenarios sequential
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8001`,
      cwd: backendDir,
      env: backendEnv,
      url: "http://127.0.0.1:8001/api/health",
      // Never reuse: a developer's own server would point at another database.
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 120_000,
    },
    {
      // --host pins IPv4: Vite otherwise binds ::1 only on some machines and
      // the 127.0.0.1 health check below would never succeed.
      command: "npm run dev -- --host 127.0.0.1 --port 5174 --strictPort",
      cwd: import.meta.dirname,
      env: { ...process.env, VITE_API_PROXY_TARGET: "http://127.0.0.1:8001" },
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 120_000,
    },
  ],
});
