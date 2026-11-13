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
  for (let i = 0; i < 50 && !d.querySelector('#view .hero'); i++) await sleep(100);
  const txt = () => d.getElementById('view').textContent;
  const click = el => el.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
  const set = (id, v) => { const el = d.getElementById(id); el.value = v; el.dispatchEvent(new w.Event('input', { bubbles: true })); };
  const step = (n) => console.log('ok  ' + n);

  assert.ok(d.getElementById('asof').textContent.includes('30 Oct'), d.getElementById('asof').textContent);
  assert.ok(txt().includes('Add your first stock')); step('loads market.json, empty holdings message');

  // bad symbol
  set('f-sym', 'NOPE'); set('f-qty', '10'); set('f-price', '100'); click(d.querySelector('[data-act=add]'));
  assert.ok(txt().includes('not in the list')); step('rejects an unknown symbol');

  // good holding
  const today = new Date().toISOString().slice(0, 10);
  set('f-sym', 'upco'); set('f-date', '2026-09-01'); set('f-qty', '10'); set('f-price', '100'); click(d.querySelector('[data-act=add]'));
  assert.ok(d.querySelector('#view .st'), 'pill shown');
  assert.ok(txt().includes('UPCO') && txt().includes('short-term now') , txt().slice(0, 300));
  const saved = JSON.parse(w.localStorage.getItem('lt_holdings_v1'));
  assert.strictEqual(saved.length, 1); assert.strictEqual(saved[0].sym, 'UPCO'); step('adds a holding, shows status, saves to localStorage');

  // ideas
  click(d.querySelector('[data-tab=ideas]'));
  const mm = txt().match(/(\d+) stocks? (is|are) in a steady uptrend/); assert.ok(mm, txt().slice(0, 200));
  const found = parseInt(mm[1], 10); assert.ok(found >= 1, 'ideas: ' + found);
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
  assert.ok(txt().includes('Add your first stock'));
  click(d.querySelector('[data-tab=settings]')); set('rs', bk); click(d.querySelector('[data-act=restore]'));
  assert.strictEqual(JSON.parse(w.localStorage.getItem('lt_holdings_v1')).length, 1);
  assert.ok(txt().includes('Restored 1'));  step('delete and restore from backup');


  // a holding bought years ago keeps its real date and shows the stop-loss in force
  click(d.querySelector('[data-tab=holdings]'));
  set('f-sym', 'NIFTYBEES'); set('f-date', '2021-03-15'); set('f-qty', '5'); set('f-price', '120'); click(d.querySelector('[data-act=add]'));
  const old = JSON.parse(w.localStorage.getItem('lt_holdings_v1')).find(x => x.sym === 'NIFTYBEES');
  assert.strictEqual(old.buyDate, '2021-03-15');
  assert.ok(txt().includes('15 Mar 2021'), 'buy date with its year shown');
  assert.ok(txt().includes('Stop-loss now'), 'stop-loss shown');
  assert.ok(/Long-term since\s*16 Mar 2022/.test(txt()), 'long-term date with year');
  assert.ok(txt().includes('You bought before'), 'short-history note');
  step('an older purchase date and year are kept and shown, with the stop-loss');


  // ---- News tab (needs docs/news.json built from the test fixtures)
  click(d.querySelector('[data-tab=news]'));
  assert.ok(d.querySelector('#view .seg'), 'segmented control');
  assert.ok(d.querySelector('.verdict').textContent.indexOf('Nifty 50') >= 0 && d.querySelector('.verdict').textContent.indexOf('S&P 500') >= 0, d.querySelector('.verdict').textContent);
  assert.ok(txt().includes('Indian markets') && txt().includes('Nifty 50') && txt().includes('Sensex'), 'india indices');
  const links = [...d.querySelectorAll('a.hl')];
  assert.ok(links.length >= 3, 'headline links: ' + links.length);
  assert.ok(links.every(a => /^https?:/.test(a.getAttribute('href')) && a.getAttribute('rel').includes('noopener') && a.getAttribute('target') === '_blank'), 'safe links');
  assert.ok(!txt().includes('A bad link item'), 'unsafe link dropped');
  assert.ok(txt().includes('Indian stocks in the news') && txt().includes('ETERNAL') && txt().includes('SBIN'), 'mentions');
  assert.ok(txt().includes('Biggest movers') && txt().includes('GLOBALH'), 'movers');
  assert.ok(txt().includes('3 of 4 news feeds answered'), 'feed health');
  step('News tab: Indian markets, headlines, stocks in the news, movers');
  click(d.querySelector('[data-act=news-view][data-v=world]'));
  assert.ok(txt().includes('World markets') && txt().includes('S&P 500') && txt().includes('Currency and commodities') && txt().includes('US dollar in rupees'));
  assert.ok(txt().includes('Global stocks in the news') && txt().includes('AAPL') && txt().includes('$210'), 'us mention with a dollar price');
  assert.ok(txt().indexOf('World markets') > -1); step('World view: markets, headlines, US stocks');
  click(d.querySelector('[data-act=news-view][data-v=watch]'));
  assert.ok(txt().includes('Indian stocks to watch') && txt().includes('Volume 5.0 times'), 'watch list with a reason');
  assert.ok(txt().includes('Global stocks to watch') && txt().includes('not a recommendation'));
  step('To watch view: volume-and-move picks with a reason, plus the publishers\' lists');
  click(d.querySelector('[data-tab=settings]'));
  assert.ok(!d.getElementById('bk').value.includes('ipos'), 'no leftover IPO data in backups');
  assert.strictEqual(w.localStorage.getItem('lt_ipos_v1'), null); step('old IPO data is gone');

  assert.deepStrictEqual(errors, []);
  console.log('\nsmoke test passed');
  srv.close(); w.close(); process.exit(0);
})().catch(e => { console.error('FAIL', e); process.exit(1); });
