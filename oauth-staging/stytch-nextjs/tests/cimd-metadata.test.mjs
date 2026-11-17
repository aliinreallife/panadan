import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { STAGING_CIMD_CLIENT_ID, STAGING_CIMD_REDIRECT_URI } from '../src/lib/testCimdClient.ts';

test('owned public CIMD metadata has RFC-compatible identifier and exact callback', () => {
  const path = new URL('../public/.well-known/panadan-test-cimd.json', import.meta.url);
  const metadata = JSON.parse(readFileSync(path, 'utf8'));
  assert.equal(metadata.client_id, STAGING_CIMD_CLIENT_ID);
  assert.equal(new URL(metadata.client_id).protocol, 'https:');
  assert.ok(new URL(metadata.client_id).pathname.length > 1);
  assert.deepEqual(metadata.redirect_uris, [STAGING_CIMD_REDIRECT_URI]);
  assert.equal(metadata.token_endpoint_auth_method, 'none');
  assert.deepEqual(metadata.grant_types, ['authorization_code']);
  assert.deepEqual(metadata.response_types, ['code']);
  assert.equal(metadata.client_uri, 'https://panadan-stytch-oauth-staging.vercel.app');
  assert.equal(metadata.scope, 'openid panadan:mcp:read');
  assert.equal(metadata.client_secret, undefined);
  assert.equal(metadata.jwks, undefined);
});
