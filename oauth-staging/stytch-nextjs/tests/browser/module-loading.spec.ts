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
