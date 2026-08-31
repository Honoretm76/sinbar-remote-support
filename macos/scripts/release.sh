#!/bin/bash
set -euo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$script_dir/build-app.sh"
"$script_dir/build-pkg.sh"
"$script_dir/notarize.sh"
