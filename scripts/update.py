#!/usr/bin/env python3
"""update.py: build docs/market.json for the long-term tracker page.

Reads the stocks to follow from data/universe.txt (+ data/extra.txt for ETFs etc.),
downloads about two years of DAILY prices from Yahoo Finance (free, unofficial),
works out trend numbers for each one, and writes docs/market.json.
The web page (docs/index.html) reads that file. Standard library only, Python 3.8+.

  python scripts/update.py                 # everything
  python scripts/update.py --limit 20      # quick test on the first 20
  python scripts/update.py --offline DIR   # read saved Yahoo JSON (tests)

Education and tooling, not financial advice.
"""
import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0 (long-term-tracker; personal research tool)"
BENCH = "^NSEI"                      # Nifty 50
KEEP = 260                           # trading days of closes kept for the page
NSE_NIFTY500 = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class UpdateError(Exception):
    pass


# --------------------------------------------------------------- list files
def read_symbol_file(path):
    """[(SYMBOL, name, [list names])]. A line starting with '##' names a list for the symbols
    after it; a single '#' line is a plain comment."""
    out, current = [], []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("##"):
                title = line.lstrip("#").strip()
                current = [title] if title else []
                continue
            if line.startswith("#"):
                continue
            sym, _, name = line.partition("|")
            sym = sym.strip().upper()
            if sym:
                out.append((sym, name.strip() or sym, list(current)))
    return out


def load_universe(root, allow_download=True):
    uni = read_symbol_file(os.path.join(root, "data", "universe.txt"))
    if not uni and allow_download:
        try:
            text = http_get(NSE_NIFTY500).decode("utf-8-sig", "replace")
            for r in csv.DictReader(io.StringIO(text)):
                r = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
                if r.get("symbol") and (r.get("series") or "EQ").upper() == "EQ":
                    uni.append((r["symbol"].upper(), r.get("company name") or r["symbol"], []))
        except UpdateError:
            pass
    if not uni:
        raise UpdateError("data/universe.txt is empty. Copy your NSE list into it, for example:\n"
                          "  Copy-Item D:\\trading\\trader\\universe.txt data\\universe.txt")
    return uni


# --------------------------------------------------------------------- data
def http_get(url, timeout=25, retries=3):
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(2.0 * (i + 1))        # back off: Yahoo rate-limits shared servers
    raise UpdateError("could not fetch %s (%s)" % (url, last))


def parse_chart(js):
    chart = js.get("chart") or {}
    if chart.get("error"):
        raise UpdateError("Yahoo says: %s" % (chart["error"].get("description") or chart["error"]))
    res = (chart.get("result") or [None])[0]
    if not res:
        return []
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    seen = {}
    for i, t in enumerate(ts):
        try:
            c, v = q["close"][i], q["volume"][i]
        except (KeyError, IndexError):
            continue
        if c is None:
            continue
        day = dt.datetime.fromtimestamp(t, IST).date()
        seen[day] = (day, float(c), v or 0)      # one bar a day; the later one wins
    return [seen[d] for d in sorted(seen)]


def yahoo_symbol(sym):
    s = sym.upper()
    return s if s.startswith("^") or "." in s else s + ".NS"


def fetch_daily(sym, offline=None, pause=0.4):
    tk = yahoo_symbol(sym)
    if offline:
        p = os.path.join(offline, "%s_1d.json" % tk)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8-sig") as f:
            return parse_chart(json.load(f))
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=2y"
           "&includePrePost=false" % urllib.parse.quote(tk, safe=""))
    data = http_get(url)
    time.sleep(pause)
    return parse_chart(json.loads(data.decode("utf-8")))


# ------------------------------------------------------------------ numbers
def sma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None


def metrics(bars, bench_ret12=None):
    """Trend numbers from daily (date, close, volume) bars, oldest first."""
    cl = [b[1] for b in bars]
    vol = [b[2] for b in bars]
    n = len(cl)
    if n < 30:
        return None
    price = cl[-1]

    def ret(k):
        return round((price / cl[-1 - k] - 1) * 100, 2) if n > k and cl[-1 - k] else None

    dma50, dma200 = sma(cl, 50), sma(cl, 200)
    last = cl[-252:]
    hi52, lo52 = max(last), min(last)
    rets = [math.log(cl[i] / cl[i - 1]) for i in range(max(1, n - 126), n) if cl[i - 1] > 0 and cl[i] > 0]
    vol_ann = None
    if len(rets) > 20:
        mu = sum(rets) / len(rets)
        sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (len(rets) - 1))
        vol_ann = round(sd * math.sqrt(252) * 100, 1)
    below = 0                                     # days in a row closing under the 200-day average
    if dma200 is not None:
        i = n
        while i >= 200 and below < 60:
            if cl[i - 1] < sum(cl[i - 200:i]) / 200:
                below += 1
                i -= 1
            else:
                break
    tv = [cl[i] * vol[i] for i in range(max(0, n - 20), n)]
    turn = round(sum(tv) / len(tv) / 1e7, 1) if tv else None      # crore rupees a day
    trend = None
    if dma200 is not None and dma50 is not None:
        if price > dma200 and dma50 > dma200:
            trend = "UP"
        elif price < dma200 and dma50 < dma200:
            trend = "DOWN"
        else:
            trend = "MIXED"
    chg1d = round((price / cl[-2] - 1) * 100, 2) if n >= 2 and cl[-2] else None
    avg20 = sum(vol[-21:-1]) / 20 if n >= 21 else 0
    volx = round(vol[-1] / avg20, 2) if avg20 else None          # today's volume against the 20-day average
    m = {"chg1d": chg1d, "volx": volx, "r1m": ret(21), "r3m": ret(63), "r6m": ret(126), "r12m": ret(252),
         "dma50": round(dma50, 2) if dma50 else None, "dma200": round(dma200, 2) if dma200 else None,
         "vs200": round((price / dma200 - 1) * 100, 1) if dma200 else None,
         "hi52": round(hi52, 2), "lo52": round(lo52, 2), "dd": round((price / hi52 - 1) * 100, 1),
         "vol": vol_ann, "below200": below, "turn": turn, "trend": trend}
    if dma200 is not None and m["r12m"] is not None:
        checks = [
            ("above its 200-day average", price > dma200),
            ("50-day average above 200-day", dma50 > dma200),
            ("beat the Nifty over 12 months", bench_ret12 is not None and m["r12m"] > bench_ret12),
            ("within 20% of its 52-week high", m["dd"] >= -20),
            ("not too jumpy (volatility under 40%)", vol_ann is not None and vol_ann <= 40),
            ("easy to trade (over Rs 10 crore a day)", turn is not None and turn >= 10),
        ]
        m["checks"] = sum(1 for _, ok in checks if ok)
        m["failed"] = [lab for lab, ok in checks if not ok]
    return m


# --------------------------------------------------------------------- main
def load_old(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build(root, limit=0, offline=None, pause=0.4, now=None, quiet=False):
    uni = load_universe(root, allow_download=not offline)
    extra = read_symbol_file(os.path.join(root, "data", "extra.txt"))
    screens = {}
    for s, _, lists in read_symbol_file(os.path.join(root, "data", "screens.txt")):
        have = screens.setdefault(s, [])
        have.extend(x for x in lists if x not in have)
    names = {}
    for s, n, _ in uni + extra:
        names.setdefault(s, n)
    for s in screens:
        names.setdefault(s, s)
    order = list(names)
    if limit:
        keep = set(order[:limit]) | set(screens)
        order = [s for s in order if s in keep]
    old = load_old(os.path.join(root, "docs", "market.json")).get("symbols", {})

    bench = fetch_daily(BENCH, offline, pause)
    if len(bench) < 100:
        raise UpdateError("could not get the Nifty 50 history (%d bars): Yahoo may be rate-limiting. "
                          "Try again later." % len(bench))
    cal = [b[0] for b in bench][-KEEP:]
    calset = {d: i for i, d in enumerate(cal)}
    bench_ret12 = (bench[-1][1] / bench[-253][1] - 1) * 100 if len(bench) > 252 else None

    symbols, errors, fresh = {}, [], 0
    for i, s in enumerate(order, 1):
        try:
            bars = fetch_daily(s, offline, pause)
            if not bars:
                errors.append("%s: no price data" % s)
        except UpdateError as e:
            bars = []
            errors.append("%s: %s" % (s, str(e)[:80]))
        m = metrics(bars, bench_ret12) if bars else None
        if m is None:
            if s in old:                               # keep yesterday's numbers, marked stale
                symbols[s] = dict(old[s], stale=True)
            continue
        fresh += 1
        closes = [None] * len(cal)
        for d, c, _ in bars:
            if d in calset:
                closes[calset[d]] = round(c, 2)
        entry = {"n": names[s], "p": round(bars[-1][1], 2), "d": bars[-1][0].isoformat(), "m": m, "c": closes}
        if screens.get(s):
            entry["L"] = screens[s]
        symbols[s] = entry
        if not quiet and i % 50 == 0:
            print("  %d/%d ..." % (i, len(order)), file=sys.stderr)
    if fresh < min(len(order), max(3, len(order) // 4)):
        raise UpdateError("only %d of %d symbols came back, so I did not overwrite your data. "
                          "Yahoo is probably rate-limiting; try again later. First errors: %s"
                          % (fresh, len(order), "; ".join(errors[:3])))
    now = now or dt.datetime.now(IST)
    nifty = {"p": round(bench[-1][1], 2), "d": bench[-1][0].isoformat(),
             "r12m": round(bench_ret12, 2) if bench_ret12 is not None else None,
             "c": [round(b[1], 2) for b in bench][-KEEP:]}
    return {"asof": now.strftime("%Y-%m-%d %H:%M IST"), "last_day": bench[-1][0].isoformat(),
            "dates": [d.isoformat() for d in cal], "nifty": nifty, "symbols": symbols,
            "count": len(symbols), "fresh": fresh, "errors": errors[:25]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offline")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--pause", type=float, default=0.4)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    try:
        out = build(a.root, a.limit, a.offline, a.pause, quiet=a.quiet)
    except UpdateError as e:
        print("update.py: %s" % e, file=sys.stderr)
        return 1
    path = os.path.join(a.root, "docs", "market.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    kb = os.path.getsize(path) / 1024.0
    print("Wrote %s: %d symbols (%d fresh, %d errors), %.0f KB, data to %s."
          % (path, out["count"], out["fresh"], len(out["errors"]), kb, out["last_day"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
