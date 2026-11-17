import test from 'node:test';
import assert from 'node:assert/strict';
import { summarizeProviderFailure } from '../src/lib/stytchErrors.ts';

test('diagnoses a structured Stytch Test error without leaking messages', () => {
  const error = summarizeProviderFailure(403, 'application/json', JSON.stringify({
    status_code: 403,
    error_type: 'permission_denied',
    error: 'invalid_grant',
    request_id: 'request-id-test-123e4567-e89b-12d3-a456-426614174000',
    error_message: 'secret-token-do-not-display',
    access_token: 'secret-token-do-not-display',
  }));
  assert.deepEqual(error, {
    provider_http_status: 403,
    provider_response_kind: 'json',
    provider_error_type: 'permission_denied',
    oauth_error: 'invalid_grant',
    provider_request_id: 'request-id-test-123e4567-e89b-12d3-a456-426614174000',
  });
  assert.doesNotMatch(JSON.stringify(error), /secret-token-do-not-display/);
});

test('does not copy HTML proxy error bodies or arbitrary strings', () => {
  const html = summarizeProviderFailure(403, 'text/html', '<html>Secret hello</html>');
  assert.equal(html.provider_response_kind, 'non_json');
  assert.equal(html.provider_error_type, null);
  assert.doesNotMatch(JSON.stringify(html), /Secret hello/);

  const json = summarizeProviderFailure(403, 'application/json', JSON.stringify({
    error_type: 'error with spaces and secret=abc',
    request_id: 'request-id-live-123e4567-e89b-12d3-a456-426614174000',
  }));
  assert.equal(json.provider_error_type, null);
  assert.equal(json.provider_request_id, null);
});
