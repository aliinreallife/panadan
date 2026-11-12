/** Diagnostic hints from UNVERIFIED decoded Test JWT metadata.
 *
 * Never use these hints for authorization. The independent Python MCP
 * resource validates RS256 signature, issuer, audience, scope and TTL.
 */
export const STAGING_MCP_RESOURCE = 'https://panadan-mcp-oauth-staging.vercel.app/mcp/';
export const STAGING_MCP_MAX_TTL_SECONDS = 3600;

export function unverifiedMcpRejectionHints(jwt: Record<string, unknown> | null | undefined): string[] {
  if (!jwt) return [];
  const hints: string[] = [];
  const rawAudience = jwt.aud;
  const audiences = typeof rawAudience === 'string'
    ? [rawAudience]
    : Array.isArray(rawAudience) && rawAudience.every(value => typeof value === 'string')
      ? rawAudience as string[] : [];
  if (!audiences.includes(STAGING_MCP_RESOURCE)) {
    hints.push('Missing MCP resource audience. In Stytch Test, edit this dynamically discovered Connected App and set Custom JWT Audience to the exact staging /mcp/ URL.');
  }
  const ttl = jwt.ttl_seconds;
  if (typeof ttl === 'number' && Number.isFinite(ttl) && ttl > STAGING_MCP_MAX_TTL_SECONDS) {
    hints.push('Access token lifetime exceeds the staging limit. Set Access Token Expiry to 60 minutes or less in this Stytch Test Connected App.');
  }
  return hints;
}
