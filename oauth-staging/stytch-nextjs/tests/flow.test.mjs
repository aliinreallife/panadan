import test from 'node:test';
import assert from 'node:assert/strict';
import { validateAuthorizationParams, safeReturnTo } from '../src/lib/flow.ts';

const good = '?client_id=client-test-abc&response_type=code&redirect_uri=https%3A%2F%2Fclient.example%2Fcallback&scope=openid%20panadan%3Amcp%3Aread&code_challenge_method=S256&code_challenge=' + 'a'.repeat(43);
test('accepts a well-shaped, scoped PKCE request', () => {
  assert.equal(validateAuthorizationParams(good), null);
  assert.equal(safeReturnTo('/oauth/authorize' + good), '/oauth/authorize' + good);
});
test('rejects missing scope, method, challenge and duplicate parameters', () => {
  assert.match(validateAuthorizationParams(good.replace('panadan%3Amcp%3Aread','email')), /scope/);
  assert.match(validateAuthorizationParams(good.replace('S256','plain')), /S256/);
  assert.match(validateAuthorizationParams(good.replace('a'.repeat(43),'short')), /challenge/);
  assert.match(validateAuthorizationParams(good + '&client_id=evil'), /client_id/);
});
test('does not accept arbitrary redirects or unvalidated return paths', () => {
  for (const p of [null, 'https://evil.example', '//evil.example', '/dashboard', '/oauth/authorize?client_id=x', '/oauth/authorize#fragment']) {
    assert.equal(safeReturnTo(p), '/');
  }
});
