import test from 'node:test';
import assert from 'node:assert/strict';
import {dialablePhone} from '../static/phone.js';

test('safe dial links preserve leading zeros and format Iranian phone numbers',()=>{
  assert.equal(dialablePhone('09121234567'),'tel:09121234567');
  assert.equal(dialablePhone('۰۹۱۲ ۱۲۳ ۴۵۶۷'),'tel:09121234567');
  assert.equal(dialablePhone('٠٩١٢-١٢٣-٤٥٦٧'),'tel:09121234567');
  assert.equal(dialablePhone('+98 (912) 123-4567'),'tel:+989121234567');
  assert.equal(dialablePhone('021 8877 6666'),'tel:02188776666');
  assert.equal(dialablePhone('0098-912-123-4567'),'tel:00989121234567');
});

test('do not construct tel links from numeric, ambiguous, malicious or missing values',()=>{
  for(const value of [null,undefined,9121234567,1.2345e10,'','0','00000000',
    '1234','1234567890123456','09121234567;alert(1)',
    '09121234567,09121234568','tel:09121234567',
    '09121234567 ext 2','0912\n1234567',
    'javascript:alert(1)']) {
    assert.equal(dialablePhone(value),null,String(value));
  }
});
