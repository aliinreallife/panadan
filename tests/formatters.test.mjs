import test from 'node:test';
import assert from 'node:assert/strict';
import {formatVoiceDuration, voiceDurationSegments, formatSourceCallClock, hasDisplayableDealValue} from '../static/formatters.js';

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


test('call_time is rendered as a local clock, never as an audio duration',()=>{
  assert.equal(formatSourceCallClock(0),'۰۰:۰۰');
  assert.equal(formatSourceCallClock(59),'۰۰:۰۰');
  assert.equal(formatSourceCallClock(3600),'۰۱:۰۰');
  assert.equal(formatSourceCallClock(3661),'۰۱:۰۱');
  assert.equal(formatSourceCallClock(67116),'۱۸:۳۸');
  assert.equal(formatSourceCallClock(86399),'۲۳:۵۹');
  assert.equal(formatSourceCallClock('43200'),'۱۲:۰۰');
});
test('unverified or absent source clocks render safely',()=>{
  for(const value of [null, undefined,'',false,-1,86400,1.5,'N/A',Infinity,NaN]){
    assert.equal(formatSourceCallClock(value),'—');
  }
});
test('zero deal values are hidden in UI while nonzero raw values remain',()=>{
  for(const value of [0,-0,'0','0.0',null,undefined,'',NaN,Infinity,'unknown']){
    assert.equal(hasDisplayableDealValue(value),false);
  }
  assert.equal(hasDisplayableDealValue(123.45),true);
  assert.equal(hasDisplayableDealValue(-10),true);
  assert.equal(hasDisplayableDealValue('200'),true);
});


test('RTL durations retain largest unit first as DOM segments',()=>{
  assert.deepEqual(voiceDurationSegments(178),['۲ دقیقه','۵۸ ثانیه']);
  assert.deepEqual(voiceDurationSegments(3661),['۱ ساعت','۱ دقیقه','۱ ثانیه']);
  assert.deepEqual(voiceDurationSegments(0),['۰ ثانیه']);
  assert.deepEqual(voiceDurationSegments(null),[]);
});
