#!/usr/bin/env bash
# Acceptance check for the iOS tasks. Runs on the CI runner without Xcode,
# and also runs the Swift package tests when a toolchain is installed.
# In CI the Swift tests are required: a missing toolchain fails the run.
set -euo pipefail
cd "$(dirname "$0")"
python3 tests/test_client.py
if command -v swift >/dev/null 2>&1; then
  swift test --package-path MetaLabCore
elif [ -n "${CI:-}" ]; then
  echo "::error::swift not found; CI must run the MetaLabCore tests" >&2
  exit 1
else
  echo "swift not found; skipping MetaLabCore tests (local run)" >&2
fi
