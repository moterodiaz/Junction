#!/usr/bin/env bash
# Backend tests for every backend area (app, stt, ai). CI runs this from backend/.
# Tests are unittest files named test_*.py; each folder they live in needs an __init__.py.
# Dependencies go into backend/.venv (created on first run) from requirements.txt.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
if command -v timeout >/dev/null 2>&1; then
  run_with_deadline() { timeout 300 "$@"; }
elif command -v gtimeout >/dev/null 2>&1; then
  run_with_deadline() { gtimeout 300 "$@"; }
else
  run_with_deadline() { "$@"; }
fi
run_with_deadline .venv/bin/python -m unittest discover -s . -t . -p 'test_*.py' -v
