import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalStytchTestRedirect, TEST_DISCOVERED_ISSUER, TEST_LEGACY_ISSUER } from '../src/lib/stytchTestIssuerCompat.ts';

const callback = 'http://localhost:6274/oauth/callback?client_param=keep';
const state = 'state123';

function providerResponse(issuer=TEST_LEGACY_ISSUER, code='fake-code-123') {
  const target = new URL(callback);
  target.searchParams.set('state', state);
  target.searchParams.set('code', code);
  target.searchParams.set('iss', issuer);
  return { redirect_uri: target.toString(), authorization_code: code };
}
test('canonicalizes only the known, Stytch-SDK-returned Test issuer', () => {
  const result = canonicalStytchTestRedirect(callback, state, providerResponse());
  const url = new URL(result);
  assert.equal(url.origin + url.pathname, 'http://localhost:6274/oauth/callback');
  assert.equal(url.searchParams.get('code'), 'fake-code-123');
  assert.equal(url.searchParams.get('state'), state);
  assert.equal(url.searchParams.get('iss'), TEST_DISCOVERED_ISSUER);
  assert.equal(url.searchParams.get('client_param'), 'keep');
  assert.equal(canonicalStytchTestRedirect(callback, state, providerResponse(TEST_DISCOVERED_ISSUER)), result);
});
test('rejects unrecognized issuer and missing or duplicated iss', () => {
  for (const issuer of ['https://attacker.example', 'https://viridian-faucet-2753.customers.stytch.dev.evil', '']) {
    assert.throws(() => canonicalStytchTestRedirect(callback, state, providerResponse(issuer)));
  }
  const missing = providerResponse();
  missing.redirect_uri = missing.redirect_uri.replace(/&iss=[^&]+/, '');
  assert.throws(() => canonicalStytchTestRedirect(callback, state, missing));
  const duplicate = providerResponse();
  duplicate.redirect_uri += '&iss=' + encodeURIComponent(TEST_DISCOVERED_ISSUER);
  assert.throws(() => canonicalStytchTestRedirect(callback, state, duplicate));
});
test('rejects redirect substitution, unexpected state, code mismatch and injection', () => {
  const hijack = providerResponse();
  hijack.redirect_uri = hijack.redirect_uri.replace('localhost:6274', 'evil.example');
  assert.throws(() => canonicalStytchTestRedirect(callback, state, hijack));
  const altered = providerResponse();
  altered.redirect_uri = altered.redirect_uri.replace('client_param=keep', 'client_param=evil');
  assert.throws(() => canonicalStytchTestRedirect(callback, state, altered));
  assert.throws(() => canonicalStytchTestRedirect(callback, 'attacker-state', providerResponse()));
  const mismatched = providerResponse();
  mismatched.authorization_code = 'different-code';
  assert.throws(() => canonicalStytchTestRedirect(callback, state, mismatched));
  const duplicatedCode = providerResponse();
  duplicatedCode.redirect_uri += '&code=another';
  assert.throws(() => canonicalStytchTestRedirect(callback, state, duplicatedCode));
  const fragment = providerResponse();
  fragment.redirect_uri += '#evil';
  assert.throws(() => canonicalStytchTestRedirect(callback, state, fragment));
  assert.throws(() => canonicalStytchTestRedirect('https://user:pass@client.example/cb', state, providerResponse()));
  assert.throws(() => canonicalStytchTestRedirect('http://evil.example/callback', state, providerResponse()));
  assert.throws(() => canonicalStytchTestRedirect(callback, '', providerResponse()));
});
