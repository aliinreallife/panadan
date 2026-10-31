import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {multiValues,multiSummary} from '../static/multiselect.js';

test('multi-select only submits actual selected values, never placeholder',()=>{
  const select={selectedOptions:[
    {value:'Ali'}, {value:'Sara'}, {value:''}
  ]};
  assert.deepEqual(multiValues(select),['Ali','Sara']);
  assert.equal(multiSummary(select,'کارشناس'),'کارشناس · ۲ انتخاب');
  assert.equal(multiSummary({selectedOptions:[]},'وضعیت'),'همه وضعیت');
});

test('report filter HTML has six native multi-selects without logic switch',()=>{
  const html=readFileSync('templates/dashboard.html','utf8');
  for(const id of ['operator','destination','team','call_type','state','direction']){
    assert.match(html,new RegExp('id="'+id+'" multiple data-multi'));
  }
  assert.doesNotMatch(html,/filter-logic|name="filter_mode"/);
  assert.doesNotMatch(html,/AND|OR/);
});

test('mobile navigation groups secondary pages into exactly four destinations',()=>{
  const js=readFileSync('static/mobile-nav.js','utf8');
  for(const id of ['report','operators','integrations','management']){
    assert.match(js,new RegExp("id:'"+id+"'"));
  }
  assert.match(js,/groups=\[/);
  assert.match(js,/mobile-nav-tab/);
  assert.match(js,/aria-expanded/);
  assert.match(js,/links\.filter/);
  const css=readFileSync('static/style.css','utf8');
  assert.match(css,/grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
  assert.match(css,/\.shell > \.sidebar\.mobile-nav-ready > nav\{display:none!important\}/);
});

test('single-select enhancer skips multi-selects and mobile controls include search and clear',()=>{
  const selects=readFileSync('static/selects.js','utf8');
  const multi=readFileSync('static/multiselect.js','utf8');
  assert.match(selects,/:not\(\[multiple\]\)/);
  assert.match(multi,/search\.type='search'/);
  assert.match(multi,/check\.type='checkbox'/);
  assert.match(multi,/reset\.addEventListener/);
  assert.match(multi,/select\.dispatchEvent\(new Event\('change'/);
});

test('compact responsive filters use four desktop and two mobile columns',()=>{
  const css=readFileSync('static/style.css','utf8');
  assert.match(css,/\.report-filters\{display:grid;grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
  assert.match(css,/@media\(max-width:600px\)\{\s*\.report-filters\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(css,/\.mobile-nav-tab\{\s*min-height:38px/);
  assert.match(css,/\.ui-multi-popup\{\s*left:0!important;right:0!important;top:auto!important/);
});
test('every admin screen exposes all four mobile navigation destinations',()=>{
  for(const name of ['activity','connect','tokens','api','oauth','users','operators']){
    const html=readFileSync('templates/'+name+'.html','utf8');
    assert.match(html,/href="\/dashboard"/);
    assert.match(html,/href="\/dashboard\/operators"/);
    assert.match(html,/href="\/dashboard\/users"/);
    assert.match(html,/href="\/dashboard\/connect"/);
    assert.match(html,/\/static\/mobile-nav\.js/);
  }
});
