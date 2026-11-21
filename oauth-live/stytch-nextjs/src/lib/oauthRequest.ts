/** OAuth request-shape checks before passing the request to Stytch.
 *  Stytch remains authoritative for client registration, callback, consent,
 *  OAuth response issuance and token signing. This is NOT an OAuth server.
 */
export const CANONICAL_RESOURCE = 'https://dan.panafor.com/mcp/';
/** Distinct synthetic-only resource. This audience cannot authorize production MCP. */
export const LIVE_SYNTHETIC_RESOURCE = 'https://panadan-mcp-live-synthetic.vercel.app/mcp/';
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
  if (resources.length !== 1 || ![CANONICAL_RESOURCE, LIVE_SYNTHETIC_RESOURCE].includes(resources[0]))
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

/**
 * Retain the pending OAuth request through B2B email OTP sign-in.
 *
 * sessionStorage is scoped to a browser tab. Some OTP/login flows complete
 * in another tab, where it is empty; a time-limited same-origin localStorage
 * backup preserves the exact validated OAuth request across that transition.
 * No authorization code or access token is ever stored here.
 */
export const RETURN_TO_BACKUP_KEY = 'panadan_live_oauth_return_to_backup';
export const RETURN_TO_MAX_AGE_MS = 10 * 60 * 1000;
type BrowserStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

type PendingReturn = { path: string; savedAt: number };

function tryRead(store: BrowserStore, key: string): string | null {
  try { return store.getItem(key); } catch { return null; }
}
function tryRemove(store: BrowserStore, key: string) {
  try { store.removeItem(key); } catch { /* Storage may be disabled. */ }
}
function validPending(raw: string | null, now: number): string | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    const { path, savedAt } = parsed as Partial<PendingReturn>;
    if (typeof path !== 'string' || typeof savedAt !== 'number' ||
        !Number.isFinite(savedAt) || savedAt > now ||
        now - savedAt > RETURN_TO_MAX_AGE_MS) return null;
    return safeReturnTo(path) === path ? path : null;
  } catch { return null; }
}

export function rememberAuthorizationReturnTo(
  path: string,
  sessionStore: BrowserStore,
  localStore: BrowserStore,
  now = Date.now(),
): boolean {
  if (path.length > 8192 || safeReturnTo(path) !== path) return false;
  const data = JSON.stringify({ path, savedAt: now } satisfies PendingReturn);
  let saved = false;
  for (const [store, key] of [
    [sessionStore, RETURN_TO_KEY],
    [localStore, RETURN_TO_BACKUP_KEY],
  ] as const) {
    try { store.setItem(key, data); saved = true; } catch { /* fallback store */ }
  }
  return saved;
}

export function readAuthorizationReturnTo(
  sessionStore: BrowserStore,
  localStore: BrowserStore,
  now = Date.now(),
): string {
  const primary = validPending(tryRead(sessionStore, RETURN_TO_KEY), now);
  const backup = validPending(tryRead(localStore, RETURN_TO_BACKUP_KEY), now);
  return primary ?? backup ?? '/';
}

export function clearAuthorizationReturnTo(
  sessionStore: BrowserStore,
  localStore: BrowserStore,
): void {
  tryRemove(sessionStore, RETURN_TO_KEY);
  tryRemove(localStore, RETURN_TO_BACKUP_KEY);
}
