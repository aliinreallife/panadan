import test from 'node:test';
import assert from 'node:assert/strict';
import { validateAuthorizationParams, safeReturnTo, CANONICAL_RESOURCE, LIVE_SYNTHETIC_RESOURCE } from '../src/lib/oauthRequest.ts';
const good = () => new URLSearchParams({
  response_type: 'code',
  client_id: 'https://chatgpt.com/oauth/client.json',
  redirect_uri: 'https://chatgpt.com/connector_platform_oauth_redirect',
  code_challenge_method: 'S256',
  code_challenge: 'a'.repeat(43),
  scope: 'openid panadan:mcp:read',
  state: 'nonce-state-value-321',
  resource: CANONICAL_RESOURCE,
});
test('valid Live resource, scope and PKCE request', () => {
  assert.equal(validateAuthorizationParams('?' + good()), null);
  assert.equal(safeReturnTo('/oauth/authorize?' + good()), '/oauth/authorize?' + good());
});
test('wrong resource, scope, or PKCE fail closed', () => {
  for (const [field,value] of [
    ['resource','https://panadan-authz-integration-staging.vercel.app/mcp/'],
    ['resource','https://evil.example/mcp/'],
    ['scope','openid'],
    ['code_challenge_method','plain'],
    ['code_challenge','insecure'],
    ['response_type','token'],
  ]) {
    const p = good(); p.set(field,value);
    assert.notEqual(validateAuthorizationParams('?' + p),null,field);
  }
});
test('reject duplicates, arbitrary callbacks and missing state', () => {
  const p=good();p.append('client_id','other');
  assert.notEqual(validateAuthorizationParams('?' + p),null);
  const q=good();q.set('redirect_uri','javascript:alert(1)');
  assert.notEqual(validateAuthorizationParams('?' + q),null);
  const w=good();w.delete('state');
  assert.notEqual(validateAuthorizationParams('?' + w),null);
});
test('never resume login to external or invalid return paths', () => {
  for(const path of [null,'//evil.example','https://evil.example','/login','/oauth/authorize?state=bad'])
    assert.equal(safeReturnTo(path),'/');
});

test('only exact synthetic Live resource is additionally allowed', () => {
  const synthetic = good(); synthetic.set('resource', LIVE_SYNTHETIC_RESOURCE);
  assert.equal(validateAuthorizationParams('?' + synthetic), null);
  assert.equal(safeReturnTo('/oauth/authorize?' + synthetic),
               '/oauth/authorize?' + synthetic);
  const productionPlusSynthetic = good();
  productionPlusSynthetic.append('resource', LIVE_SYNTHETIC_RESOURCE);
  assert.notEqual(validateAuthorizationParams('?' + productionPlusSynthetic), null);
  for (const rejected of [
    LIVE_SYNTHETIC_RESOURCE.replace('/mcp/', '/mcp'),
    LIVE_SYNTHETIC_RESOURCE.replace('https:', 'http:'),
    'https://panadan-mcp-oauth-staging.vercel.app/mcp/',
    'https://dan.panafor.com/mcp-extra/',
  ]) {
    const q = good(); q.set('resource', rejected);
    assert.notEqual(validateAuthorizationParams('?' + q), null, rejected);
  }
});
