/** A single explicitly owned HTTPS CIMD identifier for Test-only diagnostics.
 *
 * No arbitrary client metadata URLs are allowed through our token inspector.
 * The corresponding public JSON binds its callback to this exact origin.
 */
export const STAGING_CIMD_CLIENT_ID =
  'https://panadan-stytch-oauth-staging.vercel.app/.well-known/panadan-test-cimd.json';
export const STAGING_CIMD_REDIRECT_URI =
  'https://panadan-stytch-oauth-staging.vercel.app/oauth/test-callback';
