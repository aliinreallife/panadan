/**
 * Convert a Stytch/OAuth token failure to safe diagnostics without returning
 * untrusted provider error messages, URLs, HTML, or credential material.
 */
export function summarizeProviderFailure(
  httpStatus: number,
  contentType: string,
  rawBody: string,
): {
  provider_http_status: number;
  provider_response_kind: 'json' | 'non_json';
  provider_error_type: string | null;
  oauth_error: string | null;
  provider_request_id: string | null;
} {
  const diagnostic = {
    provider_http_status: httpStatus,
    provider_response_kind: 'non_json' as 'json' | 'non_json',
    provider_error_type: null as string | null,
    oauth_error: null as string | null,
    provider_request_id: null as string | null,
  };
  if (!contentType.toLowerCase().includes('json') || rawBody.length > 8192) return diagnostic;

  let parsed: unknown;
  try { parsed = JSON.parse(rawBody); }
  catch { return diagnostic; }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return diagnostic;

  diagnostic.provider_response_kind = 'json';
  const fields = parsed as Record<string, unknown>;
  const safeType = (value: unknown) =>
    typeof value === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(value) ? value : null;

  diagnostic.provider_error_type = safeType(fields.error_type);
  diagnostic.oauth_error = safeType(fields.error);
  diagnostic.provider_request_id = typeof fields.request_id === 'string'
    && /^request-id-test-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(fields.request_id)
    ? fields.request_id
    : null;
  return diagnostic;
}
