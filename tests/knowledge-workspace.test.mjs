import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../static/knowledge.js', import.meta.url), 'utf8');
const template = readFileSync(new URL('../templates/knowledge_workspace.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../static/knowledge.css', import.meta.url), 'utf8');

test('restored workspace presentation is cleared and revalidated, normal navigation is untouched', () => {
  const handlers = {};
  let clears = 0, reloads = 0;
  runInNewContext(source, {
    window: {
      addEventListener: (name, fn) => { handlers[name] = fn; },
      location: { reload: () => reloads++ },
    },
    document: {
      querySelector: name => name === '.k-shell'
        ? { replaceChildren: () => clears++ }
        : null,
      getElementById: () => null,
    },
  });
  handlers.pagehide({ persisted: false });
  handlers.pageshow({ persisted: false });
  assert.equal(clears, 0);
  assert.equal(reloads, 0);
  handlers.pagehide({ persisted: true });
  handlers.pageshow({ persisted: true });
  assert.equal(clears, 1);
  assert.equal(reloads, 1);
});

test('workspace UI keeps RTL, self-hosted assets, native controls and narrow viewport layout', () => {
  assert.match(template, /<html lang="fa" dir="rtl">/);
  assert.match(template, /href="#content"/);
  assert.match(template, /name="csrf"/);
  assert.match(template, /aria-current="page"/);
  assert.match(template, /<details class="switcher"/);
  assert.doesNotMatch(template, /(?:src|href)="https?:\/\//);
  assert.match(css, /@media\(max-width:680px\)/);
  assert.match(css, /min-height:44px/);
  assert.match(css, /:focus-visible/);
  assert.match(css, /prefers-reduced-motion/);
});
