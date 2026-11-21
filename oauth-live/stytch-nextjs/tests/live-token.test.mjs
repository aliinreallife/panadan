import test from 'node:test';
import assert from 'node:assert/strict';
import { isValidLivePublicToken } from '../src/lib/liveToken.ts';
test('only a Live public token can initialize the Live SDK', () => {
  assert.equal(isValidLivePublicToken('public-token-live-12345678-1234-1234-1234-123456789abc'),true);
  assert.equal(isValidLivePublicToken('public-token-test-12345678-1234-1234-1234-123456789abc'),false);
  assert.equal(isValidLivePublicToken('secret-live-12345678-1234-1234-1234-123456789abc'),false);
  assert.equal(isValidLivePublicToken('public-token-live-REPLACE_ME'),false);
});
