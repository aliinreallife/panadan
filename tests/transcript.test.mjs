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

test('dense single-paragraph dialogue with repeated blank labels retains all speech', () => {
  // Synthetic text reproduces the format, not any real customer transcript.
  const raw='اپراتور مشتری اپراتور سلام، بفرمایید. مشتری سلام، وقت بخیر. اپراتور. در خدمتم. مشتری؟ هزینه چقدره؟ اپراتور، توضیح می‌دم. مشتری ممنون اپراتور.';
  const result=parseTranscript(raw);
  assert.equal(result.raw,raw);
  assert.deepEqual(result.turns.map(x=>x.speaker),
    ['اپراتور','مشتری','اپراتور','مشتری','اپراتور','مشتری']);
  assert.equal(result.turns[0].text,'سلام، بفرمایید.');
  assert.equal(result.turns[1].text,'سلام، وقت بخیر.');
  assert.equal(result.turns[2].text,'در خدمتم.');
  assert.equal(result.stats.emptyLabels,3);
  assert.equal(result.stats.inlineLines,1);
  assert.ok(result.warnings.some(w=>w.includes('یک‌خطی')));
});

test('call paragraph alternates speaker labels without colon and with punctuation', () => {
  const raw='مشتری بله اپراتور سلام خوبین مشتری الو اپراتور. سلام خوبین مشتری. بله ممنون اپراتور، مدرک‌ها رو دارید؟ مشتری؟ امروز می‌فرستم.';
  const parsed=parseTranscript(raw);
  assert.equal(parsed.raw,raw);
  assert.deepEqual(parsed.turns.map(t=>t.speaker),
    ['مشتری','اپراتور','مشتری','اپراتور','مشتری','اپراتور','مشتری']);
  assert.equal(parsed.turns[5].text,'مدرک‌ها رو دارید؟');
});

test('back-to-back roles and operator typo work in one paragraph', () => {
  const raw='مشتری اپراتور سلام مشتری چطوری اپاتور. ممنون مشتری مشخصات رو بفرست اپراتور خب؟ مشتری درخواست بزنم';
  const parsed=parseTranscript(raw);
  assert.equal(parsed.raw,raw);
  assert.deepEqual(parsed.turns.map(t=>t.speaker),
    ['اپراتور','مشتری','اپراتور','مشتری','اپراتور','مشتری']);
  assert.equal(parsed.stats.emptyLabels,1);
});

test('inline markers after punctuation can touch following text', () => {
  const raw='مشتری؟سلام اپراتور:بفرمایید مشتری،بله اپراتور.خدانگهدار';
  const parsed=parseTranscript(raw);
  assert.deepEqual(parsed.turns.map(t=>t.text),
    ['سلام','بفرمایید','بله','خدانگهدار']);
});

test('bare customer nouns in ordinary prose are not used as speaker markers', () => {
  const raw='اپراتور: این مشتری امروز تماس گرفت و برای مشتری پیام فرستاد.\\nمشتری چیزی نگفت';
  const parsed=parseTranscript(raw);
  assert.equal(parsed.turns.length,1);
  assert.equal(parsed.turns[0].speaker,'اپراتور');
  assert.match(parsed.turns[0].text,/برای مشتری پیام فرستاد/);
  assert.equal(parsed.raw,raw);
});

test('single-paragraph ordinary customer references do not cause splitting', () => {
  const raw='اپراتور امروز این مشتری آمد و برای مشتری پیام فرستاد';
  const parsed=parseTranscript(raw);
  assert.equal(parsed.stats.inlineLines,0);
  assert.deepEqual(parsed.turns,[{speaker:'نامشخص',text:raw}]);
});
