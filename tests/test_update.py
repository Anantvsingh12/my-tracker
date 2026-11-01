import datetime as dt
import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import update as up   # noqa: E402

IST = up.IST


def weekdays(end, n):
    d, out = end, []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return sorted(out)


def chart(days, closes, vols=None):
    ts = [int(dt.datetime.combine(d, dt.time(9, 15), tzinfo=IST).timestamp()) for d in days]
    return {"chart": {"error": None, "result": [{"timestamp": ts, "meta": {}, "indicators": {"quote": [{
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": vols or [1_000_000] * len(days)}]}}]}}


def series(n, start, drift, wiggle=0.004, seed=1):
    import random
    rng = random.Random(seed)
    px, out = start, []
    for i in range(n):
        px *= 1 + drift + rng.gauss(0, wiggle)
        out.append(round(px, 2))
    return out


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for d in ("data", "docs", "fx"):
            os.makedirs(os.path.join(self.root, d))
        self.days = weekdays(dt.date(2026, 10, 30), 500)
        self.write("data/universe.txt", "# comment\nUPCO|Up Company Ltd.\nDOWNCO|Down Company\nNEWCO|New Listing\nGONE|Gone Co\n")
        self.write("data/extra.txt", "NIFTYBEES|Nifty ETF\n")
        self.write("data/screens.txt", "# note\n## LT Quality Compounders\nUPCO\n## Watch\nDOWNCO\nUPCO\n")
        self.fx("^NSEI", series(500, 20000, 0.0003, seed=9))
        self.fx("UPCO.NS", series(500, 100, 0.0015, seed=2), vols=[3_000_000] * 500)
        self.fx("DOWNCO.NS", series(500, 300, -0.0012, seed=3), vols=[500_000] * 500)
        self.fx("NIFTYBEES.NS", series(500, 200, 0.0004, seed=4), vols=[2_000_000] * 500)
        self.fx("NEWCO.NS", series(40, 50, 0.001, seed=5), days=self.days[-40:])

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def fx(self, ticker, closes, vols=None, days=None):
        days = days or self.days
        with open(os.path.join(self.root, "fx", "%s_1d.json" % ticker), "w") as f:
            json.dump(chart(days, closes, vols), f)

    def build(self, **kw):
        return up.build(self.root, offline=os.path.join(self.root, "fx"), pause=0, quiet=True, **kw)


class TestLists(Fixtures):
    def test_symbol_files_and_lists(self):
        uni = up.read_symbol_file(os.path.join(self.root, "data", "universe.txt"))
        self.assertEqual([u[0] for u in uni], ["UPCO", "DOWNCO", "NEWCO", "GONE"])
        self.assertEqual(uni[0][1], "Up Company Ltd.")
        scr = up.read_symbol_file(os.path.join(self.root, "data", "screens.txt"))
        got = {}
        for s, _, names in scr:
            got.setdefault(s, []).extend(names)
        self.assertEqual(got["UPCO"], ["LT Quality Compounders", "Watch"])
        self.assertEqual(got["DOWNCO"], ["Watch"])

    def test_empty_universe_is_an_error(self):
        self.write("data/universe.txt", "# nothing\n")
        with self.assertRaises(up.UpdateError):
            up.build(self.root, offline=os.path.join(self.root, "fx"), pause=0, quiet=True)


class TestMetrics(Fixtures):
    def bars(self, closes, vols=None):
        return [(d, c, (vols or [1_000_000] * len(closes))[i]) for i, (d, c) in enumerate(zip(self.days[-len(closes):], closes))]

    def test_simple_numbers(self):
        cl = [100.0] * 300
        m = up.metrics(self.bars(cl), bench_ret12=5)
        self.assertEqual((m["dma50"], m["dma200"], m["r12m"], m["dd"], m["below200"]), (100.0, 100.0, 0.0, 0.0, 0))
        self.assertEqual(m["trend"], "MIXED")
        self.assertEqual(m["turn"], 10.0)                       # 100 * 1,000,000 = Rs 10 crore

    def test_below_200_counting_and_trend(self):
        cl = [100.0] * 250 + [90.0] * 4
        m = up.metrics(self.bars(cl))
        self.assertEqual(m["below200"], 4)
        cl = [100.0] * 250 + [90.0] * 4 + [101.0]
        self.assertEqual(up.metrics(self.bars(cl))["below200"], 0)

    def test_checks(self):
        cl = [100 * (1.001 ** i) for i in range(400)]
        m = up.metrics(self.bars(cl, [1_000_000] * 400), bench_ret12=3.0)
        self.assertEqual(m["trend"], "UP")
        self.assertEqual(m["checks"], 6, m["failed"])
        down = [200 * (0.999 ** i) for i in range(400)]
        m2 = up.metrics(self.bars(down), bench_ret12=3.0)
        self.assertEqual(m2["trend"], "DOWN")
        self.assertLess(m2["checks"], 4)
        self.assertIn("above its 200-day average", m2["failed"])
        self.assertIsNone(up.metrics(self.bars([1.0] * 10)))


class TestBuild(Fixtures):
    def test_build_output(self):
        out = self.build()
        self.assertEqual(out["last_day"], "2026-10-30")
        self.assertEqual(len(out["dates"]), 260)
        self.assertIn("UPCO", out["symbols"])
        up_, down = out["symbols"]["UPCO"], out["symbols"]["DOWNCO"]
        self.assertEqual(up_["m"]["trend"], "UP")
        self.assertEqual(down["m"]["trend"], "DOWN")
        self.assertEqual(up_["L"], ["LT Quality Compounders", "Watch"])
        self.assertEqual(len(up_["c"]), 260)
        self.assertEqual(up_["p"], up_["c"][-1])
        self.assertIn("NIFTYBEES", out["symbols"])
        self.assertIn("NEWCO", out["symbols"])                  # short history still listed
        self.assertEqual(out["symbols"]["NEWCO"]["c"].count(None), 220)
        self.assertNotIn("checks", out["symbols"]["NEWCO"]["m"])
        self.assertNotIn("GONE", out["symbols"])
        self.assertTrue(any(e.startswith("GONE") for e in out["errors"]))
        self.assertEqual(out["asof"][-3:], "IST")

    def test_main_writes_file_and_keeps_stale(self):
        code = up.main(["--root", self.root, "--offline", os.path.join(self.root, "fx"), "--pause", "0", "--quiet"])
        self.assertEqual(code, 0)
        path = os.path.join(self.root, "docs", "market.json")
        with open(path) as f:
            first = json.load(f)
        self.assertGreater(os.path.getsize(path), 5000)
        os.remove(os.path.join(self.root, "fx", "DOWNCO.NS_1d.json"))       # Yahoo "forgets" one stock
        out = self.build()
        self.assertTrue(out["symbols"]["DOWNCO"]["stale"])
        self.assertEqual(out["symbols"]["DOWNCO"]["p"], first["symbols"]["DOWNCO"]["p"])
        self.assertNotIn("stale", out["symbols"]["UPCO"])

    def test_refuses_to_overwrite_with_a_mostly_empty_run(self):
        for t in ("UPCO.NS", "DOWNCO.NS", "NIFTYBEES.NS", "NEWCO.NS"):
            os.remove(os.path.join(self.root, "fx", "%s_1d.json" % t))
        with self.assertRaises(up.UpdateError):
            self.build()
        self.assertFalse(os.path.exists(os.path.join(self.root, "docs", "market.json")))
        os.remove(os.path.join(self.root, "fx", "^NSEI_1d.json"))
        with self.assertRaises(up.UpdateError):
            self.build()

    def test_limit_keeps_screen_symbols(self):
        out = self.build(limit=1)
        self.assertIn("UPCO", out["symbols"])
        self.assertIn("DOWNCO", out["symbols"])                 # on a list, so always kept
        self.assertNotIn("NEWCO", out["symbols"])


if __name__ == "__main__":
    unittest.main()
