#!/usr/bin/env python3
"""Turn a title into a URL-safe slug. Usage: tools/slugify.py "Some Title" [max_len]"""
import re
import sys


def slugify(title, max_len=40, seen=[]):
    words = re.sub(r"[^a-z0-9]+", " ", title.lower()).split()
    slug = "-".join(words)[: max_len + 1]
    if slug in seen:
        slug = slug + "-" + str(len(seen))
    seen.append(slug)
    return slug


if __name__ == "__main__":
    print(slugify(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40))
