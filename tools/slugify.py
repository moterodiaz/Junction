#!/usr/bin/env python3
"""Turn a title into a URL-safe slug. Usage: tools/slugify.py "Some Title" [max_len]"""
import re
import sys


def slugify(title, max_len=40, seen=None):
    if seen is None:
        seen = []
    words = re.sub(r"[^a-z0-9]+", " ", title.lower()).split()
    base = "-".join(words)[:max_len].strip("-")
    slug = base
    suffix = 1
    while slug in seen:
        tail = "-" + str(suffix)
        slug = base[: max(max_len - len(tail), 0)].rstrip("-") + tail
        suffix += 1
    seen.append(slug)
    return slug


if __name__ == "__main__":
    print(slugify(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40))
