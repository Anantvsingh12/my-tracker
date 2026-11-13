#!/usr/bin/env python3
"""news.py: build docs/news.json, the data behind the News tab.

  * Market snapshot: Indian and world indices, USD/INR, crude, gold (Yahoo Finance daily prices).
  * Headlines from the publishers' own RSS feeds (data/feeds.txt): headline, source, time, link only.
  * Stocks in the news: your tracked Indian stocks and big US stocks whose names appear in headlines.
  * Biggest movers, and Indian stocks trading on unusually high volume (from docs/market.json).
  * Links to the publishers' own "stocks to watch" articles.

  python scripts/news.py             # build docs/news.json
  python scripts/news.py --check     # test each feed and print what it returned
  python scripts/news.py --offline DIR   # read saved files (tests)

Standard library only. Education and tooling, not financial advice.
"""
import argparse
import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as up   # noqa: E402  (shared fetching and chart parsing)

IST = up.IST
ROOT = up.ROOT
MAX_AGE_H = 48
PER_FEED = 25

INDICES = [
    ("in", "^NSEI", "Nifty 50"), ("in", "^BSESN", "Sensex"), ("in", "^NSEBANK", "Bank Nifty"),
    ("in", "^INDIAVIX", "India VIX"),
    ("world", "^GSPC", "S&P 500"), ("world", "^IXIC", "Nasdaq"), ("world", "^DJI", "Dow Jones"),
    ("world", "^FTSE", "FTSE 100"), ("world", "^GDAXI", "DAX"), ("world", "^N225", "Nikkei 225"),
    ("world", "^HSI", "Hang Seng"),
    ("other", "INR=X", "US dollar in rupees"), ("other", "BZ=F", "Brent crude (USD)"), ("other", "GC=F", "Gold (USD an ounce)"),
]

# big US stocks: ticker -> names headlines use
US_STOCKS = {
    "AAPL": ["Apple"], "MSFT": ["Microsoft"], "NVDA": ["Nvidia"], "AMZN": ["Amazon"], "GOOGL": ["Alphabet", "Google"],
    "META": ["Meta Platforms", "Meta"], "TSLA": ["Tesla"], "AVGO": ["Broadcom"], "JPM": ["JPMorgan", "JP Morgan"],
    "V": ["Visa Inc"], "WMT": ["Walmart"], "NFLX": ["Netflix"], "AMD": ["AMD", "Advanced Micro Devices"], "ORCL": ["Oracle"],
    "COST": ["Costco"], "BAC": ["Bank of America"], "XOM": ["Exxon", "Exxon Mobil"], "CVX": ["Chevron"],
    "LLY": ["Eli Lilly"], "UNH": ["UnitedHealth"], "JNJ": ["Johnson & Johnson"], "PG": ["Procter & Gamble"],
    "HD": ["Home Depot"], "KO": ["Coca-Cola"], "PEP": ["PepsiCo"], "MRK": ["Merck"], "PFE": ["Pfizer"],
    "DIS": ["Disney"], "INTC": ["Intel"], "CSCO": ["Cisco"], "CRM": ["Salesforce"], "ADBE": ["Adobe"],
    "QCOM": ["Qualcomm"], "BA": ["Boeing"], "GS": ["Goldman Sachs"], "MS": ["Morgan Stanley"], "UBER": ["Uber"],
    "PLTR": ["Palantir"], "MU": ["Micron"], "IBM": ["IBM"], "NKE": ["Nike"], "MCD": ["McDonald's"],
    "SBUX": ["Starbucks"], "T": ["AT&T"], "VZ": ["Verizon"], "ABBV": ["AbbVie"], "TSM": ["TSMC", "Taiwan Semiconductor"],
}
US_NAMES = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "AMZN": "Amazon", "GOOGL": "Alphabet", "META": "Meta Platforms",
    "TSLA": "Tesla", "AVGO": "Broadcom", "JPM": "JPMorgan Chase", "V": "Visa", "WMT": "Walmart", "NFLX": "Netflix",
    "AMD": "AMD", "ORCL": "Oracle", "COST": "Costco", "BAC": "Bank of America", "XOM": "Exxon Mobil", "CVX": "Chevron",
    "LLY": "Eli Lilly", "UNH": "UnitedHealth", "JNJ": "Johnson & Johnson", "PG": "Procter & Gamble", "HD": "Home Depot",
    "KO": "Coca-Cola", "PEP": "PepsiCo", "MRK": "Merck", "PFE": "Pfizer", "DIS": "Disney", "INTC": "Intel", "CSCO": "Cisco",
    "CRM": "Salesforce", "ADBE": "Adobe", "QCOM": "Qualcomm", "BA": "Boeing", "GS": "Goldman Sachs", "MS": "Morgan Stanley",
    "UBER": "Uber", "PLTR": "Palantir", "MU": "Micron", "IBM": "IBM", "NKE": "Nike", "MCD": "McDonald's", "SBUX": "Starbucks",
    "T": "AT&T", "VZ": "Verizon", "ABBV": "AbbVie", "TSM": "TSMC",
}

WATCH_RE = re.compile(r"stocks?\s+to\s+watch|stocks?\s+in\s+focus|shares?\s+to\s+watch|buzzing\s+stocks|stocks?\s+in\s+(?:the\s+)?news|"
                      r"stocks?\s+(?:that\s+)?(?:will|may)\s+be\s+in\s+focus|stock\s+picks|stocks?\s+to\s+buy|stock\s+movers|pre-?market\s+movers|"
                      r"stocks?\s+making\s+the\s+biggest\s+moves|biggest\s+movers", re.I)
STOP_SINGLE = {"global", "power", "energy", "india", "indian", "bank", "industries", "finance", "capital", "international",
               "systems", "services", "technologies", "infra", "steel", "motors", "foods", "life", "gold", "star", "sun",
               "one", "universal", "united", "national", "digital", "premier", "royal", "pioneer", "apollo", "alpha", "model",
               "ideal", "supreme", "prime", "elite", "vision", "bharat", "india", "sigma", "omega", "delta", "vertex", "nexus"}
SUFFIX_RE = re.compile(r"\s+(limited|ltd|pvt|private|inc|corp|plc|co)$")


class NewsError(Exception):
    pass


# ---------------------------------------------------------------- text helpers
def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def safe_url(u):
    u = (u or "").strip()
    return u if re.match(r"^https?://", u, re.I) else None


def norm_words(s):
    s = html.unescape(str(s)).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_company(name):
    n = norm_words(name)
    while True:
        m = SUFFIX_RE.search(n)
        if not m:
            return n
        n = n[:m.start()]


def parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    d = None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        d = None
    if d is None:
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp())


# ----------------------------------------------------------------------- feeds
def read_feeds(path):
    out, region = [], "India"
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("##"):
                region = line.lstrip("#").strip() or region
                continue
            if line.startswith("#"):
                continue
            url, _, name = line.partition("|")
            url = safe_url(url)
            if url:
                out.append({"url": url, "name": name.strip() or urllib.parse.urlparse(url).netloc, "region": region})
    return out


def local(tag):
    return tag.split("}")[-1]


def child(el, name):
    for c in el:
        if local(c.tag) == name:
            return c
    return None


def child_text(el, *names):
    for n in names:
        c = child(el, n)
        if c is not None:
            text = "".join(c.itertext()).strip()
            if text:
                return text
    return ""


def parse_feed(data, source):
    """RSS 2.0 or Atom -> [{t, l, s, ts}]. Headline, link and time only."""
    import xml.etree.ElementTree as ET
    if b"<!ENTITY" in data or b"<!entity" in data:
        raise NewsError("feed uses XML entities; skipped")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise NewsError("not a readable feed (%s)" % e)
    items = []
    for el in root.iter():
        kind = local(el.tag)
        if kind == "item":
            title, link = strip_tags(child_text(el, "title")), safe_url(child_text(el, "link"))
            ts = parse_date(child_text(el, "pubDate", "date", "published", "updated"))
        elif kind == "entry":
            title = strip_tags(child_text(el, "title"))
            link = None
            for c in el:
                if local(c.tag) == "link":
                    href = c.attrib.get("href")
                    if href and c.attrib.get("rel", "alternate") == "alternate":
                        link = safe_url(href)
                        break
            ts = parse_date(child_text(el, "published", "updated"))
        else:
            continue
        if title and link:
            items.append({"t": title, "l": link, "s": source, "ts": ts})
    return items


def dedupe(items):
    seen, out = set(), []
    for it in sorted(items, key=lambda x: -(x["ts"] or 0)):
        k = norm_words(it["t"])[:70]
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out


def collect(feeds, offline=None, now_ts=None, pause=0.4):
    now_ts = now_ts or int(time.time())
    by_region, stats = {}, []
    for fd in feeds:
        err, items = None, []
        try:
            if offline:
                slug = re.sub(r"[^a-z0-9]+", "-", fd["name"].lower()).strip("-")
                p = os.path.join(offline, "feed-%s.xml" % slug)
                if not os.path.exists(p):
                    raise NewsError("no saved file")
                with open(p, "rb") as f:
                    data = f.read()
            else:
                data = up.http_get(fd["url"], timeout=25, retries=1)
                time.sleep(pause)
            items = parse_feed(data, fd["name"])
        except (NewsError, up.UpdateError) as e:
            err = str(e)[:100]
        fresh = [i for i in items if i["ts"] is None or now_ts - i["ts"] <= MAX_AGE_H * 3600]
        fresh = sorted(fresh, key=lambda x: -(x["ts"] or 0))[:PER_FEED]
        by_region.setdefault(fd["region"].lower(), []).extend(fresh)
        stats.append({"name": fd["name"], "region": fd["region"], "ok": err is None, "items": len(fresh), "err": err})
    return {k: dedupe(v) for k, v in by_region.items()}, stats


# ---------------------------------------------------------------------- prices
def fetch_quote(sym, offline=None, pause=0.3):
    if offline:
        p = os.path.join(offline, "%s_1d.json" % sym)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8-sig") as f:
            bars = up.parse_chart(json.load(f))
    else:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=10d&includePrePost=false"
               % urllib.parse.quote(sym, safe=""))
        bars = up.parse_chart(json.loads(up.http_get(url, retries=1).decode("utf-8")))
        time.sleep(pause)
    if len(bars) < 2 or not bars[-2][1]:
        return None
    p, prev = bars[-1][1], bars[-2][1]
    return {"p": round(p, 2), "c": round((p / prev - 1) * 100, 2), "d": bars[-1][0].isoformat()}


def snapshot(offline=None, pause=0.3):
    out = []
    for region, sym, name in INDICES:
        try:
            q = fetch_quote(sym, offline, pause)
        except (up.UpdateError, ValueError):
            q = None
        if q:
            out.append(dict(q, k=region, s=sym, n=name))
    return out


def us_quotes(offline=None, pause=0.3):
    out = {}
    for sym in US_STOCKS:
        try:
            q = fetch_quote(sym, offline, pause)
        except (up.UpdateError, ValueError):
            q = None
        if q:
            out[sym] = q
    return out


# ------------------------------------------------------------- stocks in news
def read_aliases(path):
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#") and "|" in line:
                    a, _, b = line.partition("|")
                    if a.strip() and b.strip():
                        out.append((norm_words(a), norm_company(b)))
    return out


def india_name_index(symbols, aliases):
    """variant text -> NSE symbol, dropping variants that point at more than one stock."""
    seen, bad = {}, set()

    def add(v, sym):
        if not v:
            return
        if v in seen and seen[v] != sym:
            bad.add(v)
        seen[v] = sym

    names = {sym: norm_company(e.get("n") or "") for sym, e in symbols.items()}
    for sym, n in names.items():
        words = n.split()
        if len(words) >= 2 or (len(n) >= 5 and n not in STOP_SINGLE):
            add(n, sym)
    for alias, prefix in aliases:
        hits = [sym for sym, n in names.items() if n == prefix or n.startswith(prefix + " ")]
        if len(hits) == 1:
            add(alias, hits[0])
    return {v: s for v, s in seen.items() if v not in bad}


def us_name_index():
    idx = {}
    for sym, variants in US_STOCKS.items():
        for v in variants:
            idx[norm_words(v)] = sym
    return idx


def find_mentions(items, name_index):
    """{symbol: [items mentioning it]}, newest first."""
    out = {}
    variants = sorted(name_index, key=len, reverse=True)
    for it in items:
        text = " %s " % norm_words(it["t"])
        got = set()
        for v in variants:
            if " %s " % v in text:
                got.add(name_index[v])
        cash = set(m.upper() for m in re.findall(r"\$([A-Za-z]{1,5})\b", it["t"]))
        for c in cash:
            if c in US_STOCKS and name_index.get("apple") == "AAPL":    # cashtags only for the US index
                got.add(c)
        for sym in got:
            out.setdefault(sym, []).append(it)
    return out


def top_n(rows, key, n, reverse=True):
    return sorted(rows, key=key, reverse=reverse)[:n]


def india_movers(symbols, k=6):
    liquid = []
    for sym, e in symbols.items():
        m = e.get("m") or {}
        c = m.get("chg1d")
        if c is None:
            cl = [x for x in (e.get("c") or []) if x is not None]
            c = round((cl[-1] / cl[-2] - 1) * 100, 2) if len(cl) >= 2 and cl[-2] else None
        if c is None or e.get("stale") or (m.get("turn") or 0) < 10:
            continue
        liquid.append({"sym": sym, "n": e.get("n", sym), "p": e["p"], "c": c, "volx": m.get("volx")})
    up_ = [r for r in top_n(liquid, lambda r: r["c"], k) if r["c"] > 0]
    down = [r for r in top_n(liquid, lambda r: r["c"], k, reverse=False) if r["c"] < 0]
    watch = [r for r in liquid if (r["volx"] or 0) >= 2 and abs(r["c"]) >= 2]
    if len(watch) < 3:
        watch = [r for r in liquid if (r["volx"] or 0) >= 1.5 and abs(r["c"]) >= 1.5]
    watch = top_n(watch, lambda r: (r["volx"] or 0), 8)
    for r in watch:
        r["why"] = "Volume %.1f times its 20-day average, %s %.1f%%" % (r["volx"], "up" if r["c"] > 0 else "down", abs(r["c"]))
    return up_, down, watch


# ----------------------------------------------------------------------- build
def load_market(root):
    try:
        with open(os.path.join(root, "docs", "market.json"), encoding="utf-8") as f:
            return json.load(f).get("symbols", {})
    except (OSError, ValueError):
        return {}


def build(root, offline=None, now=None, pause=0.4):
    feeds = read_feeds(os.path.join(root, "data", "feeds.txt"))
    now = now or dt.datetime.now(IST)
    by_region, stats = collect(feeds, offline, int(now.timestamp()), pause)
    india_items, world_items = by_region.get("india", []), by_region.get("world", [])
    if not india_items and not world_items:
        raise NewsError("no headlines came back from any feed (%s)" % "; ".join("%s: %s" % (s["name"], s["err"]) for s in stats[:3]))

    symbols = load_market(root)
    aliases = read_aliases(os.path.join(root, "data", "aliases.txt"))
    in_idx = india_name_index(symbols, aliases) if symbols else {}
    in_men = find_mentions(india_items, in_idx) if in_idx else {}
    in_mentions = []
    for sym, its in in_men.items():
        e = symbols[sym]
        m = e.get("m") or {}
        in_mentions.append({"sym": sym, "n": e.get("n", sym), "p": e["p"], "c": m.get("chg1d"), "count": len(its),
                            "hl": [{"t": x["t"], "l": x["l"], "s": x["s"]} for x in its[:2]]})
    in_mentions = top_n(in_mentions, lambda r: (r["count"], 0), 12)

    quotes = us_quotes(offline, 0.3 if not offline else 0)
    us_men = find_mentions(world_items, us_name_index())
    us_mentions = []
    for sym, its in us_men.items():
        q = quotes.get(sym)
        us_mentions.append({"sym": sym, "n": US_NAMES.get(sym, sym), "p": q["p"] if q else None, "c": q["c"] if q else None,
                            "count": len(its), "hl": [{"t": x["t"], "l": x["l"], "s": x["s"]} for x in its[:2]]})
    us_mentions = top_n(us_mentions, lambda r: (r["count"], 0), 10)
    us_rows = [{"sym": s, "n": US_NAMES.get(s, s), "p": q["p"], "c": q["c"]} for s, q in quotes.items()]
    us_up = [r for r in top_n(us_rows, lambda r: r["c"], 5) if r["c"] > 0]
    us_down = [r for r in top_n(us_rows, lambda r: r["c"], 5, reverse=False) if r["c"] < 0]
    in_up, in_down, in_watch = india_movers(symbols) if symbols else ([], [], [])

    def links(items):
        return [i for i in items if WATCH_RE.search(i["t"])][:6]

    return {
        "asof": now.strftime("%Y-%m-%d %H:%M IST"), "ts": int(now.timestamp()),
        "indices": snapshot(offline, 0.3 if not offline else 0),
        "in_news": india_items[:20], "world_news": world_items[:20],
        "in_mentions": in_mentions, "us_mentions": us_mentions,
        "in_up": in_up, "in_down": in_down, "in_watch": in_watch,
        "us_up": us_up, "us_down": us_down,
        "watch_in": links(india_items), "watch_world": links(world_items),
        "feeds": stats,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--offline")
    ap.add_argument("--check", action="store_true", help="test each feed and print the result")
    a = ap.parse_args(argv)
    if a.check:
        feeds = read_feeds(os.path.join(a.root, "data", "feeds.txt"))
        by_region, stats = collect(feeds, a.offline)
        for s in stats:
            print("%-4s %-28s %s" % ("OK" if s["ok"] else "FAIL", s["name"], ("%d fresh headlines" % s["items"]) if s["ok"] else s["err"]))
        ok = sum(1 for s in stats if s["ok"])
        print("%d of %d feeds worked." % (ok, len(stats)))
        for region, items in by_region.items():
            print("\n%s, newest 3:" % region.title())
            for it in items[:3]:
                print("  - %s (%s)" % (it["t"][:90], it["s"]))
        q = fetch_quote("^NSEI", a.offline)
        print("\nNifty 50 quote: %s" % (q if q else "FAILED"))
        return 0 if ok else 1
    try:
        out = build(a.root, a.offline)
    except NewsError as e:
        print("news.py: %s" % e, file=sys.stderr)
        return 1
    path = os.path.join(a.root, "docs", "news.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print("Wrote %s: %d India and %d world headlines, %d indices, %d feeds ok."
          % (path, len(out["in_news"]), len(out["world_news"]), len(out["indices"]), sum(1 for s in out["feeds"] if s["ok"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
