import test from 'node:test';
import assert from 'node:assert/strict';
import { isValidStytchTestPublicToken } from '../src/lib/stytchPublicToken.ts';

test('accepts a complete Stytch Test public token without exposing it', () => {
  assert.equal(isValidStytchTestPublicToken('public-token-test-123e4567-e89b-12d3-a456-426614174000'), true);
});
test('rejects wrong environment, placeholders, secrets and project IDs', () => {
  for (const token of [
    '', 'public-token-test-REPLACE_ME',
    'public-token-test-',
    'public-token-live-123e4567-e89b-12d3-a456-426614174000',
    'project-test-123e4567-e89b-12d3-a456-426614174000',
    'secret-test-123e4567-e89b-12d3-a456-426614174000',
  ]) assert.equal(isValidStytchTestPublicToken(token), false);
});
