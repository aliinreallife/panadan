import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {multiValues,multiSummary,toggleMultiOption} from '../static/multiselect.js';

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
  assert.match(js,/groups\s*=\s*\[/);
  assert.match(js,/mobile-nav-tab/);
  assert.match(js,/aria-expanded/);
  assert.match(js,/links\.filter/);
  const css=readFileSync('static/style.css','utf8');
  assert.match(css,/grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
  assert.match(css,/\.shell > \.sidebar\.mobile-nav-ready > nav\{display:none!important\}/);
});

test('multi-select has tappable rows with checkmarks and no footer/checkboxes',()=>{
  const selects=readFileSync('static/selects.js','utf8');
  const multi=readFileSync('static/multiselect.js','utf8');
  assert.match(selects,/:not\(\[multiple\]\)/);
  assert.match(multi,/search\.type='search'/);
  assert.match(multi,/row\.type = 'button'/);
  assert.match(multi,/row\.setAttribute\('role', 'option'\)/);
  assert.match(multi,/row\.setAttribute\('aria-selected'/);
  assert.match(multi,/tick\.textContent = '✓'/);
  assert.match(multi,/select\.dispatchEvent\(new Event\('change'/);
  assert.doesNotMatch(multi,/type='checkbox'|type = 'checkbox'/);
  assert.doesNotMatch(multi,/ui-multi-footer|ui-multi-done|ui-multi-reset/);
  const option={selected:false,disabled:false};
  assert.equal(toggleMultiOption(option,0),true);
  assert.equal(option.selected,true);
  assert.equal(toggleMultiOption(option,1),true);
  assert.equal(option.selected,false);
  assert.equal(toggleMultiOption(option,20),false);
  assert.equal(option.selected,false);
  option.disabled=true;
  assert.equal(toggleMultiOption(option,0),false);
});

test('four mobile navigation tabs are actual buttons anchored at the bottom',()=>{
  const mobile=readFileSync('static/mobile-nav.js','utf8');
  const css=readFileSync('static/style.css','utf8');
  assert.match(mobile,/const button = document\.createElement\('button'\)/);
  assert.match(mobile,/button\.type = 'button'/);
  assert.match(mobile,/mobile\.append\(button\)/);
  assert.match(mobile,/openMenu\(button, group, available\)/);
  assert.match(mobile,/window\.location\.assign\(available\[0\]\.href\)/);
  assert.match(css,/\.shell > \.sidebar \.mobile-nav\{\s*display:grid;position:fixed;inset:auto 0 0 0;/);
  assert.match(css,/grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
  assert.match(css,/\.shell > \.sidebar > nav:not\(\.mobile-nav\)\{[\s\S]*?overflow-x:hidden!important/);
  assert.match(css,/\.ui-multi-option\[aria-selected="true"\] \.ui-multi-check\{/);
  assert.doesNotMatch(css,/\.ui-multi-footer\{/);
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
