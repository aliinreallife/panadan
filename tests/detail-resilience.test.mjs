import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('overview contains one full-width date card and exactly four metadata cards',()=>{
  const js=readFileSync('static/app.js','utf8');
  const start=js.indexOf("const when=el('div','detail-chip detail-chip-datetime')");
  const end=js.indexOf("hero.append(chips);",start);
  const block=js.slice(start,end);
  assert.ok(start>0&&end>start);
  assert.match(block,/clock:formatSourceCallClock\(data.call_time\)/);
  assert.match(block,/day:dateFormat\(data.CALLDATE\)/);
  assert.match(block,/for\(const \[key,text\] of \[/);
  assert.match(block,/\['vw_danix_base_info_users_name'/);
  assert.match(block,/\['tellstate'/);
  assert.match(block,/\['aicallinfostate'/);
  assert.match(block,/const score=el\('div','detail-chip detail-chip-score'\)/);
  assert.match(block,/chips\.append\(score\)/);
  assert.doesNotMatch(block,/el\('p','detail-score'/);
});

test('clock+date move to left within card while keeping clock right of date',()=>{
  const css=readFileSync('static/style.css','utf8');
  const js=readFileSync('static/app.js','utf8');
  assert.match(css,/grid-template-areas:"title timestamp" "note note"/);
  assert.match(css,/\.detail-chip-datetime \.call-datetime\{\s*grid-area:timestamp;justify-self:end/);
  assert.match(css,/\.detail-overview \.detail-chips\{gap:14px;grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(js,/wrapper\.append\(hour,date\)/);
  assert.match(js,/ساعت احتمالی به وقت تهران · رویداد تماس هنوز تأیید نشده/);
});

test('multi-select dropdown is one clean checkmark list with no secondary footer',()=>{
  const css=readFileSync('static/style.css','utf8');
  const js=readFileSync('static/multiselect.js','utf8');
  assert.match(css,/\.ui-multi-popup\[hidden\]\{display:none!important\}/);
  assert.match(css,/\.ui-multi-search:focus,\.ui-multi-search:focus-visible\{/);
  assert.match(css,/\.ui-multi-trigger > span:last-child::before\{/);
  assert.match(js,/row\.setAttribute\('aria-selected'/);
  assert.doesNotMatch(js,/ui-multi-footer|ui-multi-reset|ui-multi-done/);
});

test('dashboard reporting failures retain last same-filter data and expose retry',()=>{
  const js=readFileSync('static/app.js','utf8');
  const template=readFileSync('templates/dashboard.html','utf8');
  assert.match(js,/shownCallsKey===requestKey/);
  assert.match(js,/shownMetricsKey===key/);
  assert.match(js,/requestId!==callListRequestId/);
  assert.match(js,/reportState\('calls',false,stale\)/);
  assert.match(js,/reportState\('metrics',false,shownMetricsKey===key\)/);
  assert.match(js,/lastGoodFilterOptions=found/);
  assert.match(js,/Promise\.allSettled\(\[load\(\),metrics\(\),loadFilterOptions\(\)\]\)/);
  assert.match(template,/id="source-health"/);
  assert.match(template,/id="report-retry"/);
  assert.match(template,/id="error" role="alert"/);
});
