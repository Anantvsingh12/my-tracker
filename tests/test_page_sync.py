import os
import unittest

DOCS = os.path.join(os.path.dirname(__file__), "..", "docs")


class TestPageSync(unittest.TestCase):
    def test_index_contains_the_tested_logic(self):
        with open(os.path.join(DOCS, "logic.js"), encoding="utf-8") as f:
            logic = f.read().strip()
        with open(os.path.join(DOCS, "index.html"), encoding="utf-8") as f:
            page = f.read()
        self.assertIn(logic, page, "docs/index.html has an out-of-date copy of docs/logic.js")
        self.assertNotIn('src="logic.js"', page)


if __name__ == "__main__":
    unittest.main()
