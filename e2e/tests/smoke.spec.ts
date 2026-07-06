import { test, expect } from '@playwright/test';

// Happy-path smoke: the app shell loads and the API is reachable through the
// same origin. Deeper flows (login -> upload -> harmonize -> review -> export)
// build on this once a seeded staging account + KB snapshot are in place.

test('app shell loads', async ({ page }) => {
  const res = await page.goto('/');
  expect(res?.ok()).toBeTruthy();
  // The SPA mounts into #root (index.html).
  await expect(page.locator('#root')).toBeVisible();
});

test('backend health endpoint is reachable through the proxy', async ({ request }) => {
  const res = await request.get('/healthz');
  expect(res.ok()).toBeTruthy();
});

test('login screen is reachable', async ({ page }) => {
  await page.goto('/login');
  // A password field should be present on the auth screen.
  await expect(page.locator('input[type="password"]')).toBeVisible();
});
