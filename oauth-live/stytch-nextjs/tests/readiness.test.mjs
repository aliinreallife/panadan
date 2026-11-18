import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('readiness route reports only non-sensitive setup state', () => {
  const source = readFileSync(new URL('../src/app/api/status/route.ts', import.meta.url), 'utf8');
  assert.match(source, /isValidLivePublicToken/);
  assert.match(source, /'configured'/);
  assert.match(source, /'setup_required'/);
  assert.match(source, /Cache-Control.*no-store/);
  assert.doesNotMatch(source, /getProjectSecret|process\.env\.STYTCH_SECRET/);
});
