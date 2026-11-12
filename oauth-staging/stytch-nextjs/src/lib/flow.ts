/** Minimal request-shape validation; Stytch remains the actual OAuth authority. */
export const RETURN_TO_KEY = 'panadan_stytch_oauth_return_to';
export const CANONICAL_TEST_RESOURCE = 'https://panadan-mcp-oauth-staging.vercel.app/mcp/';

export function validateAuthorizationParams(query: string): string | null {
  const params = new URLSearchParams(query);
  const one = (key: string) => {
    const values = params.getAll(key);
    return values.length === 1 ? values[0] : null;
  };
  if (one('response_type') !== 'code') return 'Authorization code response is required.';
  if (!one('client_id')) return 'Missing OAuth client_id.';
  const resources = params.getAll('resource');
  if (resources.length > 1 || (resources.length === 1 && resources[0] !== CANONICAL_TEST_RESOURCE))
    return 'Unexpected OAuth resource indicator.';
  if (!one('redirect_uri')) return 'Missing OAuth redirect_uri.';
  if (one('code_challenge_method') !== 'S256') return 'PKCE S256 is required.';
  const challenge = one('code_challenge');
  if (!challenge || !/^[A-Za-z0-9_-]{43,128}$/.test(challenge))
    return 'Missing or malformed PKCE challenge.';
  const scopes = (one('scope') || '').split(/\s+/).filter(Boolean);
  if (!scopes.includes('panadan:mcp:read'))
    return 'This test flow requires the Panadan MCP scope.';
  return null;
}

/** Prevent sessionStorage return paths from becoming open redirects. */
export function safeReturnTo(value: string | null): string {
  if (!value || !(value.startsWith('/oauth/authorize?') || value.startsWith('/oauth/authorize-compat?')) || value.startsWith('//'))
    return '/';
  try {
    const url = new URL(value, 'http://localhost');
    if (url.origin !== 'http://localhost' || !['/oauth/authorize', '/oauth/authorize-compat'].includes(url.pathname))
      return '/';
    return validateAuthorizationParams(url.search) === null
      ? url.pathname + url.search
      : '/';
  } catch {
    return '/';
  }
}
