import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';

const script = readFileSync(new URL('../static/users.js', import.meta.url), 'utf8');
const caps = [
  'calls:read', 'metrics:read', 'calls:sensitive',
  'calls:transcript:read', 'mcp:use', 'users:manage', 'tokens:manage',
];
const groups = [
  {id: 'metrics', description: 'Aggregates only', grants: ['metrics:read']},
  {id: 'reader', description: 'Calls only', grants: ['calls:read']},
  {id: 'analyst', description: 'Standard analyst', grants: ['calls:read','metrics:read','mcp:use']},
  {id: 'confidential', description: 'Confidential calls',
    grants: ['calls:read','metrics:read','calls:sensitive']},
  {id: 'transcript', description: 'Transcript reviewer',
    grants: ['calls:read','metrics:read','calls:transcript:read']},
];
const defaults = {analyst: 'analyst', reader: 'reader', metrics: 'metrics'};

function control(value = '') {
  return {
    value, checked: false, disabled: false, hidden: true, textContent: '',
    listeners: new Map(),
    addEventListener(type, callback) {this.listeners.set(type, callback);},
    change(next) {
      this.value = next;
      this.listeners.get('change')?.();
    },
  };
}

function prepare({editing = false, selected = ['calls:read'], roleName = 'reader'} = {}) {
  const checks = new Map(caps.map(key => {
    const c = control(key);
    c.checked = selected.includes(key);
    c.change = function(checked) {
      this.checked = checked;
      this.listeners.get('change')?.();
    };
    return [key, c];
  }));
  const role = control(roleName);
  const group = control('reader');
  const counter = control();
  const hint = control();
  const warning = control();
  const messages = [];
  const form = {
    dataset: {accessEditor: editing ? 'edit' : 'create'},
    listeners: new Map(),
    addEventListener(type, callback) {this.listeners.set(type, callback);},
    querySelector(query) {
      return {
        '[data-role-select]': role,
        '[data-group-select]': group,
        '[data-grant-count]': counter,
        '[data-group-hint]': hint,
        '[data-risk-note]': warning,
      }[query] || null;
    },
    querySelectorAll(query) {
      assert.equal(query, 'input[name="grants"]');
      return [...checks.values()];
    },
    submit() {
      let prevented = false;
      this.listeners.get('submit')?.({preventDefault() {prevented = true;}});
      return !prevented;
    },
  };
  const catalogs = {
    'access-group-catalog': {textContent: JSON.stringify(groups)},
    'access-role-defaults': {textContent: JSON.stringify(defaults)},
  };
  const document = {
    getElementById(id) {
      assert.ok(id in catalogs, 'unexpected JSON catalog: ' + id);
      return catalogs[id];
    },
    querySelectorAll(query) {
      assert.equal(query, 'form[data-access-editor]');
      return [form];
    },
  };
  const window = {
    confirm(message) {messages.push(message); return true;},
  };
  vm.runInNewContext(script, {document, window});
  return {checks, role, group, counter, hint, warning, form, messages, window};
}

for (const editing of [false, true]) {
  test('MCP auto-checks prerequisites in ' + (editing ? 'edit' : 'create') + ' form', () => {
    const {checks} = prepare({editing});
    checks.get('mcp:use').change(true);
    assert.equal(checks.get('calls:read').checked, true);
    assert.equal(checks.get('metrics:read').checked, true);
    checks.get('calls:read').change(false);
    assert.equal(checks.get('mcp:use').checked, false);
    checks.get('mcp:use').change(true);
    checks.get('metrics:read').change(false);
    assert.equal(checks.get('mcp:use').checked, false);
    assert.equal(checks.get('calls:read').checked, true);
  });
}

test('default role selection never grants MCP or administration to a reader', () => {
  const {checks, role, group} = prepare({editing:false});
  role.change('reader');
  assert.equal(group.value, 'reader');
  assert.equal(checks.get('calls:read').checked, true);
  assert.equal(checks.get('metrics:read').checked, false);
  assert.equal(checks.get('mcp:use').checked, false);
  role.change('analyst');
  assert.equal(group.value, 'analyst');
  assert.equal(checks.get('calls:read').checked, true);
  assert.equal(checks.get('metrics:read').checked, true);
  assert.equal(checks.get('mcp:use').checked, true);
  role.change('admin');
  assert.ok([...checks.values()].every(c => c.disabled));
  assert.equal(group.disabled, true);
  role.change('metrics');
  assert.equal(group.disabled, false);
  assert.equal(checks.get('mcp:use').checked, false);
  assert.equal(checks.get('calls:read').checked, false);
  assert.equal(checks.get('metrics:read').checked, true);
  assert.equal(checks.get('users:manage').checked, false);
  assert.equal(checks.get('tokens:manage').checked, false);
});

test('presets are snapshots and manual changes become custom grants', () => {
  const {checks, group, hint, warning} = prepare();
  group.change('confidential');
  assert.equal(checks.get('calls:sensitive').checked, true);
  assert.equal(warning.hidden, false);
  assert.equal(hint.textContent, 'Confidential calls');
  checks.get('calls:sensitive').change(false);
  assert.equal(group.value, 'custom');
  assert.equal(warning.hidden, true);
  group.change('transcript');
  assert.equal(checks.get('calls:transcript:read').checked, true);
  checks.get('calls:read').change(false);
  assert.equal(checks.get('calls:transcript:read').checked, false);
});

test('non-admin cannot submit elevated administrator grants via preset UI', () => {
  const {checks, role, group} = prepare();
  checks.get('users:manage').change(true);
  assert.equal(checks.get('users:manage').checked, false);
  assert.equal(checks.get('tokens:manage').checked, false);
  role.change('admin');
  assert.equal(group.disabled, true);
  assert.ok([...checks.values()].every(c => c.disabled));
});

test('sensitive changes and editing require a confirmation', () => {
  const {form, group, messages, window} = prepare({editing:true});
  group.change('confidential');
  window.confirm = message => {messages.push(message); return false;};
  assert.equal(form.submit(), false);
  assert.equal(messages.length, 1);
  assert.match(messages[0], /محرمانه/);
});
