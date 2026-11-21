import test from 'node:test';
import assert from 'node:assert/strict';
import {
  rememberAuthorizationReturnTo,
  readAuthorizationReturnTo,
  clearAuthorizationReturnTo,
  RETURN_TO_KEY,
  RETURN_TO_BACKUP_KEY,
  RETURN_TO_MAX_AGE_MS,
  LIVE_SYNTHETIC_RESOURCE,
} from '../src/lib/oauthRequest.ts';

function store() {
  const data = new Map();
  return {
    getItem: key => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: key => data.delete(key),
  };
}

function oauthPath() {
  const query = new URLSearchParams({
    response_type: 'code',
    client_id: 'https://chatgpt.com/oauth/client.json',
    redirect_uri: 'https://chatgpt.com/connector_platform_oauth_redirect',
    code_challenge_method: 'S256',
    code_challenge: 'a'.repeat(43),
    scope: 'openid panadan:mcp:read',
    resource: LIVE_SYNTHETIC_RESOURCE,
    state: 'genuine-mcp-authorization-state-123',
  });
  return '/oauth/authorize?' + query;
}

test('save and resume the exact validated ChatGPT OAuth request', () => {
  const session = store(), local = store(), path = oauthPath();
  assert.equal(rememberAuthorizationReturnTo(path, session, local, 1000), true);
  assert.equal(readAuthorizationReturnTo(session, local, 1100), path);
  assert.ok(session.getItem(RETURN_TO_KEY));
  assert.ok(local.getItem(RETURN_TO_BACKUP_KEY));
  // Not consumed at login: allows another Stytch navigation to "/" to recover.
  assert.equal(readAuthorizationReturnTo(session, local, 1101), path);
  clearAuthorizationReturnTo(session, local);
  assert.equal(readAuthorizationReturnTo(session, local, 1102), '/');
});

test('restore after OTP opens a fresh browser tab without sessionStorage', () => {
  const originalTab = store(), newTab = store(), local = store();
  const path = oauthPath();
  assert.equal(rememberAuthorizationReturnTo(path, originalTab, local, 1500), true);
  assert.equal(readAuthorizationReturnTo(newTab, local, 1600), path);
  clearAuthorizationReturnTo(newTab, local);
  assert.equal(readAuthorizationReturnTo(newTab, local, 1601), '/');
});

test('expired or manipulated return targets fail closed', () => {
  const session = store(), local = store(), path = oauthPath();
  assert.equal(rememberAuthorizationReturnTo(path, session, local, 2000), true);
  assert.equal(readAuthorizationReturnTo(session, local, 2000 + RETURN_TO_MAX_AGE_MS + 1), '/');
  assert.equal(readAuthorizationReturnTo(session, local, 1000), '/');

  session.setItem(RETURN_TO_KEY, JSON.stringify({
    path: 'https://evil.example/steal', savedAt: 2000,
  }));
  local.removeItem(RETURN_TO_BACKUP_KEY);
  assert.equal(readAuthorizationReturnTo(session, local, 2100), '/');

  const modifiedQuery = new URLSearchParams(path.split('?')[1]);
  modifiedQuery.set('resource', 'https://evil.example/mcp/');
  session.setItem(RETURN_TO_KEY, JSON.stringify({
    path: '/oauth/authorize?' + modifiedQuery, savedAt: 2000,
  }));
  assert.equal(readAuthorizationReturnTo(session, local, 2100), '/');
  assert.equal(rememberAuthorizationReturnTo('/login', session, local, 2100), false);
});

test('continues safely if one storage type is blocked', () => {
  const blocked = {
    getItem() { throw new Error('Storage denied'); },
    setItem() { throw new Error('Storage denied'); },
    removeItem() { throw new Error('Storage denied'); },
  };
  const session = store(), local = store(), path = oauthPath();
  assert.equal(rememberAuthorizationReturnTo(path, blocked, local, 5000), true);
  assert.equal(readAuthorizationReturnTo(blocked, local, 5100), path);
  assert.equal(rememberAuthorizationReturnTo(path, session, blocked, 5000), true);
  assert.equal(readAuthorizationReturnTo(session, blocked, 5100), path);
  assert.equal(rememberAuthorizationReturnTo(path, blocked, blocked, 5000), false);
});
