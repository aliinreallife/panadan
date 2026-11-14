/** Trusted-local-config Stytch B2B Connected Apps discovery. */
export interface StytchOAuthMetadata {
  issuer?: unknown;
  token_endpoint?: unknown;
  jwks_uri?: unknown;
}
export function parseTestIssuer(value: string | undefined): URL {
  if (!value) throw new Error('missing_test_issuer');
  let parsed: URL;
  try { parsed = new URL(value); }
  catch { throw new Error('invalid_test_issuer'); }
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password
      || parsed.port || parsed.pathname !== '/' || parsed.search || parsed.hash
      || !parsed.hostname.includes('.') || parsed.hostname === 'localhost'
      || /^[0-9.]+$/.test(parsed.hostname) || parsed.hostname === 'test.stytch.com'
      || parsed.hostname === 'api.stytch.com') {
    throw new Error('invalid_test_issuer');
  }
  return parsed;
}
export function discoveredTokenEndpoint(issuer: URL, metadata: StytchOAuthMetadata): string {
  if (metadata.issuer !== issuer.origin) throw new Error('issuer_mismatch');
  if (typeof metadata.token_endpoint !== 'string') throw new Error('missing_token_endpoint');
  let url: URL;
  try { url = new URL(metadata.token_endpoint); }
  catch { throw new Error('invalid_token_endpoint'); }
  if (url.protocol !== 'https:' || url.origin !== issuer.origin
      || url.username || url.password || url.search || url.hash
      || url.pathname !== '/v1/oauth2/token') throw new Error('invalid_token_endpoint');
  return url.toString();
}
