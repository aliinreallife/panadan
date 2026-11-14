import test from 'node:test';
import assert from 'node:assert/strict';
import { unverifiedMcpRejectionHints, STAGING_MCP_RESOURCE } from '../src/lib/stagingMcpRejectionHints.ts';

test('reports both independent issuer-side problems in the observed CIMD token', () => {
  const hints = unverifiedMcpRejectionHints({
    aud: ['project-test-5ce2a5ad-c6a8-4177-a6a4-a918c7add228'],
    ttl_seconds: 28800,
    scopes: ['openid', 'panadan:mcp:read'],
  });
  assert.equal(hints.length, 2);
  assert.match(hints[0], /Custom JWT Audience/);
  assert.match(hints[1], /60 minutes/);
});

test('keeps hints separate from security verification', () => {
  assert.deepEqual(unverifiedMcpRejectionHints(null), []);
  assert.deepEqual(unverifiedMcpRejectionHints({aud: [STAGING_MCP_RESOURCE], ttl_seconds: 3600}), []);
  assert.equal(unverifiedMcpRejectionHints({aud: [STAGING_MCP_RESOURCE], ttl_seconds: 28800}).length, 1);
  assert.equal(unverifiedMcpRejectionHints({aud: ['project-test'], ttl_seconds: 120}).length, 1);
  assert.equal(unverifiedMcpRejectionHints({aud: null, ttl_seconds: null}).length, 1);
});
