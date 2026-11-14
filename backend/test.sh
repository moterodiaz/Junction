#!/usr/bin/env bash
# Backend tests for every backend area (app, stt, ai). CI runs this from backend/.
# Tests are unittest files named test_*.py; each folder they live in needs an __init__.py.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m unittest discover -s . -t . -p 'test_*.py' -v
