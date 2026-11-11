import { test, expect } from '@playwright/test';

for (const route of ['/', '/login', '/oauth/test-client', '/oauth/test-callback']) {
  test('does not throw a module loader error on ' + route, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const response = await page.goto(route, { waitUntil: 'domcontentloaded' });
    expect(response?.status()).toBe(200);
    await expect(page.locator('h1')).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(1500);
    expect(errors.filter((e) =>
      /Cannot read properties of undefined \(reading ['"]call['"]\)|__webpack_require__|Failed to load chunk/i.test(e)
    )).toEqual([]);
  });
}


test('browser same-origin token inspection reaches configuration validation, not 403', async ({ page, request }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  const sameOriginStatus = await page.evaluate(async () => {
    const r = await fetch('/api/oauth/test-token-inspect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    return r.status;
  });
  // The CI job has no real Stytch Test Project ID, so we expect the explicit
  // configuration error rather than a rejected local browser origin.
  expect(sameOriginStatus).toBe(400);

  const rejected = await request.post('/api/oauth/test-token-inspect', {
    headers: { origin: 'https://attacker.example' },
    data: {},
  });
  expect(rejected.status()).toBe(403);
});
