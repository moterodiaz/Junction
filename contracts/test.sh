#!/usr/bin/env bash
# Validate the shared WebSocket JSON Schema and all valid/invalid fixtures in contracts/.
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
.venv/bin/python -m unittest discover -s . -t . -p 'test_*.py' -v
