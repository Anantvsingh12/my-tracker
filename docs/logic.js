/* logic.js: the rules behind the tracker page. Pure functions, no page code,
   so the same file is tested with node and used by index.html.
   Education and tooling, not financial advice. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.LT = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var DEFAULTS = {
    capPerStock: 5000,   // most you want in one stock, in rupees
    stopPct: 20,         // sell rule: price this % below what you paid
    trailArmPct: 10,     // trailing stop starts once the stock is this % above your buy price
    trailPct: 20,        // ...and sells if it then falls this % from its peak
    trendDays: 5,        // review if it closes below its 200-day average this many days in a row
    warnDdPct: 15,       // review if it is this % below its peak since you bought
    taxWarnDays: 30      // flag when this close to the 12-month mark
  };

  function inr(n) {
    if (n == null || isNaN(n)) return '-';
    return '\u20B9' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: 0 });
  }
  function ymd(s) { var p = String(s).split('-').map(Number); return Date.UTC(p[0], p[1] - 1, p[2]); }
  function fmt(ms) { return new Date(ms).toISOString().slice(0, 10); }
  function daysBetween(a, b) { return Math.round((ymd(b) - ymd(a)) / 86400000); }
  // first day a sale counts as long-term: more than 12 months after the buy date
  function longTermFrom(buyDate) {
    var p = String(buyDate).split('-').map(Number);
    return fmt(Date.UTC(p[0] + 1, p[1] - 1, p[2]) + 86400000);
  }

  function evaluate(h, s, dates, settings, today) {
    var st = Object.assign({}, DEFAULTS, settings || {});
    var qty = Number(h.qty), buy = Number(h.price), m = s.m || {};
    var invested = qty * buy, value = qty * s.p;
    var pnl = value - invested, pnlPct = (s.p / buy - 1) * 100;
    var daysHeld = Math.max(0, daysBetween(h.buyDate, today));
    var ltFrom = longTermFrom(h.buyDate);
    var daysToLT = daysBetween(today, ltFrom);
    var peak = buy;
    for (var i = 0; i < dates.length; i++) {
      var c = s.c ? s.c[i] : null;
      if (c != null && dates[i] >= h.buyDate && c > peak) peak = c;
    }
    if (s.p > peak) peak = s.p;
    var ddPeak = (s.p / peak - 1) * 100;
    var stopPrice = h.stop ? Number(h.stop) : buy * (1 - st.stopPct / 100);
    var trailArmed = peak >= buy * (1 + st.trailArmPct / 100);
    var trailPrice = trailArmed ? peak * (1 - st.trailPct / 100) : null;

    var sell = [], review = [], notes = [];
    if (s.p <= stopPrice) sell.push('Price ' + inr(s.p) + ' is at or below your stop ' + inr(stopPrice));
    if (trailPrice != null && s.p <= trailPrice)
      sell.push('Fell ' + Math.round(-ddPeak) + '% from its peak after a gain: trailing stop hit');
    if (m.below200 >= st.trendDays)
      review.push('Closed below its 200-day average ' + m.below200 + ' days in a row: the trend has broken');
    if (h.target && s.p >= Number(h.target))
      review.push('Reached your target ' + inr(h.target) + ': decide whether to take some profit');
    if (!sell.length && ddPeak <= -st.warnDdPct)
      review.push('Down ' + Math.round(-ddPeak) + '% from its peak since you bought');
    if (daysToLT > 0 && daysToLT <= st.taxWarnDays && pnl > 0)
      notes.push(daysToLT + ' days until the gain is taxed at the long-term rate (from ' + ltFrom +
                 '). Unless a sell rule hits, waiting may save tax.');

    var status = 'HOLD', reasons;
    if (sell.length) { status = 'SELL'; reasons = sell.concat(review); }
    else if (review.length) { status = 'REVIEW'; reasons = review; }
    else if (m.dma200 && m.dma50 && s.p > m.dma200 && s.p <= m.dma50 * 1.05 && value < st.capPerStock * 0.8) {
      status = 'ADD';
      reasons = ['Trend is up and the price is not stretched; there is room for about ' +
                 inr(Math.floor(st.capPerStock - value)) + ' more under your ' + inr(st.capPerStock) + ' cap'];
    } else {
      reasons = ['No sell rule hit' + (m.trend ? '; trend ' + m.trend.toLowerCase() : '')];
    }
    return {
      status: status, reasons: reasons, notes: notes, invested: invested, value: value, pnl: pnl, pnlPct: pnlPct,
      daysHeld: daysHeld, isLong: daysToLT <= 0, daysToLT: daysToLT, longFrom: ltFrom, peak: peak, ddPeak: ddPeak,
      stopPrice: stopPrice, trailPrice: trailPrice, stale: !!s.stale
    };
  }

  function ideaCandidates(symbols, opts) {
    var o = Object.assign({ minChecks: 5, onlyLists: false, affordableOnly: true, cap: DEFAULTS.capPerStock }, opts || {});
    var out = [];
    Object.keys(symbols).forEach(function (sym) {
      var s = symbols[sym], m = s.m;
      if (!m || m.checks == null || s.stale) return;
      if (m.checks < o.minChecks) return;
      if (o.onlyLists && !(s.L && s.L.length)) return;
      var q = Math.floor(o.cap / s.p);
      if (o.affordableOnly && q < 1) return;
      out.push({ sym: sym, s: s, qty: q, cost: q * s.p });
    });
    out.sort(function (a, b) {
      if (b.s.m.checks !== a.s.m.checks) return b.s.m.checks - a.s.m.checks;
      var x = a.s.m.r6m == null ? -1e9 : a.s.m.r6m, y = b.s.m.r6m == null ? -1e9 : b.s.m.r6m;
      return y - x;
    });
    return out;
  }

  function findSymbols(symbols, query, limit) {
    var q = String(query || '').trim().toUpperCase();
    if (!q) return [];
    var exact = [], starts = [], within = [];
    Object.keys(symbols).forEach(function (sym) {
      var nm = String(symbols[sym].n || '').toUpperCase();
      if (sym === q) exact.push(sym);
      else if (sym.indexOf(q) === 0) starts.push(sym);
      else if (nm.indexOf(q) >= 0) within.push(sym);
    });
    starts.sort(); within.sort();
    return exact.concat(starts, within).slice(0, limit || 8);
  }

  function sparkPoints(closes, w, h) {
    var pts = [], lo = Infinity, hi = -Infinity, i;
    for (i = 0; i < closes.length; i++) if (closes[i] != null) { lo = Math.min(lo, closes[i]); hi = Math.max(hi, closes[i]); }
    if (!isFinite(lo)) return '';
    var span = hi - lo || 1, n = closes.length - 1 || 1;
    for (i = 0; i < closes.length; i++) {
      if (closes[i] == null) continue;
      pts.push((i / n * w).toFixed(1) + ',' + (h - (closes[i] - lo) / span * h).toFixed(1));
    }
    return pts.join(' ');
  }

  return { DEFAULTS: DEFAULTS, inr: inr, daysBetween: daysBetween, longTermFrom: longTermFrom,
           evaluate: evaluate, ideaCandidates: ideaCandidates, findSymbols: findSymbols, sparkPoints: sparkPoints };
});
