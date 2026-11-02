import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const script = readFileSync(new URL('../static/users.js', import.meta.url), 'utf8');
const caps = ['calls:read','metrics:read','calls:sensitive','calls:transcript:read','mcp:use'];

function prepare({editing = false, selected = [], roleName = 'reader'} = {}) {
  const makeCheckbox = (value) => ({
    value, checked: selected.includes(value), disabled: false,
    listeners: new Map(),
    addEventListener(type, callback) {this.listeners.set(type, callback);},
    change(checked) {this.checked = checked; this.listeners.get('change')?.();}
  });
  const checks = new Map(caps.map(c => [c, makeCheckbox(c)]));
  const form = {
    querySelectorAll(query) {
      assert.equal(query, 'input[name="grants"]');
      return [...checks.values()];
    },
  };
  const role = {
    value: roleName,
    listeners: new Map(),
    addEventListener(type, callback) {this.listeners.set(type, callback);},
    change(value) {this.value = value; this.listeners.get('change')?.();}
  };
  const document = {
    getElementById(id) {assert.equal(id,'role'); return editing ? null : role;},
    querySelectorAll(query) {
      if (query === 'form[action="/dashboard/users"], form.user-edit-form') return [form];
      if (query === 'form[action="/dashboard/users"] input[name="grants"]') return [...checks.values()];
      throw Error('unexpected DOM selector: ' + query);
    },
  };
  vm.runInNewContext(script, {document});
  return {checks,role};
}

for (const editing of [false,true]) {
  test('MCP auto-checks prerequisites in '+(editing?'edit':'create')+' form', () => {
    const {checks}=prepare({editing});
    checks.get('mcp:use').change(true);
    assert.equal(checks.get('calls:read').checked,true);
    assert.equal(checks.get('metrics:read').checked,true);
    // Deny incomplete grants on prerequisite removal.
    checks.get('calls:read').change(false);
    assert.equal(checks.get('mcp:use').checked,false);
    checks.get('mcp:use').change(true);
    checks.get('metrics:read').change(false);
    assert.equal(checks.get('mcp:use').checked,false);
    assert.equal(checks.get('calls:read').checked,true);
  });
}

test('default role selection still works without granting MCP to readers', () => {
  const {checks,role}=prepare({editing:false});
  role.change('reader');
  assert.equal(checks.get('calls:read').checked,true);
  assert.equal(checks.get('metrics:read').checked,false);
  assert.equal(checks.get('mcp:use').checked,false);
  role.change('analyst');
  assert.equal(checks.get('calls:read').checked,true);
  assert.equal(checks.get('metrics:read').checked,true);
  assert.equal(checks.get('mcp:use').checked,true);
  role.change('admin');
  assert.ok([...checks.values()].every(c=>c.disabled));
  role.change('metrics');
  assert.ok([...checks.values()].every(c=>!c.disabled));
  assert.equal(checks.get('mcp:use').checked,false);
});
