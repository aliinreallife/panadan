import { NextRequest, NextResponse } from 'next/server';

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
  const allowedOrigins = new Set([
    'http://127.0.0.1:3000',
    'http://localhost:3000',
  ]);
  if (!browserOrigin || !allowedOrigins.has(browserOrigin)
    || requestHost !== new URL(browserOrigin).host)
    return errorResponse('This diagnostic endpoint is restricted to the local test origin.', 403);

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

  try {
    const result = await fetch('https://test.stytch.com/v1/public/' + projectId + '/oauth2/token', {
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

    // Never log the provider response or echo opaque error details; they may include tokens.
    if (!result.ok) return errorResponse('Stytch Test rejected the code exchange (HTTP ' + result.status + '). Start a fresh authorization and verify the configured Project ID.', 502);
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
    }, { headers: HEADERS });
  } catch {
    return errorResponse('Could not reach the Stytch Test token endpoint.', 502);
  }
}
