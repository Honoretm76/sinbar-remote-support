#!/bin/bash
set -euo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly project_dir="$(cd "$script_dir/.." && pwd)"
readonly release_dir="$project_dir/build/release"
readonly package_root="$project_dir/build/package-root"
readonly dist_dir="$project_dir/dist"
readonly helper_name="com.sinbarconsultants.supportassistant.installhelper"
readonly output_pkg="$dist_dir/Sinbar-Support-Assistant.pkg"

: "${DEVELOPER_ID_INSTALLER:?DEVELOPER_ID_INSTALLER is required}"
: "${SINBAR_TEAM_IDENTIFIER:?SINBAR_TEAM_IDENTIFIER is required}"
[[ "$(uname -s)" == "Darwin" ]] || exit 2
[[ "$DEVELOPER_ID_INSTALLER" == "Developer ID Installer:"* ]] || {
    echo 'ERROR: a Developer ID Installer identity is required' >&2
    exit 2
}
[[ "$SINBAR_TEAM_IDENTIFIER" =~ ^[A-Z0-9]{10}$ ]] || exit 2

test -d "$release_dir/Sinbar Support Assistant.app"
test -x "$release_dir/$helper_name"
test -f "$release_dir/runtime-config.plist"

rm -rf "$package_root" "$dist_dir"
mkdir -p \
    "$package_root/Applications" \
    "$package_root/Library/PrivilegedHelperTools" \
    "$package_root/Library/LaunchDaemons" \
    "$package_root/Library/Application Support/Sinbar Support Assistant" \
    "$dist_dir"

/usr/bin/ditto "$release_dir/Sinbar Support Assistant.app" \
    "$package_root/Applications/Sinbar Support Assistant.app"
install -m 0755 "$release_dir/$helper_name" \
    "$package_root/Library/PrivilegedHelperTools/$helper_name"
install -m 0644 \
    "$project_dir/Config/com.sinbarconsultants.supportassistant.installhelper.plist.template" \
    "$package_root/Library/LaunchDaemons/$helper_name.plist"
install -m 0644 "$release_dir/runtime-config.plist" \
    "$package_root/Library/Application Support/Sinbar Support Assistant/config.plist"
chmod 0755 "$project_dir/scripts/package-scripts/preinstall" \
    "$project_dir/scripts/package-scripts/postinstall"

/usr/bin/pkgbuild \
    --root "$package_root" \
    --scripts "$project_dir/scripts/package-scripts" \
    --identifier com.sinbarconsultants.supportassistant.pkg \
    --version 2.0.0 \
    --install-location / \
    --ownership recommended \
    --sign "$DEVELOPER_ID_INSTALLER" \
    "$output_pkg"

signature_output="$(/usr/sbin/pkgutil --check-signature "$output_pkg")"
printf '%s\n' "$signature_output"
printf '%s\n' "$signature_output" \
    | /usr/bin/grep -Eq "Developer ID Installer:.*\\($SINBAR_TEAM_IDENTIFIER\\)" || {
        echo 'ERROR: package signer does not match SINBAR_TEAM_IDENTIFIER' >&2
        exit 1
    }
echo "PASS: signed package created: $output_pkg"
