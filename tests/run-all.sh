#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash "$root/portal/tests/run.sh"
python3 "$root/windows/tests/linux/validate_source.py"
bash "$root/macos/tests/run-linux-tests.sh"
python3 "$root/release/scripts/validate_release_contract.py" \
  --repository-root "$root" \
  --tag v2.0.0 \
  --manifest-key-id sinbar-support-manifest-p256-v1
python3 "$root/tests/validate_integration.py"

(
  cd "$root/server"
  PYTHONPATH=. uv run --isolated \
    --with 'pytest==8.4.2' \
    --with 'Flask==3.1.2' \
    --with 'cryptography==46.0.0' \
    pytest -q tests
)

echo "PASS: all portable source and contract tests completed"
