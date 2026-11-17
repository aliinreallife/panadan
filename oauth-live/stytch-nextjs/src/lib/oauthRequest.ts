/** OAuth request-shape checks before passing the request to Stytch.
 *  Stytch remains authoritative for client registration, callback, consent,
 *  OAuth response issuance and token signing. This is NOT an OAuth server.
 */
export const CANONICAL_RESOURCE = 'https://dan.panafor.com/mcp/';
export const AUTHORIZATION_PATH = '/oauth/authorize';
export const RETURN_TO_KEY = 'panadan_live_oauth_return_to';

function exactlyOne(params: URLSearchParams, key: string): string | null {
  const values = params.getAll(key);
  return values.length === 1 ? values[0] : null;
}

export function validateAuthorizationParams(query: string): string | null {
  const params = new URLSearchParams(query);
  if (exactlyOne(params, 'response_type') !== 'code')
    return 'An OAuth authorization code is required.';
  const client = exactlyOne(params, 'client_id');
  if (!client || client.length > 2048 || /\s/.test(client))
    return 'Invalid OAuth client ID.';
  const callback = exactlyOne(params, 'redirect_uri');
  if (!callback || callback.length > 2048) return 'Missing OAuth callback.';
  try {
    const url = new URL(callback);
    if (!(url.protocol === 'https:' ||
          (url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname)))
        || url.username || url.password || url.hash)
      return 'Invalid OAuth callback.';
  } catch {
    return 'Invalid OAuth callback.';
  }
  if (exactlyOne(params, 'code_challenge_method') !== 'S256')
    return 'PKCE S256 is required.';
  if (!/^[a-zA-Z0-9_-]{43,128}$/.test(exactlyOne(params, 'code_challenge') || ''))
    return 'Invalid PKCE challenge.';
  const scopes = (exactlyOne(params, 'scope') || '').split(/\s+/).filter(Boolean);
  if (!scopes.includes('panadan:mcp:read'))
    return 'Panadan MCP read scope is required.';
  const resources = params.getAll('resource');
  if (resources.length > 1 || (resources.length === 1 && resources[0] !== CANONICAL_RESOURCE))
    return 'Unexpected MCP resource.';
  const state = exactlyOne(params, 'state');
  if (!state || state.length > 1024 || !/^[\x21-\x7e]+$/.test(state))
    return 'Invalid OAuth state.';
  if (params.getAll('nonce').length > 1 || params.getAll('prompt').length > 1)
    return 'Duplicate OAuth parameters.';
  return null;
}

export function safeReturnTo(value: string | null): string {
  if (!value || !value.startsWith(AUTHORIZATION_PATH + '?') || value.startsWith('//'))
    return '/';
  try {
    const url = new URL(value, 'https://panadan-live.local');
    if (url.origin !== 'https://panadan-live.local' ||
        url.pathname !== AUTHORIZATION_PATH ||
        validateAuthorizationParams(url.search)) return '/';
    return url.pathname + url.search;
  } catch {
    return '/';
  }
}
