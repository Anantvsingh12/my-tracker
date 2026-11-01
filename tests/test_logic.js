// run: node tests/test_logic.js
const assert = require('assert');
const LT = require('../docs/logic.js');

function mk(prices, extra) {            // symbol record with a 10-day calendar
  const dates = ['2026-10-19','2026-10-20','2026-10-21','2026-10-22','2026-10-23',
                 '2026-10-26','2026-10-27','2026-10-28','2026-10-29','2026-10-30'];
  const p = prices[prices.length - 1];
  return { dates, s: Object.assign({ n: 'Test Co', p, c: prices,
    m: { dma50: p * 0.97, dma200: p * 0.90, below200: 0, trend: 'UP', checks: 6 } }, extra || {}) };
}
const today = '2026-11-02';
let n = 0;
function t(name, fn) { fn(); n++; console.log('ok  ' + name); }

t('long-term date is one year and one day after the buy', () => {
  assert.strictEqual(LT.longTermFrom('2025-11-02'), '2026-11-03');
  assert.strictEqual(LT.longTermFrom('2025-12-31'), '2027-01-01');
  assert.strictEqual(LT.daysBetween('2026-11-02', '2026-11-12'), 10);
});

t('HOLD when nothing is wrong and trend is not an add', () => {
  const { dates, s } = mk([100,100,101,101,102,102,103,103,104,105], { m: { dma50: 90, dma200: 80, below200: 0, trend: 'UP' } });
  const r = LT.evaluate({ buyDate: '2026-10-20', price: 100, qty: 40 }, s, dates, {}, today);
  assert.strictEqual(r.status, 'HOLD');                 // value 4200 >= 80% of the 5000 cap, price stretched over 50dma
  assert.ok(Math.abs(r.pnl - 200) < 1e-9);
});

t('SELL when the price is at the stop (20% under cost)', () => {
  const { dates, s } = mk([100,99,95,92,90,88,85,82,80,79]);
  const r = LT.evaluate({ buyDate: '2026-10-19', price: 100, qty: 10 }, s, dates, {}, today);
  assert.strictEqual(r.status, 'SELL');
  assert.ok(r.reasons[0].indexOf('stop') >= 0);
  assert.strictEqual(r.stopPrice, 80);
});

t('your own stop price beats the percentage rule', () => {
  const { dates, s } = mk([100,100,100,100,100,100,100,100,100,94]);
  const r = LT.evaluate({ buyDate: '2026-10-19', price: 100, qty: 10, stop: 95 }, s, dates, {}, today);
  assert.strictEqual(r.status, 'SELL');
});

t('trailing stop arms after a 10% gain and sells on a 20% fall from the peak', () => {
  const { dates, s } = mk([100,110,120,130,140,135,130,125,115,110]);
  const r = LT.evaluate({ buyDate: '2026-10-19', price: 100, qty: 10 }, s, dates, {}, today);
  assert.strictEqual(r.peak, 140);
  assert.strictEqual(r.status, 'SELL');
  assert.ok(r.reasons.some(x => x.indexOf('trailing') >= 0));
  const r2 = LT.evaluate({ buyDate: '2026-10-19', price: 100, qty: 10 }, mk([100,105,106,106,106,105,104,103,102,101]).s, dates, {}, today);
  assert.strictEqual(r2.trailPrice, null);              // never gained 10%, so no trailing stop
});

t('peak only counts closes after the buy date', () => {
  const { dates, s } = mk([200,200,200,200,200,100,100,100,100,100]);
  const r = LT.evaluate({ buyDate: '2026-10-26', price: 100, qty: 10 }, s, dates, {}, today);
  assert.strictEqual(r.peak, 100);
});

t('REVIEW when the 200-day trend breaks, or target reached', () => {
  const a = mk([100,100,100,100,100,100,100,100,100,100], { m: { dma50: 98, dma200: 105, below200: 6, trend: 'DOWN' } });
  assert.strictEqual(LT.evaluate({ buyDate: '2026-10-19', price: 100, qty: 10 }, a.s, a.dates, {}, today).status, 'REVIEW');
  const b = mk([100,101,102,103,104,105,106,107,108,109]);
  const r = LT.evaluate({ buyDate: '2026-10-19', price: 100, qty: 10, target: 108 }, b.s, b.dates, {}, today);
  assert.strictEqual(r.status, 'REVIEW');
  assert.ok(r.reasons[0].indexOf('target') >= 0);
});

t('ADD only with room under the cap and a calm uptrend', () => {
  const a = mk([100,100,100,100,100,100,100,100,100,100], { m: { dma50: 99, dma200: 90, below200: 0, trend: 'UP' } });
  const r = LT.evaluate({ buyDate: '2026-10-19', price: 100, qty: 10 }, a.s, a.dates, { capPerStock: 5000 }, today);
  assert.strictEqual(r.status, 'ADD');                  // value 1000 < 4000, price within 5% of 50dma
  const full = LT.evaluate({ buyDate: '2026-10-19', price: 100, qty: 45 }, a.s, a.dates, { capPerStock: 5000 }, today);
  assert.strictEqual(full.status, 'HOLD');              // already near the cap
});

t('tax-mark note appears within 30 days of 12 months, only in profit', () => {
  const { dates, s } = mk([100,100,100,100,100,100,100,100,100,110]);
  const near = LT.evaluate({ buyDate: '2025-11-20', price: 100, qty: 10 }, s, dates, {}, today);
  assert.ok(near.daysToLT > 0 && near.daysToLT <= 30);
  assert.ok(near.notes.length === 1 && !near.isLong);
  const past = LT.evaluate({ buyDate: '2025-10-01', price: 100, qty: 10 }, s, dates, {}, today);
  assert.ok(past.isLong && past.notes.length === 0);
  const loss = LT.evaluate({ buyDate: '2025-11-20', price: 120, qty: 10 }, s, dates, {}, today);
  assert.strictEqual(loss.notes.length, 0);
});

t('ideas: filters and ordering', () => {
  const sym = {
    A: { n: 'Alpha', p: 100, c: [], m: { checks: 6, r6m: 10 }, L: ['LT Quality Compounders'] },
    B: { n: 'Beta', p: 100, c: [], m: { checks: 6, r6m: 30 } },
    C: { n: 'Gamma', p: 100, c: [], m: { checks: 5, r6m: 50 } },
    D: { n: 'Delta', p: 100, c: [], m: { checks: 3, r6m: 90 } },
    E: { n: 'Pricey', p: 9000, c: [], m: { checks: 6, r6m: 5 } },
    F: { n: 'Stale', p: 100, c: [], stale: true, m: { checks: 6, r6m: 99 } }
  };
  assert.deepStrictEqual(LT.ideaCandidates(sym, {}).map(x => x.sym), ['B', 'A', 'C']);
  assert.deepStrictEqual(LT.ideaCandidates(sym, { minChecks: 6 }).map(x => x.sym), ['B', 'A']);
  assert.deepStrictEqual(LT.ideaCandidates(sym, { onlyLists: true }).map(x => x.sym), ['A']);
  assert.deepStrictEqual(LT.ideaCandidates(sym, { affordableOnly: false, minChecks: 6 }).map(x => x.sym), ['B', 'A', 'E']);
  assert.strictEqual(LT.ideaCandidates(sym, {})[0].qty, 50);
});

t('search and sparkline', () => {
  const sym = { JIOFIN: { n: 'Jio Financial Services Ltd.' }, TRENT: { n: 'Trent Ltd.' }, TCS: { n: 'Tata Consultancy' } };
  assert.deepStrictEqual(LT.findSymbols(sym, 'jio'), ['JIOFIN']);
  assert.deepStrictEqual(LT.findSymbols(sym, 'T'), ['TCS', 'TRENT', 'JIOFIN']);   // symbol starts first, then names containing T
  assert.deepStrictEqual(LT.findSymbols(sym, 'TR'), ['TRENT']);
  assert.deepStrictEqual(LT.findSymbols(sym, 'consult'), ['TCS']);
  assert.strictEqual(LT.sparkPoints([1, null, 3], 100, 10), '0.0,10.0 100.0,0.0');
  assert.strictEqual(LT.sparkPoints([null], 100, 10), '');
  assert.strictEqual(LT.inr(1234.5), '\u20B91,234.5');
});

console.log('\n' + n + ' tests passed');
