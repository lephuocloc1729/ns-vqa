import { defineConfig, devices } from "@playwright/test";

// The real API with a fake pipeline (e2e/fake_api.py, no Claude calls) and the Vite dev server
// proxying to it. PYTHON picks the interpreter (default: the repo's .venv).
const API_PORT = 8765;
const WEB_PORT = 5174;
const python = process.env.PYTHON ?? "../.venv/bin/python";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, trace: "retain-on-failure", locale: "vi-VN" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: `${python} e2e/fake_api.py --port ${API_PORT}`,
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort --host 127.0.0.1`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      env: { VQA_API_URL: `http://127.0.0.1:${API_PORT}` },
      reuseExistingServer: !process.env.CI,
    },
  ],
});
