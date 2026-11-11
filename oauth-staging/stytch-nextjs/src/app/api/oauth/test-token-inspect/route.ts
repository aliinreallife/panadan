import { NextRequest, NextResponse } from 'next/server';
import { createHash } from 'node:crypto';
import { summarizeProviderFailure } from '@/lib/stytchErrors';
import { parseTestIssuer, discoveredTokenEndpoint, type StytchOAuthMetadata } from '@/lib/stytchDiscovery';
import { HOSTED_STAGING_ORIGIN, isAllowedInspectorOrigin, isAllowedInspectorClient } from '@/lib/stytchInspectorOrigin';
import { probeStytchTestMcp } from '@/lib/stytchStagingMcpProbe';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const PROJECT_TEST_ID = /^project-test-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const PUBLIC_CLIENT_ID = /^connected-app-test-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const PKCE_VERIFIER = /^[A-Za-z0-9._~-]{43,128}$/;
const HEADERS = { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' };

function errorResponse(detail: string, status: number) {
  return NextResponse.json({ status: 'error', detail }, { status, headers: HEADERS });
}

function safeDecodeUnverified(raw: string): Record<string, unknown> | null {
  if (raw.length > 12000 || raw.split('.').length !== 3) return null;
  try {
    const [header64, payload64] = raw.split('.');
    const header = JSON.parse(Buffer.from(header64, 'base64url').toString('utf8')) as Record<string, unknown>;
    const payload = JSON.parse(Buffer.from(payload64, 'base64url').toString('utf8')) as Record<string, unknown>;
    const get = (key: string) => typeof payload[key] === 'string' ? payload[key] : null;
    const audiences = payload.aud;
    const aud = typeof audiences === 'string' ? audiences
      : (Array.isArray(audiences) && audiences.every(a => typeof a === 'string') ? audiences : null);
    const scopes = payload.scope ?? payload.scp;
    const scopeList = typeof scopes === 'string' ? scopes.split(/\s+/)
      : (Array.isArray(scopes) ? scopes.filter(s => typeof s === 'string') : []);
    const iss = get('iss');
    return {
      alg: typeof header.alg === 'string' ? header.alg : null,
      kid_present: typeof header.kid === 'string',
      iss,
      issuer_is_https_url: typeof iss === 'string' && iss.startsWith('https://'),
      aud,
      scopes: scopeList,
      required_scope_present: scopeList.includes('panadan:mcp:read'),
      sub_present: typeof get('sub') === 'string',
      // Pseudonymous Test member binding for the separate staging MCP.
      // Decoded only, not proof of identity until resource verifies RS256.
      sub_sha256: get('sub') ? createHash('sha256').update(get('sub')!, 'utf8').digest('hex') : null,
      client_id: get('client_id'),
      azp: get('azp'),
      token_use: get('token_use'),
      iat: typeof payload.iat === 'number' ? payload.iat : null,
      exp: typeof payload.exp === 'number' ? payload.exp : null,
      ttl_seconds: typeof payload.iat === 'number' && typeof payload.exp === 'number'
        ? payload.exp - payload.iat : null,
    };
  } catch {
    return null;
  }
}

export async function POST(request: NextRequest) {
  // Never infer the browser-facing origin from request.nextUrl. Next.js 15
  // may normalize that origin to localhost even if the user is browsing
  // http://127.0.0.1:3000 (notably with Windows -> WSL2 port forwarding).
  // Check the actual browser Origin against the original Host header instead.
  const browserOrigin = request.headers.get('origin');
  const requestHost = request.headers.get('host');
  const hostedRuntime = process.env.VERCEL === '1' || Boolean(process.env.VERCEL_ENV);
  if (!isAllowedInspectorOrigin(
    browserOrigin, requestHost, process.env.STYTCH_TEST_INSPECT_ORIGIN, hostedRuntime,
  ))
    return errorResponse('Token inspection is restricted to the configured Test origin.', 403);

  const projectId = process.env.STYTCH_TEST_PROJECT_ID;
  if (!projectId || !PROJECT_TEST_ID.test(projectId))
    return errorResponse('Set STYTCH_TEST_PROJECT_ID to the Test Project ID in .env.local and restart Next.js.', 400);

  const contentType = request.headers.get('content-type') || '';
  if (!contentType.startsWith('application/json'))
    return errorResponse('Expected JSON request.', 415);
  if (Number(request.headers.get('content-length') || '0') > 10000)
    return errorResponse('Request is too large.', 413);

  let data: Record<string, unknown>;
  try { data = await request.json() as Record<string, unknown>; }
  catch { return errorResponse('Invalid JSON.', 400); }

  const code = data.code;
  const verifier = data.code_verifier;
  const clientId = data.client_id;
  const redirect = data.redirect_uri;
  if (typeof code !== 'string' || !/^[A-Za-z0-9._~-]{12,4096}$/.test(code)
    || typeof verifier !== 'string' || !PKCE_VERIFIER.test(verifier)
    || typeof clientId !== 'string' || !PUBLIC_CLIENT_ID.test(clientId)
    || typeof redirect !== 'string' || redirect !== browserOrigin + '/oauth/test-callback')
    return errorResponse('Malformed one-time code, PKCE verifier, client ID or callback.', 400);

  if (!isAllowedInspectorClient(browserOrigin, clientId, process.env.STYTCH_TEST_CLIENT_ID))
    return errorResponse('This Connected App is not authorized for hosted Test diagnostics.', 403);

  // Never forward localhost or arbitrary client requests to the remote MCP staging service.
  if (data.probe_mcp === true && browserOrigin !== HOSTED_STAGING_ORIGIN)
    return errorResponse('MCP probing is restricted to the configured HTTPS Test host.', 403);


  // Use this B2B project's published OAuth endpoint instead of a shared
  // public/M2M endpoint. Issuer is explicitly configured locally, never client-supplied.
  let issuer: URL;
  try { issuer = parseTestIssuer(process.env.STYTCH_TEST_ISSUER_URL); }
  catch {
    return errorResponse('Set STYTCH_TEST_ISSUER_URL to your Stytch Test Project Domain (https://...customers.stytch.dev) in .env.local and restart.', 400);
  }
  let tokenEndpoint: string;
  try {
    const metadataResponse = await fetch(new URL('/.well-known/oauth-authorization-server', issuer), {
      headers: { Accept: 'application/json' }, redirect: 'error', cache: 'no-store',
      signal: AbortSignal.timeout(12000),
    });
    if (!metadataResponse.ok)
      return errorResponse('Stytch Test OAuth discovery failed (HTTP ' + metadataResponse.status + '). Confirm the Test Project Domain.', 502);
    const metadata = await metadataResponse.json() as StytchOAuthMetadata;
    tokenEndpoint = discoveredTokenEndpoint(issuer, metadata);
  } catch {
    return errorResponse('Stytch Test discovery could not verify the issuer and token endpoint. Check STYTCH_TEST_ISSUER_URL.', 502);
  }

  try {
    const result = await fetch(tokenEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'authorization_code',
        client_id: clientId,
        redirect_uri: redirect,
        code,
        code_verifier: verifier,
      }),
      cache: 'no-store',
      signal: AbortSignal.timeout(15000),
    });

    // Read error details only to extract allowlisted identifiers. Provider
    // messages and response bodies may be sensitive, so never echo/log them.
    if (!result.ok) {
      const rawBody = await result.text();
      const safe = summarizeProviderFailure(
        result.status,
        result.headers.get('content-type') || '',
        rawBody,
      );
      return NextResponse.json({
        status: 'error',
        detail: 'Stytch Test rejected the code exchange. Start a fresh authorization after checking the diagnostic values.',
        ...safe,
      }, { status: 502, headers: HEADERS });
    }
    const resultData = await result.json() as Record<string, unknown>;
    const token = resultData.access_token;
    if (typeof token !== 'string' || !token)
      return errorResponse('Stytch returned no access token.', 502);

    return NextResponse.json({
      status: 'ok',
      access_token_format: token.split('.').length === 3 ? 'jwt' : 'opaque',
      token_type: typeof resultData.token_type === 'string' ? resultData.token_type : null,
      expires_in: typeof resultData.expires_in === 'number' ? resultData.expires_in : null,
      refresh_token_returned: typeof resultData.refresh_token === 'string',
      jwt: safeDecodeUnverified(token),
      mcp_probe: data.probe_mcp === true ? await probeStytchTestMcp(token) : null,
    }, { headers: HEADERS });
  } catch {
    return errorResponse('Could not reach the Stytch Test token endpoint.', 502);
  }
}
