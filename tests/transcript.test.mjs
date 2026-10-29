import test from 'node:test';
import assert from 'node:assert/strict';
import { parseTranscript } from '../static/transcript.js';

test('colon-prefixed lines and adjacent lines render without changing raw', () => {
  const raw = 'اپراتور: سلام نهال گشت بفرمایید.\nمشتری: سلام خسته نباشید.\nاپراتور: بفرمایید.';
  const result = parseTranscript(raw);
  assert.equal(result.raw, raw);
  assert.deepEqual(result.turns.map(x => x.speaker), ['اپراتور','مشتری','اپراتور']);
  assert.equal(result.turns[1].text, 'سلام خسته نباشید.');
});

test('escaped literal newlines and stand-alone labels', () => {
  const raw = 'مشتری \\n اپراتور \\n مشتری \\n الو \\n اپراتور \\n سلام عزیزم';
  const result = parseTranscript(raw);
  assert.equal(result.turns.length, 2);
  assert.equal(result.turns[0].speaker, 'مشتری');
  assert.equal(result.turns[0].text, 'الو');
  assert.equal(result.turns[1].text, 'سلام عزیزم');
  assert.equal(result.stats.emptyLabels, 2);
});

test('multiline dialogue, blank labels, and unassigned introduction', () => {
  const raw = 'سلام آغاز\nمشتری:\nبا سلام، شما با مجموعه تماس گرفتید.\nاپراتور:\nمیگه نت‌هام صادر شده.\nمشتری:\nاپراتور:\nسلام';
  const result = parseTranscript(raw);
  assert.equal(result.turns.length, 4);
  assert.equal(result.turns[0].speaker,'نامشخص');
  assert.equal(result.turns[1].speaker,'مشتری');
  assert.equal(result.stats.emptyLabels,1);
});

test('speaker word in the body is not mistaken for a new speaker', () => {
  const result = parseTranscript('اپراتور: این مشتری امروز تماس گرفت.\nمشتری چیزی نگفت');
  assert.equal(result.turns.length,1);
  assert.match(result.turns[0].text, /مشتری چیزی نگفت/);
});

test('unmarked transcript is retained, without invented speakers', () => {
  const raw = 'الو\nسلام\nبله';
  const r = parseTranscript(raw);
  assert.deepEqual(r.turns, [{speaker:'نامشخص',text:raw}]);
  assert.equal(r.stats.labelsFound,0);
});

test('empty input behaves safely', () => {
  const r = parseTranscript(null);
  assert.equal(r.turns.length,0);
  assert.equal(r.raw,'');
});


test('backslash line continuation around speaker labels is handled', () => {
  const result=parseTranscript('مشتری:\\nبا سلام\nاپراتور:\\nسلام');
  assert.deepEqual(result.turns.map(t=>t.text), ['با سلام','سلام']);
});
