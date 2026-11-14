"""Rewrite an exchange's recorded replies from the live backend: .venv/bin/python record.py <name>...

Run only for an intentional contract change, then review the diff of exchanges/<name>.json.
"""

from __future__ import annotations

import json
import sys

from test_conformance import EXCHANGES_DIR, drive, load, names


def main(argv: list[str]) -> int:
    if not argv:
        print(f"usage: record.py <name>...  (one of: {', '.join(names())})", file=sys.stderr)
        return 1
    for name in argv:
        exchange = load(name)
        exchange["receive"] = drive(exchange)
        path = EXCHANGES_DIR / f"{name}.json"
        path.write_text(json.dumps(exchange, indent=2) + "\n", encoding="utf-8")
        print(f"recorded {len(exchange['receive'])} replies into {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
