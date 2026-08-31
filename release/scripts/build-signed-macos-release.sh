#!/bin/bash
set -euo pipefail

# Intentionally never enable xtrace in this script: several inputs are secrets.

if [[ "$#" -ne 2 ]]; then
    echo "Usage: $0 REPOSITORY_ROOT OUTPUT_DIRECTORY" >&2
    exit 2
fi

readonly repository_root="$(cd "$1" && pwd)"
readonly output_directory="$2"
readonly canonical_release="$repository_root/macos/scripts/release.sh"

require_value() {
    local name="$1"
    if [[ -z "${!name:-}" ]]; then
        printf 'ERROR: required release configuration is absent: %s\n' "$name" >&2
        exit 2
    fi
}

for name in \
    APPLE_APPLICATION_P12_BASE64 \
    APPLE_APPLICATION_P12_PASSWORD \
    APPLE_INSTALLER_P12_BASE64 \
    APPLE_INSTALLER_P12_PASSWORD \
    APPLE_NOTARY_KEY_P8_BASE64 \
    APPLE_NOTARY_KEY_ID \
    APPLE_NOTARY_ISSUER_ID \
    DEVELOPER_ID_APPLICATION \
    DEVELOPER_ID_INSTALLER \
    SINBAR_TEAM_IDENTIFIER \
    BUILD_NUMBER \
    MANIFEST_KEY_ID \
    MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL \
    RUSTDESK_BUNDLE_IDENTIFIER \
    RUSTDESK_TEAM_IDENTIFIER \
    RUSTDESK_X86_64_DMG_SHA256 \
    RUSTDESK_ARM64_DMG_SHA256
do
    require_value "$name"
done

[[ "$(uname -s)" == "Darwin" ]] || {
    echo 'ERROR: this release must run on a macOS runner' >&2
    exit 2
}
[[ -x "$canonical_release" ]] || {
    echo 'ERROR: canonical macOS release script is missing or not executable' >&2
    exit 2
}
[[ "$SINBAR_TEAM_IDENTIFIER" =~ ^[A-Z0-9]{10}$ ]] || {
    echo 'ERROR: SINBAR_TEAM_IDENTIFIER must be a ten-character Apple Team ID' >&2
    exit 2
}
[[ "$MANIFEST_KEY_ID" == "sinbar-support-manifest-p256-v1" ]] || {
    echo 'ERROR: MANIFEST_KEY_ID must be sinbar-support-manifest-p256-v1' >&2
    exit 2
}
[[ "$RUSTDESK_BUNDLE_IDENTIFIER" == "com.carriez.rustdesk" ]] || {
    echo 'ERROR: RUSTDESK_BUNDLE_IDENTIFIER must be com.carriez.rustdesk' >&2
    exit 2
}
case "$DEVELOPER_ID_APPLICATION" in
    *"($SINBAR_TEAM_IDENTIFIER)"*) ;;
    *) echo 'ERROR: Developer ID Application identity does not match Apple Team ID' >&2; exit 2 ;;
esac
case "$DEVELOPER_ID_INSTALLER" in
    *"($SINBAR_TEAM_IDENTIFIER)"*) ;;
    *) echo 'ERROR: Developer ID Installer identity does not match Apple Team ID' >&2; exit 2 ;;
esac

readonly temp_parent="${RUNNER_TEMP:-/tmp}"
temp_dir="$(mktemp -d "$temp_parent/sinbar-release-signing.XXXXXX")"
readonly temp_dir
readonly application_p12="$temp_dir/application.p12"
readonly installer_p12="$temp_dir/installer.p12"
readonly notary_key="$temp_dir/AuthKey.p8"
readonly keychain="$temp_dir/release.keychain-db"
readonly keychain_password="$(uuidgen)$(uuidgen)"
readonly notary_profile="sinbar-release-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"

original_default_keychain="$(security default-keychain -d user 2>/dev/null | tr -d '"' | xargs || true)"
original_keychains=()
while IFS= read -r line; do
    cleaned="$(printf '%s' "$line" | tr -d '"' | xargs)"
    [[ -n "$cleaned" ]] && original_keychains+=("$cleaned")
done < <(security list-keychains -d user 2>/dev/null || true)

cleanup() {
    local status=$?
    if [[ -n "$original_default_keychain" ]]; then
        security default-keychain -d user -s "$original_default_keychain" \
            >/dev/null 2>&1 || true
    fi
    if [[ "${#original_keychains[@]}" -gt 0 ]]; then
        security list-keychains -d user -s "${original_keychains[@]}" \
            >/dev/null 2>&1 || true
    fi
    security delete-keychain "$keychain" >/dev/null 2>&1 || true
    rm -rf "$temp_dir"
    unset \
        APPLE_APPLICATION_P12_BASE64 \
        APPLE_APPLICATION_P12_PASSWORD \
        APPLE_INSTALLER_P12_BASE64 \
        APPLE_INSTALLER_P12_PASSWORD \
        APPLE_NOTARY_KEY_P8_BASE64 \
        APPLE_NOTARY_KEY_ID \
        APPLE_NOTARY_ISSUER_ID
    exit "$status"
}
trap cleanup EXIT HUP INT TERM

decode_secret() {
    local variable_name="$1"
    local destination="$2"
    printf '%s' "${!variable_name}" | \
        /usr/bin/openssl base64 -d -A >"$destination"
    chmod 0600 "$destination"
    [[ -s "$destination" ]] || {
        printf 'ERROR: decoded secret is empty: %s\n' "$variable_name" >&2
        exit 2
    }
}

decode_secret APPLE_APPLICATION_P12_BASE64 "$application_p12"
decode_secret APPLE_INSTALLER_P12_BASE64 "$installer_p12"
decode_secret APPLE_NOTARY_KEY_P8_BASE64 "$notary_key"

security create-keychain -p "$keychain_password" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$keychain_password" "$keychain"
security list-keychains -d user -s "$keychain" "${original_keychains[@]}"
security default-keychain -d user -s "$keychain"

security import "$application_p12" \
    -k "$keychain" \
    -P "$APPLE_APPLICATION_P12_PASSWORD" \
    -T /usr/bin/codesign
security import "$installer_p12" \
    -k "$keychain" \
    -P "$APPLE_INSTALLER_P12_PASSWORD" \
    -T /usr/bin/pkgbuild \
    -T /usr/bin/productsign
security set-key-partition-list \
    -S apple-tool:,apple: \
    -s \
    -k "$keychain_password" \
    "$keychain" >/dev/null

security find-certificate -c "$DEVELOPER_ID_APPLICATION" "$keychain" >/dev/null
security find-certificate -c "$DEVELOPER_ID_INSTALLER" "$keychain" >/dev/null

xcrun notarytool store-credentials "$notary_profile" \
    --key "$notary_key" \
    --key-id "$APPLE_NOTARY_KEY_ID" \
    --issuer "$APPLE_NOTARY_ISSUER_ID" \
    --keychain "$keychain"

# From here on the build needs only public pins, signing identities, and the
# temporary keychain profile. Do not expose raw credentials to compiler tools.
unset \
    APPLE_APPLICATION_P12_BASE64 \
    APPLE_APPLICATION_P12_PASSWORD \
    APPLE_INSTALLER_P12_BASE64 \
    APPLE_INSTALLER_P12_PASSWORD \
    APPLE_NOTARY_KEY_P8_BASE64 \
    APPLE_NOTARY_KEY_ID \
    APPLE_NOTARY_ISSUER_ID
rm -f "$application_p12" "$installer_p12" "$notary_key"
export NOTARYTOOL_PROFILE="$notary_profile"
export NOTARYTOOL_KEYCHAIN="$keychain"

(
    cd "$repository_root/macos"
    scripts/release.sh
)

readonly source_package="$repository_root/macos/dist/Sinbar-Support-Assistant.pkg"
[[ -f "$source_package" && ! -L "$source_package" ]] || {
    echo 'ERROR: canonical macOS build did not produce the expected package' >&2
    exit 1
}

signature_report="$temp_dir/pkg-signature.txt"
/usr/sbin/pkgutil --check-signature "$source_package" | tee "$signature_report"
grep -F -- "$DEVELOPER_ID_INSTALLER" "$signature_report" >/dev/null || {
    echo 'ERROR: final package is signed by the wrong Developer ID Installer' >&2
    exit 1
}
grep -F -- "$SINBAR_TEAM_IDENTIFIER" "$signature_report" >/dev/null || {
    echo 'ERROR: final package signature does not contain the configured Team ID' >&2
    exit 1
}
xcrun stapler validate "$source_package"
/usr/sbin/spctl --assess --type install --verbose=4 "$source_package"

mkdir -p "$output_directory"
destination="$output_directory/Sinbar-Support-Assistant.pkg"
/usr/bin/ditto "$source_package" "$destination"
echo 'PASS: Developer ID signed, notarized, and stapled macOS release is ready'
echo "artifact=$destination"
