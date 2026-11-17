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

test('legacy authorization URL forwards to the Test-only issuer compatibility flow', async ({ page }) => {
  const observed: string[] = [];
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) observed.push(frame.url());
  });
  const query = new URLSearchParams({
    response_type: 'code',
    client_id: 'connected-app-test-example',
    redirect_uri: 'http://127.0.0.1:6274/oauth/callback',
    scope: 'openid panadan:mcp:read',
    code_challenge: 'a'.repeat(43),
    code_challenge_method: 'S256',
    state: 'regression-test-state',
  });
  const response = await page.goto('/oauth/authorize?' + query.toString(), { waitUntil: 'domcontentloaded' });
  expect(response?.status()).toBe(200);
  // The user may be sent to Test login immediately after reaching compat.
  // Record top-level navigations instead of asserting a stable final URL.
  await expect.poll(() => observed.some((u) => {
    try {
      const url = new URL(u);
      return url.pathname === '/oauth/authorize-compat' &&
        url.searchParams.get('state') === 'regression-test-state' &&
        url.searchParams.get('redirect_uri') === 'http://127.0.0.1:6274/oauth/callback';
    } catch { return false; }
  }), { timeout: 15_000 }).toBe(true);
  expect(observed.some(u => u.includes('evil.example'))).toBe(false);
});
