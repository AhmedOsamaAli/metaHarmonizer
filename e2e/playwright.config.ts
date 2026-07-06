import { defineConfig, devices } from '@playwright/test';

// End-to-end smoke tests run against a *running* stack (dev compose or staging),
// not the unit-test harness. Point them at the base URL via E2E_BASE_URL
// (default http://localhost:8080 — the Caddy origin from docker-compose).
export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
