import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const fieldSource = readFileSync(new URL('../static/fields.js', import.meta.url), 'utf8');
const consentSource = readFileSync(new URL('../static/mcp-apps.js', import.meta.url), 'utf8');
const control = (value, checked = false) => ({
  value, checked, disabled: false, listeners: {},
  addEventListener(name, fn) {(this.listeners[name] ??= []).push(fn);},
  change(value) {
    this.checked = value;
    for (const fn of this.listeners.change ?? []) fn();
  },
  closest() {return {classList:{toggle(){}}};},
});

test('admin form disables non-granted columns rather than merely hiding them', () => {
  const role = control('reader');
  const grants = [control('calls:read',true), control('metrics:read',false)];
  const fields = [control('id',true),control('CALLDATE',true),
                  control('customername',true),control('aicallinfostate',true)];
  const form = {
    querySelectorAll(query) {
      if (query === 'input[name="fields"]') return fields;
      if (query === 'input[name="grants"]') return grants;
      throw Error(query);
    },
    querySelector(query) {
      if (query === '[data-role-select]') return role;
      if (query === '[data-group-select]') return null;
      throw Error(query);
    },
  };
  const document = {querySelectorAll(query) {
    assert.equal(query,'form[data-access-editor]');
    return [form];
  }};
  vm.runInNewContext(fieldSource,{document});
  assert.equal(fields[2].checked,false);
  assert.equal(fields[2].disabled,true);
  assert.equal(fields[0].checked,true);
  grants[0].change(false);
  assert.equal(fields[0].disabled,true);
  assert.equal(fields[0].checked,false);
  grants[1].change(true);
  assert.equal(fields[0].checked,true);
  assert.equal(fields[1].disabled,true);
});

test('OAuth app grant deselecting call capability removes call-only fields',()=>{
  const grants=[control('calls:read',true),control('metrics:read',false)];
  const fields=[control('id',true), control('CALLDATE',true),
                control('aicallinfostate',true),control('transcription',false)];
  const form={
    querySelectorAll(query) {
      if(query==='input[name="capabilities"]') return grants;
      if(query==='input[name="fields"]') return fields;
      throw Error(query);
    }
  };
  const document={querySelectorAll(q){
    assert.equal(q,'.mcp-consent-form');return [form];
  }};
  vm.runInNewContext(consentSource,{document});
  grants[0].change(false);
  assert.ok(fields.every(f=>!f.checked && f.disabled));
  grants[1].change(true);
  assert.equal(fields[0].disabled,false);
  assert.equal(fields[1].disabled,true);
});
