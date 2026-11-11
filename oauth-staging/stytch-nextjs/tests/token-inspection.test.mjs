import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const route = readFileSync(new URL('../src/app/api/oauth/test-token-inspect/route.ts', import.meta.url), 'utf8');
const config = readFileSync(new URL('../next.config.ts', import.meta.url), 'utf8');
const callback = readFileSync(new URL('../src/app/oauth/test-callback/page.tsx', import.meta.url), 'utf8');

test('token inspector never returns raw credentials or secrets', () => {
  assert.match(route, /jwt: safeDecodeUnverified\(token\)/);
  assert.doesNotMatch(route, /access_token:\s*token|refresh_token:\s*resultData\.refresh_token/);
  assert.match(route, /isAllowedInspectorOrigin/);
  assert.match(route, /isAllowedInspectorClient/);
  assert.match(route, /STYTCH_TEST_INSPECT_ORIGIN/);
  assert.match(route, /STYTCH_TEST_CLIENT_ID/);
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

test('optional live MCP verification remains opt-in and never returns bearer token', () => {
  assert.match(route, /data\.probe_mcp === true/);
  assert.match(route, /browserOrigin !== HOSTED_STAGING_ORIGIN/);
  assert.match(route, /await probeStytchTestMcp\(token\)/);
  assert.match(callback, /Exchange code &amp; test synthetic MCP/);
  assert.match(callback, /Inspect token only/);
  assert.match(callback, /mcp_probe: testSyntheticMcp/);
});
