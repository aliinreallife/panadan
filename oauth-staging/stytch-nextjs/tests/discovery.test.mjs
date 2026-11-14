import test from 'node:test';
import assert from 'node:assert/strict';
import { parseTestIssuer, discoveredTokenEndpoint } from '../src/lib/stytchDiscovery.ts';

const issuer = 'https://example-project.customers.stytch.dev';
test('accepts the correct discovered Stytch Connected Apps endpoint', () => {
  const actual = parseTestIssuer(issuer);
  assert.equal(discoveredTokenEndpoint(actual, {
    issuer,
    token_endpoint: issuer + '/v1/oauth2/token',
  }), issuer + '/v1/oauth2/token');
});
test('rejects shared API host, local URLs, and invalid issuers', () => {
  for (const raw of [undefined, 'https://test.stytch.com', 'https://api.stytch.com',
    'http://example-project.customers.stytch.dev', 'http://localhost:3000',
    'https://127.0.0.1', 'https://example-project.customers.stytch.dev/abc']) {
    assert.throws(() => parseTestIssuer(raw));
  }
});
test('rejects issuer mismatches and foreign or unexpected token endpoints', () => {
  const configured = parseTestIssuer(issuer);
  for (const endpoint of [
    'https://test.stytch.com/v1/public/project-test-abc/oauth2/token',
    issuer + '/v1/public/project-test-abc/oauth2/token',
    'https://evil.example/v1/oauth2/token',
    issuer + '/v1/oauth2/token?secret=1',
    issuer.replace('https:', 'http:') + '/v1/oauth2/token',
  ]) assert.throws(() => discoveredTokenEndpoint(configured, {
    issuer, token_endpoint: endpoint,
  }));
  assert.throws(() => discoveredTokenEndpoint(configured, {
    issuer: 'https://different.customers.stytch.dev',
    token_endpoint: issuer + '/v1/oauth2/token',
  }));
});
