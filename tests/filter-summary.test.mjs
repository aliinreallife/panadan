import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {appliedFilterGroups, REPORT_FACETS, preserveSelectedFacetOptions} from '../static/filter-summary.js';

test('applied filter summary ignores pagination and locked operator identity', () => {
  const params = new URLSearchParams({
    limit: '20', offset: '40', operator: 'profile-operator',
    after: '2026-10-01', state: 'FollowUp',
  });
  const found = appliedFilterGroups(params, {
    formatDate: raw => 'تاریخ ' + raw,
    labelFor: (key, raw) => key === 'state' ? 'پیگیری' : raw,
  });
  assert.deepEqual(found, [
    {key: 'after', label: 'از تاریخ', summary: 'تاریخ 2026-10-01', count: 1},
    {key: 'state', label: 'وضعیت', summary: 'پیگیری', count: 1},
  ]);
  assert.equal(appliedFilterGroups(new URLSearchParams('limit=20&offset=0')).length, 0);
});

test('long multi-selects are capped to compact category summaries without changing values', () => {
  const params = new URLSearchParams('direction=IntoOut&destination=west&destination=east&destination=north&destination=west');
  const found = appliedFilterGroups(params, {
    labelFor: (_key, raw) => ({west:'غرب',east:'شرق',north:'شمال',IntoOut:'خروجی'})[raw] ?? raw,
    formatCount: n => n.toLocaleString('fa-IR'),
  });
  assert.deepEqual(found, [
    {key:'destination',label:'مقصد',summary:'غرب، شرق و ۱ مورد دیگر',count:3},
    {key:'direction',label:'جهت تماس',summary:'خروجی',count:1},
  ]);
  assert.deepEqual(params.getAll('destination'), ['west','east','north','west']);
  assert.equal(REPORT_FACETS.length, 8);
});

test('applied chips represent successful responses only and render source labels safely', () => {
  const app = readFileSync('static/app.js','utf8');
  const html = readFileSync('templates/dashboard.html','utf8');
  const css = readFileSync('static/style.css','utf8');
  assert.match(app,/appliedCallsParams=new URLSearchParams\(requestKey\)/);
  assert.match(app,/shownCallsKey=requestKey;[\s\S]*?renderAppliedFilterSummary\(\);/);
  assert.match(app,/chip\.append\(el\('span','applied-filter-name'/);
  assert.doesNotMatch(app,/chip\.innerHTML/);
  assert.match(html,/id="applied-filters"[^>]*hidden/);
  assert.match(html,/id="applied-filter-chips"/);
  assert.match(html,/id="count"[^>]*aria-live="polite"/);
  assert.match(app,/\$\('rows'\)\.setAttribute\('aria-busy','true'\)/);
  assert.match(app,/\$\('rows'\)\.removeAttribute\('aria-busy'\)/);
  assert.match(app,/clear\.onclick=\(\)=>\$\('reset'\)\?\.click\(\)/);
  assert.match(css,/\.applied-filters\[hidden\]\{display:none!important\}/);
});

test('mobile operator profile activates the operators destination', () => {
  const nav = readFileSync('static/mobile-nav.js','utf8');
  assert.match(nav,/group\.id === 'operators' && current === '\/dashboard\/operator'/);
  assert.doesNotMatch(nav,/group\.id === 'report' && current === '\/dashboard\/operator'/);
});

test('refreshed facet list retains selected raw values and their old labels', () => {
  const options=preserveSelectedFacetOptions(
    ['IntoOut','OutToIn'],
    [{value:'UnknownLegacy',textContent:'وضعیت ناشناخته'}, {value:'IntoOut',textContent:'خروجی'}]
  );
  assert.deepEqual(options,[
    {value:'IntoOut',selected:true,available:true,previousLabel:'خروجی'},
    {value:'OutToIn',selected:false,available:true,previousLabel:'OutToIn'},
    {value:'UnknownLegacy',selected:true,available:false,previousLabel:'وضعیت ناشناخته'},
  ]);
  assert.deepEqual(
    preserveSelectedFacetOptions([], [{value:'',textContent:'همه'}, {value:'x',textContent:'مورد x'}]),
    [{value:'x',selected:true,available:false,previousLabel:'مورد x'}]
  );
  const app=readFileSync('static/app.js','utf8');
  assert.match(app,/preserveSelectedFacetOptions\(values,select\.selectedOptions\)/);
  assert.match(app,/option\.selected=entry\.selected/);
});
