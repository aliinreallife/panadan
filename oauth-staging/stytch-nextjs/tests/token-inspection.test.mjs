import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const route = readFileSync(new URL('../src/app/api/oauth/test-token-inspect/route.ts', import.meta.url), 'utf8');
const config = readFileSync(new URL('../next.config.ts', import.meta.url), 'utf8');
const callback = readFileSync(new URL('../src/app/oauth/test-callback/page.tsx', import.meta.url), 'utf8');

test('token inspector never returns raw credentials or secrets', () => {
  assert.match(route, /jwt: safeDecodeUnverified\(token\)/);
  assert.doesNotMatch(route, /access_token:\s*token|refresh_token:\s*resultData\.refresh_token/);
  assert.match(route, /'127\.0\.0\.1', 'localhost'/);
  assert.match(route, /STYTCH_TEST_PROJECT_ID/);
});
test('callback validates state and erases code URL before exchange', () => {
  assert.match(callback, /stored\.state !== state/);
  assert.match(callback, /window\.history\.replaceState/);
  assert.match(callback, /setPending\(null\)/);
});
test('dev request logging is disabled to avoid printing OAuth codes', () => {
  assert.match(config, /logging: \{ incomingRequests: false \}/);
  assert.match(config, /Referrer-Policy/);
});
