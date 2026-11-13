#!/usr/bin/env python3
"""Copy docs/logic.js into docs/index.html so the page works as a single file.
Run after editing docs/logic.js:  python scripts/inline_logic.py"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARK = "/* ---- logic.js, inlined so this page works on its own ---- */"


def main():
    page_path = os.path.join(ROOT, "docs", "index.html")
    with open(os.path.join(ROOT, "docs", "logic.js"), encoding="utf-8") as f:
        logic = f.read().strip()
    with open(page_path, encoding="utf-8") as f:
        page = f.read()
    a = page.index(MARK) + len(MARK)
    b = page.index("</script>", a)
    page = page[:a] + "\n" + logic + "\n" + page[b:]
    with open(page_path, "w", encoding="utf-8") as f:
        f.write(page)
    print("inlined logic.js into docs/index.html")


if __name__ == "__main__":
    sys.exit(main())
