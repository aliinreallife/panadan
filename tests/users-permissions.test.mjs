import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const code = readFileSync(new URL('../static/users.js', import.meta.url), 'utf8');
const caps = [
  'calls:read','metrics:read','calls:sensitive','calls:transcript:read',
  'mcp:use','users:manage','tokens:manage',
];
const groups = [
  {id:'reader',description:'reader',grants:['calls:read']},
  {id:'metrics',description:'metrics',grants:['metrics:read']},
  {id:'analyst',description:'analyst',grants:['calls:read','metrics:read','mcp:use']},
];
const defaults = {reader:'reader',metrics:'metrics',analyst:'analyst'};

function control(value) {
  return {
    value, checked:false, disabled:false, listeners:{},
    addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);},
    change(value){this.value=value; for(const fn of this.listeners.change||[])fn();},
    toggle(value){this.checked=value; for(const fn of this.listeners.change||[])fn();},
  };
}
function setup(initial=[]) {
  const role=control('reader');
  const group=control('reader');
  const checkboxMap=new Map(caps.map(x=>[x,control(x)]));
  for (const name of initial) checkboxMap.get(name).checked=true;
  const count={textContent:''};
  const hint={textContent:''};
  const warning={hidden:true};
  const form={
    dataset:{accessEditor:'edit'},listeners:{},
    querySelector(query){
      return ({
        '[data-role-select]':role,'[data-group-select]':group,
        '[data-grant-count]':count,'[data-group-hint]':hint,
        '[data-risk-note]':warning,
      })[query]??null;
    },
    querySelectorAll(query){
      assert.equal(query,'input[name="grants"]');
      return [...checkboxMap.values()];
    },
    addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);},
  };
  const document={
    querySelectorAll(query){
      assert.equal(query,'form[data-access-editor]');
      return [form];
    },
    getElementById(id){
      const data={'access-group-catalog':groups,'access-role-defaults':defaults}[id];
      return data ? {textContent:JSON.stringify(data)} : null;
    },
  };
  vm.runInNewContext(code,{document,window:{confirm:()=>true},Intl});
  return {role,group,checkboxMap,count,hint,warning,form};
}
const checked = state => [...state.checkboxMap].filter(([k,c])=>c.checked).map(([k])=>k);

test('metrics-only user can enable MCP without call summaries',()=>{
  const state=setup(['metrics:read']);
  state.checkboxMap.get('mcp:use').toggle(true);
  assert.equal(state.checkboxMap.get('mcp:use').checked,true);
  assert.equal(state.checkboxMap.get('metrics:read').checked,true);
  assert.equal(state.checkboxMap.get('calls:read').checked,false);
});

test('calls-only user keeps MCP when metrics is removed',()=>{
  const state=setup(['calls:read','mcp:use']);
  state.checkboxMap.get('metrics:read').toggle(false);
  assert.equal(state.checkboxMap.get('mcp:use').checked,true);
  assert.equal(state.checkboxMap.get('calls:read').checked,true);
});

test('MCP is disabled when the final reporting grant goes away',()=>{
  const state=setup(['metrics:read','mcp:use']);
  state.checkboxMap.get('metrics:read').toggle(false);
  assert.equal(state.checkboxMap.get('mcp:use').checked,false);
});

test('group templates set only visible grants and never admin capabilities',()=>{
  const state=setup([]);
  state.role.change('analyst');
  assert.deepEqual(new Set(checked(state)),new Set(['calls:read','metrics:read','mcp:use']));
  state.group.change('metrics');
  assert.deepEqual(checked(state),['metrics:read']);
  state.role.change('admin');
  assert.ok([...state.checkboxMap.values()].every(x=>x.disabled));
});
