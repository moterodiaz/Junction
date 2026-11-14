#!/usr/bin/env bash
# Acceptance check for the iOS tasks. Runs on the CI runner without Xcode,
# and also runs the Swift package tests when a toolchain is installed.
set -euo pipefail
cd "$(dirname "$0")"
python3 tests/test_client.py
if command -v swift >/dev/null 2>&1; then
  swift test --package-path MetaLabCore
fi
