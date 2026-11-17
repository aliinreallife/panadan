/** One-shot real Stytch Test JWT -> pinned synthetic staging MCP probe.
 * The access token is sent only to this fixed, operator-owned HTTPS resource.
 * Never log, echo, store or return the token, provider response or tool payload.
 */
export const STAGING_MCP_RESOURCE = 'https://panadan-mcp-oauth-staging.vercel.app/mcp/';

export type McpProbeResult = {
  status: 'accepted' | 'rejected' | 'unexpected' | 'unavailable';
  http_status: number | null;
  verified_by_resource: boolean;
};

export async function probeStytchTestMcp(
  accessToken: string,
  transport: typeof fetch = fetch,
): Promise<McpProbeResult> {
  if (!accessToken || accessToken.length > 12000) {
    return { status: 'unexpected', http_status: null, verified_by_resource: false };
  }
  try {
    const response = await transport(STAGING_MCP_RESOURCE, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + accessToken,
        'Content-Type': 'application/json',
        Accept: 'application/json, text/event-stream',
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'tools/call',
        params: { name: 'get_staging_access', arguments: {} },
      }),
      redirect: 'error',
      cache: 'no-store',
      signal: AbortSignal.timeout(12000),
    });

    if (response.status === 401 || response.status === 403) {
      return { status: 'rejected', http_status: response.status, verified_by_resource: false };
    }
    if (!response.ok) {
      return { status: 'unexpected', http_status: response.status, verified_by_resource: false };
    }

    // A 200 response by itself does not prove the MCP tool authorized access.
    // Require the exact expected synthetic response from the fixed tool.
    const raw = await response.text();
    if (raw.length > 10000) {
      return { status: 'unexpected', http_status: response.status, verified_by_resource: false };
    }
    let parsed: unknown;
    try { parsed = JSON.parse(raw); }
    catch {
      return { status: 'unexpected', http_status: response.status, verified_by_resource: false };
    }
    if (!parsed || typeof parsed !== 'object') {
      return { status: 'unexpected', http_status: response.status, verified_by_resource: false };
    }
    const rpc = parsed as Record<string, unknown>;
    const result = rpc.result;
    if (!result || typeof result !== 'object' || (result as Record<string, unknown>).isError === true) {
      return { status: 'unexpected', http_status: response.status, verified_by_resource: false };
    }
    const record = result as Record<string, unknown>;
    let value: unknown = record.structuredContent;
    if (!value && Array.isArray(record.content)) {
      const first = record.content[0] as Record<string, unknown> | undefined;
      if (first?.type === 'text' && typeof first.text === 'string' && first.text.length <= 5000) {
        try { value = JSON.parse(first.text); } catch { /* Unstructured tool output */ }
      }
    }
    const good = !!value && typeof value === 'object'
      && (value as Record<string, unknown>).environment === 'stytch-test'
      && (value as Record<string, unknown>).data === 'synthetic-only'
      && (value as Record<string, unknown>).actor === 'authorized-test-member';
    return {
      status: good ? 'accepted' : 'unexpected',
      http_status: response.status,
      verified_by_resource: good,
    };
  } catch {
    // Never surface or log exception details; some implementations embed headers.
    return { status: 'unavailable', http_status: null, verified_by_resource: false };
  }
}
