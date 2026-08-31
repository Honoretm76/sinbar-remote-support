#!/bin/bash
set -euo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly project_dir="$(cd "$script_dir/.." && pwd)"
readonly package_path="$project_dir/dist/Sinbar-Support-Assistant.pkg"

: "${NOTARYTOOL_PROFILE:?NOTARYTOOL_PROFILE keychain profile is required}"
[[ "$(uname -s)" == "Darwin" ]] || exit 2
test -f "$package_path"

notary_arguments=(
    submit "$package_path"
    --keychain-profile "$NOTARYTOOL_PROFILE"
)
if [[ -n "${NOTARYTOOL_KEYCHAIN:-}" ]]; then
    test -f "$NOTARYTOOL_KEYCHAIN" || {
        echo 'ERROR: NOTARYTOOL_KEYCHAIN does not identify a file keychain' >&2
        exit 2
    }
    notary_arguments+=(--keychain "$NOTARYTOOL_KEYCHAIN")
fi
notary_arguments+=(--wait)

xcrun notarytool "${notary_arguments[@]}"
xcrun stapler staple "$package_path"
xcrun stapler validate "$package_path"
/usr/sbin/spctl --assess --type install --verbose=4 "$package_path"
/usr/sbin/pkgutil --check-signature "$package_path"

echo "PASS: signed, notarized, and stapled package: $package_path"
