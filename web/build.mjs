import { build } from 'esbuild';
import { mkdirSync, copyFileSync } from 'node:fs';
mkdirSync('static/vendor', { recursive: true });
await build({
  entryPoints: ['web/calendar-entry.js'],
  outfile: 'static/vendor/panadan-bundle.js',
  bundle: true, minify: true, format: 'iife', target: 'es2022',
  assetNames: 'assets/[name]-[hash]',
  loader: { '.woff2': 'file', '.woff': 'file' },
});
copyFileSync('node_modules/@doranjs/wc/dist/styles.css', 'static/vendor/doran.css');
console.log('Doran calendar and self-hosted Vazirmatn assets ready.');
