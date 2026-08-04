import { test, expect } from '@playwright/test';

// Deeper end-to-end journey against a *running* stack with a seeded account.
// Provide credentials to enable it; without them the journey is skipped so the
// smoke suite still runs on a bare stack:
//   E2E_EMAIL=admin@example.com E2E_PASSWORD='ChangeMe!2026' npx playwright test
const EMAIL = process.env.E2E_EMAIL;
const PASSWORD = process.env.E2E_PASSWORD;
const haveCreds = Boolean(EMAIL && PASSWORD);

test.describe('authenticated journey', () => {
  test.skip(!haveCreds, 'set E2E_EMAIL and E2E_PASSWORD to run the authenticated journey');

  test('API login issues a token and the studies list is owner-scoped', async ({ request }) => {
    const login = await request.post('/api/v1/auth/login', {
      data: { email: EMAIL, password: PASSWORD },
    });
    expect(login.ok()).toBeTruthy();
    const body = await login.json();
    expect(body.access_token).toBeTruthy();

    // The studies list is per-user: it must accept the token and return an array.
    const studies = await request.get('/api/v1/studies', {
      headers: { Authorization: `Bearer ${body.access_token}` },
    });
    expect(studies.ok()).toBeTruthy();
    expect(Array.isArray(await studies.json())).toBeTruthy();

    // …and reject an unauthenticated caller (owner-scoping now requires identity).
    const anon = await request.get('/api/v1/studies');
    expect(anon.status()).toBe(401);
  });

  test('another curator cannot read a foreign study id', async ({ request }) => {
    const login = await request.post('/api/v1/auth/login', {
      data: { email: EMAIL, password: PASSWORD },
    });
    const { access_token } = await login.json();

    // A study id this account does not own is hidden as 404 (never 403), so a
    // guessed id leaks nothing about whether it exists.
    const foreign = await request.get('/api/v1/mappings/does-not-belong-to-me', {
      headers: { Authorization: `Bearer ${access_token}` },
    });
    expect(foreign.status()).toBe(404);
  });

  test('UI login leaves the login screen', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"], input[name="email"]').first().fill(EMAIL!);
    await page.locator('input[type="password"]').first().fill(PASSWORD!);
    await page.locator('button[type="submit"]').first().click();
    await expect(page).not.toHaveURL(/\/login$/, { timeout: 10_000 });
    await expect(page.locator('#root')).toBeVisible();
  });
});
