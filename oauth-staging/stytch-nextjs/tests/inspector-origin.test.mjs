import test from 'node:test';
import assert from 'node:assert/strict';
import {
  HOSTED_STAGING_ORIGIN, isAllowedInspectorOrigin, isAllowedInspectorClient,
} from '../src/lib/stytchInspectorOrigin.ts';

const client = 'connected-app-test-e2f5508f-e63e-4a7a-8fab-207276bda582';
const host = 'panadan-stytch-oauth-staging.vercel.app';

test('the local inspector remains local and origin/host matched', () => {
  for (const origin of ['http://127.0.0.1:3000', 'http://localhost:3000']) {
    assert.equal(isAllowedInspectorOrigin(origin, new URL(origin).host, undefined, false), true);
    assert.equal(isAllowedInspectorOrigin(origin, 'evil.example', undefined, false), false);
    assert.equal(isAllowedInspectorOrigin(origin, new URL(origin).host, undefined, true), false);
  }
});

test('hosted inspector requires exact HTTPS origin, host and opt-in', () => {
  assert.equal(isAllowedInspectorOrigin(HOSTED_STAGING_ORIGIN, host, HOSTED_STAGING_ORIGIN, true), true);
  for (const [origin, requestHost, enabledOrigin] of [
    [HOSTED_STAGING_ORIGIN, host, undefined],
    [HOSTED_STAGING_ORIGIN, host, 'https://other.vercel.app'],
    ['https://attacker.example', host, HOSTED_STAGING_ORIGIN],
    ['http://'+host, host, HOSTED_STAGING_ORIGIN],
    ['https://panadan-stytch-oauth-staging-preview.vercel.app', host, HOSTED_STAGING_ORIGIN],
    [HOSTED_STAGING_ORIGIN, 'other.vercel.app', HOSTED_STAGING_ORIGIN],
    [null, host, HOSTED_STAGING_ORIGIN],
  ]) assert.equal(isAllowedInspectorOrigin(origin, requestHost, enabledOrigin, true), false);
});

test('hosted diagnostics allow only pinned client or explicitly owned CIMD URL', () => {
  assert.equal(isAllowedInspectorClient(HOSTED_STAGING_ORIGIN, client, client), true);
  assert.equal(isAllowedInspectorClient(HOSTED_STAGING_ORIGIN, client, undefined), false);
  assert.equal(isAllowedInspectorClient(HOSTED_STAGING_ORIGIN, client, 'connected-app-test-other'), false);
  assert.equal(isAllowedInspectorClient(HOSTED_STAGING_ORIGIN, 'connected-app-test-11111111-2222-3333-4444-555555555555', client), false);
  assert.equal(isAllowedInspectorClient('http://127.0.0.1:3000', client, undefined), true);
});

test('hosted Test CIMD is exact and does not open arbitrary URL clients', async () => {
  const { STAGING_CIMD_CLIENT_ID } = await import('../src/lib/testCimdClient.ts');
  assert.equal(isAllowedInspectorClient(HOSTED_STAGING_ORIGIN, STAGING_CIMD_CLIENT_ID, client), true);
  assert.equal(isAllowedInspectorClient(HOSTED_STAGING_ORIGIN, STAGING_CIMD_CLIENT_ID, undefined), true);
  for (const untrusted of [
    'https://attacker.example/client.json',
    STAGING_CIMD_CLIENT_ID + '?version=2',
    STAGING_CIMD_CLIENT_ID.replace('https://', 'http://'),
    STAGING_CIMD_CLIENT_ID.replace('/.well-known/', '/different/'),
  ]) {
    assert.equal(isAllowedInspectorClient(HOSTED_STAGING_ORIGIN, untrusted, client), false);
  }
});
