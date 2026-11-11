import test from 'node:test';
import assert from 'node:assert/strict';
import { probeStytchTestMcp, STAGING_MCP_RESOURCE } from '../src/lib/stytchStagingMcpProbe.ts';

const syntheticToken = 'synthetic-jwt-not-a-real-token';

test('probe sends bearer only to pinned HTTPS synthetic staging resource and hides it in output', async () => {
  let count = 0;
  const transport = async (url, init) => {
    count += 1;
    assert.equal(url, STAGING_MCP_RESOURCE);
    assert.equal(url, 'https://panadan-mcp-oauth-staging.vercel.app/mcp/');
    assert.equal(init.headers.Authorization, 'Bearer ' + syntheticToken);
    assert.equal(init.redirect, 'error');
    const body = JSON.parse(init.body);
    assert.equal(body.method, 'tools/call');
    assert.equal(body.params.name, 'get_staging_access');
    return new Response(JSON.stringify({
      jsonrpc: '2.0', id: 1,
      result: { structuredContent: {
        environment: 'stytch-test',
        data: 'synthetic-only',
        actor: 'authorized-test-member',
      } },
    }), { status: 200 });
  };
  const out = await probeStytchTestMcp(syntheticToken, transport);
  assert.equal(count, 1);
  assert.deepEqual(out, { status: 'accepted', http_status: 200, verified_by_resource: true });
  assert.doesNotMatch(JSON.stringify(out), /synthetic-jwt/);
});

test('probe fails closed on rejection, missing proof and network error', async () => {
  const unauthorized = await probeStytchTestMcp(syntheticToken, async () =>
    new Response('{"error":"unauthorized"}', {status:401}));
  assert.deepEqual(unauthorized, {status:'rejected',http_status:401,verified_by_resource:false});
  const falsePositive = await probeStytchTestMcp(syntheticToken, async () =>
    new Response(JSON.stringify({jsonrpc:'2.0',id:1,result:{content:[]}}), {status:200}));
  assert.equal(falsePositive.status, 'unexpected');
  assert.equal(falsePositive.verified_by_resource, false);
  const failed = await probeStytchTestMcp(syntheticToken, async () => {throw new Error('sensitive token');});
  assert.deepEqual(failed, {status:'unavailable',http_status:null,verified_by_resource:false});
  assert.doesNotMatch(JSON.stringify(failed), /sensitive/);
  const empty = await probeStytchTestMcp('', async () => {throw new Error('should not contact');});
  assert.equal(empty.status, 'unexpected');
});
