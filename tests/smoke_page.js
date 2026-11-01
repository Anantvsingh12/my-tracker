// Optional browser-style check. Needs: npm install jsdom. Generate docs/market.json first, copy docs/ to /tmp/site, then: node tests/smoke_page.js
const http = require('http'), fs = require('fs'), path = require('path'), assert = require('assert');
const { JSDOM } = require('jsdom');
const root = '/tmp/site';
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.json': 'application/json' };
const srv = http.createServer((req, res) => {
  const p = path.join(root, req.url.split('?')[0] === '/' ? 'index.html' : req.url.split('?')[0]);
  fs.readFile(p, (e, b) => { if (e) { res.writeHead(404); return res.end(); } res.writeHead(200, { 'content-type': types[path.extname(p)] || 'text/plain' }); res.end(b); });
});
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  await new Promise(r => srv.listen(0, '127.0.0.1', r));
  const url = 'http://127.0.0.1:' + srv.address().port + '/';
  const errors = [];
  const dom = await JSDOM.fromURL(url, { runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
    beforeParse(w) { w.fetch = (u) => fetch(new URL(u, w.location.href).href); w.confirm = () => true; w.alert = (m) => errors.push('alert:' + m);
      w.addEventListener('error', e => errors.push(e.message)); } });
  const w = dom.window, d = w.document;
  for (let i = 0; i < 50 && !d.querySelector('#view .card'); i++) await sleep(100);
  const txt = () => d.getElementById('view').textContent;
  const click = el => el.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  const set = (id, v) => { const el = d.getElementById(id); el.value = v; el.dispatchEvent(new w.Event('input', { bubbles: true })); };
  const step = (n) => console.log('ok  ' + n);

  assert.ok(d.getElementById('asof').textContent.includes('Prices to 2026-10-30'), d.getElementById('asof').textContent);
  assert.ok(txt().includes('No holdings yet')); step('loads market.json, empty holdings message');

  // bad symbol
  set('f-sym', 'NOPE'); set('f-qty', '10'); set('f-price', '100'); click(d.querySelector('[data-act=add]'));
  assert.ok(txt().includes('Symbol not found')); step('rejects an unknown symbol');

  // good holding
  const today = new Date().toISOString().slice(0, 10);
  set('f-sym', 'upco'); set('f-date', '2026-09-01'); set('f-qty', '10'); set('f-price', '100'); click(d.querySelector('[data-act=add]'));
  assert.ok(d.querySelector('#view .pill'), 'pill shown');
  assert.ok(txt().includes('UPCO') && txt().includes('Short-term') , txt().slice(0, 300));
  const saved = JSON.parse(w.localStorage.getItem('lt_holdings_v1'));
  assert.strictEqual(saved.length, 1); assert.strictEqual(saved[0].sym, 'UPCO'); step('adds a holding, shows status, saves to localStorage');

  // ideas
  click(d.querySelector('[data-tab=ideas]'));
  assert.ok(txt().includes('found'), txt().slice(0, 200));
  const found = parseInt(txt().match(/(\d+) found/)[1], 10); assert.ok(found >= 1, 'ideas: ' + found);
  const lists = d.getElementById('i-lists'); lists.checked = true; lists.dispatchEvent(new w.Event('change', { bubbles: true }));
  assert.ok(txt().includes('UPCO')); step('ideas tab lists candidates and filters to my lists');
  click(d.querySelector('[data-act=bought]'));
  assert.strictEqual(d.getElementById('f-sym').value, 'UPCO'); assert.ok(d.getElementById('f-price').value); step('"I bought this" prefills the form');

  // lookup
  click(d.querySelector('[data-tab=lookup]')); set('q', 'down');
  assert.ok(d.getElementById('qres').textContent.includes('DOWNCO')); assert.ok(d.querySelector('svg.spark')); step('look up finds a stock and draws a chart');

  // settings + backup/restore
  click(d.querySelector('[data-tab=settings]')); set('s-cap', '3000'); click(d.querySelector('[data-act=save-settings]'));
  assert.strictEqual(JSON.parse(w.localStorage.getItem('lt_settings_v1')).capPerStock, 3000);
  const bk = d.getElementById('bk').value; assert.ok(bk.includes('UPCO')); step('saves settings, shows a backup');
  click(d.querySelector('[data-tab=holdings]')); click(d.querySelector('[data-act=del]'));
  assert.ok(txt().includes('No holdings yet'));
  click(d.querySelector('[data-tab=settings]')); set('rs', bk); click(d.querySelector('[data-act=restore]'));
  assert.strictEqual(JSON.parse(w.localStorage.getItem('lt_holdings_v1')).length, 1);
  assert.ok(txt().includes('Restored 1'));  step('delete and restore from backup');

  assert.deepStrictEqual(errors, []);
  console.log('\nsmoke test passed');
  srv.close(); w.close(); process.exit(0);
})().catch(e => { console.error('FAIL', e); process.exit(1); });
