/** Stytch Test-only, explicitly trusted issuer compatibility boundary.
 *
 * Stytch's headless SDK returns a redirect URI after it accepts an OAuth
 * authorization request. Some Test versions return their legacy internal
 * issuer in the authorization response while public discovery advertises
 * a project-domain HTTPS issuer.
 *
 * NEVER normalize arbitrary values, client-provided redirect URLs, or
 * messages received directly at a callback endpoint. Only call this with
 * the return value of the approved Stytch Test SDK's authorize-submit API
 * after its authorize-start preflight and a logged-in Test member consent.
 * Revisit/remove this compatibility shim once Stytch fixes the issuer.
 */
export const TEST_DISCOVERED_ISSUER = 'https://viridian-faucet-2753.customers.stytch.dev';
export const TEST_LEGACY_ISSUER = 'stytch.com/project-test-5ce2a5ad-c6a8-4177-a6a4-a918c7add228';

type ApprovedResponse = { redirect_uri: string; authorization_code?: string };

export function canonicalStytchTestRedirect(
  requestedRedirectUri: string,
  requestedState: string,
  providerResponse: ApprovedResponse,
): string {
  if (!requestedState || requestedState.length > 512 || /[\r\n]/.test(requestedState)) {
    throw new Error('missing_oauth_state');
  }
  const before = new URL(requestedRedirectUri);
  const after = new URL(providerResponse.redirect_uri);

  const validProtocol = before.protocol === 'https:' || (
    before.protocol === 'http:' &&
    (before.hostname === 'localhost' || before.hostname === '127.0.0.1')
  );
  if (!validProtocol || before.username || before.password || before.hash || after.hash
      || after.username || after.password || before.protocol !== after.protocol
      || before.host !== after.host || before.pathname !== after.pathname) {
    throw new Error('oauth_redirect_mismatch');
  }
  // Even if the callback contained pre-existing query parameters, the
  // provider must return them without changing their values or cardinality.
  for (const key of new Set(before.searchParams.keys())) {
    const initial = before.searchParams.getAll(key);
    const returned = after.searchParams.getAll(key);
    if (initial.length !== returned.length || initial.some((x, i) => x !== returned[i])) {
      throw new Error('oauth_redirect_query_mismatch');
    }
  }
  const singleton = (key: string) => {
    const values = after.searchParams.getAll(key);
    return values.length === 1 ? values[0] : null;
  };
  const code = singleton('code');
  if (!code || code.length > 4096 || !/^[A-Za-z0-9._~-]+$/.test(code)
      || singleton('state') !== requestedState
      || (providerResponse.authorization_code && providerResponse.authorization_code !== code)
      || after.searchParams.has('error')) {
    throw new Error('oauth_response_mismatch');
  }
  const issuer = singleton('iss');
  if (issuer !== TEST_LEGACY_ISSUER && issuer !== TEST_DISCOVERED_ISSUER) {
    throw new Error('unexpected_provider_issuer');
  }
  // This is NOT a general issuer rewrite or a bypass of RFC 9207 client
  // validation: the Stytch Test SDK response and its exact legacy issuer
  // have been pinned first, with strict code/state/callback checks.
  after.searchParams.set('iss', TEST_DISCOVERED_ISSUER);
  return after.toString();
}
