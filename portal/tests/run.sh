#!/usr/bin/env sh
set -eu

test_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
portal_dir="$(dirname "$test_dir")"

python3 "$test_dir/validate_portal.py"

if command -v node >/dev/null 2>&1; then
  node --check "$portal_dir/assets/app.js"
  printf '%s\n' "PASS: JavaScript syntax verified"
else
  printf '%s\n' "SKIP: Node.js is unavailable; JavaScript syntax check skipped"
fi
