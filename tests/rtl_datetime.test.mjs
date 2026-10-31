import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';

const jalaliSource=readFileSync('static/jalali.js','utf8');
const scope={window:{},Intl,Date};
runInNewContext(jalaliSource,scope);
const format=scope.window.PanadanDate.format;

test('Persian Jalali formatter honors clock-only options in Tehran',()=>{
  const raw='2026-10-29T04:39:00';
  const clock=format(raw,{hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZone:'Asia/Tehran'});
  const date=format(raw,{year:'numeric',month:'2-digit',day:'2-digit',timeZone:'Asia/Tehran'});
  assert.equal(clock,'۰۸:۰۹');
  assert.match(date,/۱۴۰۵/);
  assert.doesNotMatch(clock,/۱۴۰۵/);
});

test('call detail builds clock then date as separately isolated RTL parts',()=>{
  const app=readFileSync('static/app.js','utf8');
  const component=app.slice(app.indexOf('function dateTimeNode('),app.indexOf('function recordedDateTime('));
  assert.match(component,/wrapper\.dir='rtl'/);
  assert.match(component,/wrapper\.append\(hour,date\)/);
  assert.match(component,/hour\.dir=date\.dir='ltr'/);
  assert.match(app,/className:'call-datetime'/);
  assert.match(app,/recordedDateTime\(val\)/);
});

test('activity timestamps put clock first while maintaining Tehran conversion',()=>{
  const activity=readFileSync('static/activity.js','utf8');
  assert.match(activity,/time\.append\(node\('span','activity-clock datetime-clock',stamp\.time\),\s*node\('span','activity-date datetime-date',stamp\.date\)\)/);
});

test('RTL CSS ensures clock on right and date on left even with bidi digits',()=>{
  const css=readFileSync('static/style.css','utf8');
  assert.match(css,/\.datetime-inline\{display:inline-flex;direction:rtl;flex-direction:row/);
  assert.match(css,/\.datetime-clock,\.datetime-date\{direction:ltr;unicode-bidi:isolate/);
  const template=readFileSync('templates/tokens.html','utf8');
  assert.ok(template.indexOf('date_time_clock') < template.indexOf('date_time_day'));
  assert.match(template,/class="datetime-inline token-datetime" dir="rtl"/);
});
