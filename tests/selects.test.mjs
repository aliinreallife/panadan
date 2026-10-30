import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeSearch, selectOptions, visibleOptions, nextEnabledIndex} from '../static/selects.js';

test('search matches Persian/Arabic equivalents and digit shapes',()=>{
  assert.equal(normalizeSearch('  پيگيري  '),normalizeSearch('پیگیری'));
  assert.equal(normalizeSearch(' ۱۲٣ '),'123');
  assert.equal(normalizeSearch('مَتین'),normalizeSearch('متین'));
  assert.deepEqual(
    visibleOptions([{label:'پیگیری',hint:'FollowUp'},{label:'تماس اول',hint:'FirstToch'}],'follow').map(x=>x.label),
    ['پیگیری']
  );
});

test('select options preserve exact native values and selected status',()=>{
  const select={options:[
    {value:'',textContent:'همه وضعیت‌ها',title:'',disabled:false,selected:true},
    {value:'SoldOut',textContent:'فروش رفته',title:'SoldOut',disabled:false,selected:false},
    {value:'Unchecked',textContent:'بررسی‌نشده',title:'',disabled:true,selected:false}
  ]};
  assert.deepEqual(selectOptions(select),[
    {index:0,value:'',label:'همه وضعیت‌ها',hint:'',disabled:false,selected:true},
    {index:1,value:'SoldOut',label:'فروش رفته',hint:'SoldOut',disabled:false,selected:false},
    {index:2,value:'Unchecked',label:'بررسی‌نشده',hint:'',disabled:true,selected:false}
  ]);
});

test('keyboard movement skips disabled options and wraps safely',()=>{
  const options=[{disabled:false},{disabled:true},{disabled:false}];
  assert.equal(nextEnabledIndex(options,0,'next'),2);
  assert.equal(nextEnabledIndex(options,2,'next'),0);
  assert.equal(nextEnabledIndex(options,0,'previous'),2);
  assert.equal(nextEnabledIndex(options,0,'first'),0);
  assert.equal(nextEnabledIndex(options,0,'last'),2);
  assert.equal(nextEnabledIndex([{disabled:true}],0,'next'),-1);
  assert.equal(nextEnabledIndex([],0,'next'),-1);
});

test('empty searches and unknown labels remain visible',()=>{
  const rows=[{label:'نامشخص',hint:''},{label:'بررسی‌نشده',hint:'Unchecked'}];
  assert.equal(visibleOptions(rows,'').length,2);
  assert.equal(visibleOptions(rows,'کلمات-وجود-ندارد').length,0);
  assert.equal(visibleOptions(rows,'unchecked')[0].label,'بررسی‌نشده');
});
