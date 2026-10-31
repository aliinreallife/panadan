import test from 'node:test';
import assert from 'node:assert/strict';
import {formatVoiceDuration} from '../static/formatters.js';

test('voice_length in seconds formats in compact readable Persian units',()=>{
  assert.equal(formatVoiceDuration(0),'۰ ثانیه');
  assert.equal(formatVoiceDuration(45),'۴۵ ثانیه');
  assert.equal(formatVoiceDuration(90),'۱ دقیقه و ۳۰ ثانیه');
  assert.equal(formatVoiceDuration(125),'۲ دقیقه و ۵ ثانیه');
  assert.equal(formatVoiceDuration(3600),'۱ ساعت');
  assert.equal(formatVoiceDuration(3661),'۱ ساعت و ۱ دقیقه و ۱ ثانیه');
});

test('invalid, missing and fractional average voice duration',()=>{
  assert.equal(formatVoiceDuration(null),'—');
  assert.equal(formatVoiceDuration(undefined),'—');
  assert.equal(formatVoiceDuration(''),'—');
  assert.equal(formatVoiceDuration('abc'),'—');
  assert.equal(formatVoiceDuration(-1),'—');
  assert.equal(formatVoiceDuration(89.8),'۱ دقیقه و ۳۰ ثانیه');
});
