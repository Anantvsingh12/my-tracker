import datetime as dt
import email.utils
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import news  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 11, 3, 0, tzinfo=UTC)          # 08:30 IST


def rfc(hours_ago):
    return email.utils.format_datetime(NOW - dt.timedelta(hours=hours_ago))


def rss(items):
    body = "".join("<item><title>%s</title><link>%s</link><pubDate>%s</pubDate></item>" % it for it in items)
    return ("<?xml version='1.0'?><rss version='2.0'><channel><title>x</title>%s</channel></rss>" % body).encode()


def chart(closes, vols=None):
    start = dt.date(2026, 11, 3)
    days = [start + dt.timedelta(days=i) for i in range(len(closes))]
    ts = [int(dt.datetime.combine(d, dt.time(9, 15), tzinfo=news.IST).timestamp()) for d in days]
    return {"chart": {"error": None, "result": [{"timestamp": ts, "meta": {}, "indicators": {"quote": [{
        "open": closes, "high": closes, "low": closes, "close": closes, "volume": vols or [1000] * len(closes)}]}}]}}


class Fx(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for d in ("data", "docs", "off"):
            os.makedirs(os.path.join(self.root, d))
        self.w("data/feeds.txt", "# c\n## India\nhttps://ex.test/et.xml|ET Markets\nhttps://ex.test/hindu.xml|The Hindu\n"
                                 "## World\nhttps://ex.test/bbc.xml|BBC Business\nhttps://ex.test/dead.xml|Dead Feed\n")
        self.w("data/aliases.txt", "# a\nzomato|Eternal\nsbi|State Bank of India\nnothere|No Such Company\n")
        syms = {
            "RELIANCE": {"n": "Reliance Industries Ltd.", "p": 1500.0, "m": {"chg1d": 1.2, "volx": 1.0, "turn": 900}},
            "ETERNAL": {"n": "Eternal Limited", "p": 300.0, "m": {"chg1d": 4.5, "volx": 3.1, "turn": 600}},
            "SBIN": {"n": "State Bank of India", "p": 800.0, "m": {"chg1d": -2.5, "volx": 2.4, "turn": 800}},
            "TRENT": {"n": "Trent Ltd.", "p": 4000.0, "m": {"chg1d": -3.9, "volx": 1.1, "turn": 300}},
            "GLOBALH": {"n": "Global Ltd.", "p": 100.0, "m": {"chg1d": 9.0, "volx": 5.0, "turn": 50}},
            "THIN": {"n": "Thin Traded Ltd.", "p": 50.0, "m": {"chg1d": 12.0, "volx": 8.0, "turn": 1.0}},
            "OLD": {"n": "Stale Company Ltd.", "p": 50.0, "stale": True, "m": {"chg1d": 7.0, "volx": 4.0, "turn": 100}},
            "TWIN1": {"n": "Twin Industries Ltd.", "p": 10.0, "m": {"chg1d": 0.1, "turn": 20}},
            "TWIN2": {"n": "Twin Industries Limited", "p": 11.0, "m": {"chg1d": 0.1, "turn": 20}},
        }
        self.w("docs/market.json", json.dumps({"symbols": syms}))
        self.feed("et-markets", [
            ("Stocks to watch: Zomato, SBI, Trent among 10 shares in focus today", "https://ex.test/a", rfc(2)),
            ("Reliance Industries shares rise as retail arm gains", "https://ex.test/b", rfc(3)),
            ("Sensex ends flat; Zomato jumps on strong results", "https://ex.test/c", rfc(5)),
            ("Old news from last week", "https://ex.test/old", rfc(100)),
            ("Twin Industries rallies", "https://ex.test/tw", rfc(6)),
            ("A bad link item", "javascript:alert(1)", rfc(1)),
        ])
        self.feed("the-hindu", [("Reliance Industries shares rise as retail arm gains!", "https://ex.test/b2", rfc(4)),
                                ("Rupee steady against dollar", "https://ex.test/r", rfc(7))])
        self.feed("bbc-business", [("Apple and Microsoft lead Wall Street higher", "https://ex.test/w1", rfc(2)),
                                   ("Stocks to watch today: Nvidia earnings preview", "https://ex.test/w2", rfc(3)),
                                   ("Oil slides as supply worries ease", "https://ex.test/w3", rfc(8))])
        for sym, closes in {"^NSEI": [24000, 24100], "^BSESN": [79000, 79300], "^GSPC": [6000, 5950], "INR=X": [88.0, 88.2],
                            "AAPL": [200, 210], "MSFT": [400, 380], "NVDA": [150, 160]}.items():
            self.chart(sym, closes)

    def tearDown(self):
        self.tmp.cleanup()

    def w(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def feed(self, slug, items):
        with open(os.path.join(self.root, "off", "feed-%s.xml" % slug), "wb") as f:
            f.write(rss(items))

    def chart(self, sym, closes):
        with open(os.path.join(self.root, "off", "%s_1d.json" % sym), "w") as f:
            json.dump(chart(closes), f)

    def build(self):
        return news.build(self.root, offline=os.path.join(self.root, "off"), now=NOW.astimezone(news.IST), pause=0)


class TestParsing(unittest.TestCase):
    def test_rss_and_atom(self):
        data = rss([("<b>Markets</b> &amp; more", "https://a.test/1", rfc(1)), ("No link here", "", rfc(1)), ("Bad", "ftp://x", rfc(1))])
        items = news.parse_feed(data, "Src")
        self.assertEqual([i["t"] for i in items], ["Markets & more"])
        self.assertEqual(items[0]["s"], "Src")
        atom = (b"<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Atom story</title>"
                b"<link rel='alternate' href='https://a.test/atom'/><updated>2026-11-11T01:00:00Z</updated></entry></feed>")
        a = news.parse_feed(atom, "A")
        self.assertEqual((a[0]["t"], a[0]["l"]), ("Atom story", "https://a.test/atom"))
        self.assertEqual(a[0]["ts"], int(dt.datetime(2026, 11, 11, 1, tzinfo=UTC).timestamp()))

    def test_unsafe_or_broken_feeds(self):
        with self.assertRaises(news.NewsError):
            news.parse_feed(b"<?xml version='1.0'?><!DOCTYPE x [<!ENTITY a 'b'>]><rss/>", "x")
        with self.assertRaises(news.NewsError):
            news.parse_feed(b"<html>not xml", "x")

    def test_dedupe_and_dates(self):
        items = [{"t": "Same Story!", "l": "https://a", "s": "A", "ts": 100}, {"t": "same story", "l": "https://b", "s": "B", "ts": 200},
                 {"t": "Other", "l": "https://c", "s": "C", "ts": 150}]
        out = news.dedupe(items)
        self.assertEqual([i["t"] for i in out], ["same story", "Other"])
        self.assertEqual(news.parse_date("Wed, 11 Nov 2026 08:30:00 +0530"), int(dt.datetime(2026, 11, 11, 3, tzinfo=UTC).timestamp()))
        self.assertIsNone(news.parse_date("yesterday-ish"))

    def test_names(self):
        self.assertEqual(news.norm_company("Reliance Industries Ltd."), "reliance industries")
        self.assertEqual(news.norm_company("Mahindra & Mahindra Limited"), "mahindra and mahindra")
        self.assertEqual(news.norm_words("L&T"), "l and t")


class TestBuild(Fx):
    def test_everything(self):
        out = self.build()
        titles = [i["t"] for i in out["in_news"]]
        self.assertNotIn("Old news from last week", titles)                       # older than 48 hours
        self.assertFalse(any(i["l"].startswith("javascript") for i in out["in_news"]))
        self.assertEqual(sum(1 for t in titles if t.startswith("Reliance Industries shares rise")), 1)   # de-duplicated across feeds
        self.assertEqual(titles[0], "Stocks to watch: Zomato, SBI, Trent among 10 shares in focus today")  # newest first
        self.assertEqual(len(out["world_news"]), 3)
        ok = {f["name"]: f["ok"] for f in out["feeds"]}
        self.assertEqual(ok, {"ET Markets": True, "The Hindu": True, "BBC Business": True, "Dead Feed": False})
        idx = {i["s"]: i for i in out["indices"]}
        self.assertEqual(set(idx), {"^NSEI", "^BSESN", "^GSPC", "INR=X"})
        self.assertAlmostEqual(idx["^NSEI"]["c"], 0.42, places=2)
        self.assertEqual(idx["^NSEI"]["k"], "in"); self.assertEqual(idx["^GSPC"]["k"], "world"); self.assertEqual(idx["INR=X"]["k"], "other")
        men = {m["sym"]: m for m in out["in_mentions"]}
        self.assertEqual(set(men), {"ETERNAL", "SBIN", "TRENT", "RELIANCE"})      # aliases work; generic and twin names do not
        self.assertEqual(men["ETERNAL"]["count"], 2)
        self.assertEqual(men["ETERNAL"]["c"], 4.5)
        self.assertEqual(out["in_mentions"][0]["sym"], "ETERNAL")                  # most mentioned first
        usm = {m["sym"]: m for m in out["us_mentions"]}
        self.assertEqual(set(usm), {"AAPL", "MSFT", "NVDA"})
        self.assertAlmostEqual(usm["AAPL"]["c"], 5.0, places=2)
        self.assertEqual([r["sym"] for r in out["us_up"]], ["NVDA", "AAPL"])
        self.assertEqual([r["sym"] for r in out["us_down"]], ["MSFT"])
        self.assertTrue(all("stocks to watch" in w["t"].lower() or "in focus" in w["t"].lower() for w in out["watch_in"] + out["watch_world"]))
        self.assertEqual(len(out["watch_in"]), 1); self.assertEqual(len(out["watch_world"]), 1)

    def test_indian_movers_and_watch(self):
        out = self.build()
        self.assertEqual([r["sym"] for r in out["in_up"]], ["GLOBALH", "ETERNAL", "RELIANCE", "TWIN1", "TWIN2"])
        self.assertEqual([r["sym"] for r in out["in_down"]], ["TRENT", "SBIN"])
        everyone = [r["sym"] for r in out["in_up"]] + [r["sym"] for r in out["in_down"]]
        self.assertNotIn("THIN", everyone); self.assertNotIn("OLD", everyone)       # illiquid and stale are left out
        self.assertEqual([r["sym"] for r in out["in_watch"]], ["GLOBALH", "ETERNAL", "SBIN"])   # volume 2x+ and a 2%+ move, biggest volume first
        self.assertIn("3.1 times", out["in_watch"][1]["why"])
        self.assertIn("down 2.5%", out["in_watch"][2]["why"])

    def test_main_writes_file_and_failures(self):
        code = news.main(["--root", self.root, "--offline", os.path.join(self.root, "off")])
        self.assertEqual(code, 0)
        with open(os.path.join(self.root, "docs", "news.json"), encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("in_news", data)
        for name in os.listdir(os.path.join(self.root, "off")):
            if name.startswith("feed-"):
                os.remove(os.path.join(self.root, "off", name))
        os.remove(os.path.join(self.root, "docs", "news.json"))
        self.assertEqual(news.main(["--root", self.root, "--offline", os.path.join(self.root, "off")]), 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "docs", "news.json")))

    def test_check_mode_prints_each_feed(self):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = news.main(["--root", self.root, "--offline", os.path.join(self.root, "off"), "--check"])
        text = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("OK   ET Markets", text); self.assertIn("FAIL Dead Feed", text); self.assertIn("3 of 4 feeds worked", text)

    def test_works_without_market_data(self):
        os.remove(os.path.join(self.root, "docs", "market.json"))
        out = self.build()
        self.assertEqual(out["in_mentions"], []); self.assertEqual(out["in_watch"], [])
        self.assertTrue(out["in_news"])


if __name__ == "__main__":
    unittest.main()
