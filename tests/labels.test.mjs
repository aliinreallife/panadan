import test from 'node:test';
import assert from 'node:assert/strict';
import {callTypeLabel, callStateLabel} from '../static/labels.js';

test('call types map to stable Persian display names', () => {
  assert.equal(callTypeLabel('FirstToch'), 'تماس اول');
  assert.equal(callTypeLabel('FirstTouch'), 'تماس اول');
  assert.equal(callTypeLabel('FollowUp'), 'پیگیری');
  assert.equal(callTypeLabel('Colleague'), 'همکار');
  assert.equal(callTypeLabel('Unknown'), 'نامشخص');
});
test('AI states are translated without inventing sales confirmation', () => {
  assert.equal(callStateLabel('SoldOut'), 'فروش رفته');
  assert.equal(callStateLabel('Unchecked'), 'بررسی‌نشده');
  assert.equal(callStateLabel('System Invalid'), 'نامعتبر سیستمی');
  assert.equal(callStateLabel('User Invalid'), 'نامعتبر کاربری');
  assert.equal(callStateLabel('Inprocess'), 'در حال بررسی');
});
test('unknown values are preserved, not inferred or changed', () => {
  assert.equal(callTypeLabel('NewType'), 'NewType');
  assert.equal(callStateLabel('New State'), 'New State');
  assert.equal(callTypeLabel(null), '—');
});
