/** Small, Test-only boundary for the OAuth token-inspection diagnostic.
 * The Origin + Host checks are CSRF/misrouting defenses, NOT authentication.
 * Stytch still validates the authorization code and PKCE verifier.
 */
export const HOSTED_STAGING_ORIGIN = 'https://panadan-stytch-oauth-staging.vercel.app';
const LOCAL_ORIGINS = new Set([
  'http://127.0.0.1:3000',
  'http://localhost:3000',
]);
import { STAGING_CIMD_CLIENT_ID } from './testCimdClient';

const TEST_CLIENT_ID = /^connected-app-test-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

export function isAllowedInspectorOrigin(
  browserOrigin: string | null,
  requestHost: string | null,
  configuredHostedOrigin: string | undefined,
  isHostedRuntime: boolean,
): boolean {
  if (!browserOrigin || !requestHost) return false;
  if (!isHostedRuntime && LOCAL_ORIGINS.has(browserOrigin)) {
    return requestHost === new URL(browserOrigin).host;
  }
  // Fail closed: never accept deployment-preview domains, external origins,
  // arbitrary Vercel aliases, or a missing/incorrect environment setting.
  return browserOrigin === HOSTED_STAGING_ORIGIN
    && configuredHostedOrigin === HOSTED_STAGING_ORIGIN
    && requestHost === new URL(HOSTED_STAGING_ORIGIN).host;
}

export function isAllowedInspectorClient(
  browserOrigin: string | null,
  clientId: string,
  configuredTestClientId: string | undefined,
): boolean {
  if (browserOrigin !== HOSTED_STAGING_ORIGIN) return true;
  // The one self-owned HTTPS CIMD metadata document is explicitly allowed;
  // never accept arbitrary URL-form client IDs from untrusted browsers.
  if (clientId === STAGING_CIMD_CLIENT_ID) return true;
  // The existing manual-client baseline is otherwise unchanged.
  return !!configuredTestClientId && TEST_CLIENT_ID.test(configuredTestClientId)
    && clientId === configuredTestClientId;
}
