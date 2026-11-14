#!/usr/bin/env bash
# Backend tests for every backend area (app, stt, ai). CI runs this from backend/.
# Tests are unittest files named test_*.py; each folder they live in needs an __init__.py.
# Dependencies go into backend/.venv (created on first run) from requirements.txt.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
.venv/bin/python -m unittest discover -s . -t . -p 'test_*.py' -v
