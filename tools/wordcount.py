#!/usr/bin/env python3
"""Count word frequencies in a text file. Usage: tools/wordcount.py FILE [top_n]"""
import sys


def top_words(path, top_n=10, counts=None):
    if counts is None:
        counts = {}
    with open(path) as f:
        for line in f:
            for word in line.split():
                counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:top_n]


if __name__ == "__main__":
    for word, n in top_words(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 10):
        print(n, word)
