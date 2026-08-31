#!/bin/bash
set -euo pipefail

readonly script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly project_dir="$(cd "$script_dir/.." && pwd)"
readonly build_dir="$project_dir/build"
readonly release_dir="$build_dir/release"
readonly app_name="Sinbar Support Assistant.app"
readonly app_dir="$release_dir/$app_name"
readonly helper_name="com.sinbarconsultants.supportassistant.installhelper"

require_value() {
    local name="$1"
    if [[ -z "${!name:-}" ]]; then
        printf 'ERROR: required public release value %s is not set\n' "$name" >&2
        exit 2
    fi
}

for name in \
    BUILD_NUMBER \
    DEVELOPER_ID_APPLICATION \
    SINBAR_TEAM_IDENTIFIER \
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
    echo 'ERROR: macOS and Xcode command-line tools are required' >&2
    exit 2
}
[[ "$BUILD_NUMBER" =~ ^[1-9][0-9]*$ ]] || {
    echo 'ERROR: BUILD_NUMBER must be a positive integer' >&2
    exit 2
}
[[ "$DEVELOPER_ID_APPLICATION" == "Developer ID Application:"* ]] || {
    echo 'ERROR: a Developer ID Application identity is required; ad-hoc signing is refused' >&2
    exit 2
}
[[ "$SINBAR_TEAM_IDENTIFIER" =~ ^[A-Z0-9]{10}$ ]] || exit 2
[[ "$RUSTDESK_TEAM_IDENTIFIER" =~ ^[A-Z0-9]{10}$ ]] || exit 2
[[ "$RUSTDESK_BUNDLE_IDENTIFIER" == "com.carriez.rustdesk" ]] || {
    echo 'ERROR: RUSTDESK_BUNDLE_IDENTIFIER must equal com.carriez.rustdesk' >&2
    exit 2
}
[[ "$MANIFEST_KEY_ID" =~ ^[A-Za-z0-9._-]{1,64}$ ]] || exit 2
[[ "$MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL" =~ ^[A-Za-z0-9_-]{87}$ ]] || {
    echo 'ERROR: manifest key must be a 65-byte X9.63 P-256 point encoded as base64url' >&2
    exit 2
}
[[ "$RUSTDESK_X86_64_DMG_SHA256" =~ ^[0-9a-f]{64}$ ]] || exit 2
[[ "$RUSTDESK_ARM64_DMG_SHA256" =~ ^[0-9a-f]{64}$ ]] || exit 2

rm -rf "$build_dir/swift-arm64" "$build_dir/swift-x86_64" "$release_dir"
mkdir -p "$release_dir"

swift build \
    --package-path "$project_dir" \
    --scratch-path "$build_dir/swift-arm64" \
    --configuration release \
    --arch arm64

swift build \
    --package-path "$project_dir" \
    --scratch-path "$build_dir/swift-x86_64" \
    --configuration release \
    --arch x86_64

binary_for() {
    local scratch="$1"
    local product="$2"
    find "$scratch" -type f -perm -111 -name "$product" -print -quit
}

arm_app="$(binary_for "$build_dir/swift-arm64" SinbarSupportAssistant)"
x64_app="$(binary_for "$build_dir/swift-x86_64" SinbarSupportAssistant)"
arm_helper="$(binary_for "$build_dir/swift-arm64" SinbarSupportInstallHelper)"
x64_helper="$(binary_for "$build_dir/swift-x86_64" SinbarSupportInstallHelper)"

for file in "$arm_app" "$x64_app" "$arm_helper" "$x64_helper"; do
    [[ -n "$file" && -f "$file" ]] || {
        echo 'ERROR: an expected Swift release binary was not produced' >&2
        exit 1
    }
done

mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources"
cp "$project_dir/Info.plist.template" "$app_dir/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NUMBER" "$app_dir/Contents/Info.plist"

/usr/bin/lipo -create "$arm_app" "$x64_app" \
    -output "$app_dir/Contents/MacOS/SinbarSupportAssistant"
/usr/bin/lipo -create "$arm_helper" "$x64_helper" \
    -output "$release_dir/$helper_name"
chmod 0755 \
    "$app_dir/Contents/MacOS/SinbarSupportAssistant" \
    "$release_dir/$helper_name"

cp "$project_dir/Config/runtime-config.plist.template" \
    "$release_dir/runtime-config.plist"
/usr/libexec/PlistBuddy -c "Set :ManifestKeyID $MANIFEST_KEY_ID" \
    "$release_dir/runtime-config.plist"
/usr/libexec/PlistBuddy -c "Set :ManifestP256PublicKeyX963Base64URL $MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL" \
    "$release_dir/runtime-config.plist"
/usr/libexec/PlistBuddy -c "Set :RustDeskBundleIdentifier $RUSTDESK_BUNDLE_IDENTIFIER" \
    "$release_dir/runtime-config.plist"
/usr/libexec/PlistBuddy -c "Set :RustDeskTeamIdentifier $RUSTDESK_TEAM_IDENTIFIER" \
    "$release_dir/runtime-config.plist"
/usr/libexec/PlistBuddy -c "Set :SinbarTeamIdentifier $SINBAR_TEAM_IDENTIFIER" \
    "$release_dir/runtime-config.plist"
/usr/libexec/PlistBuddy -c "Set :RustDeskArtifacts:x86_64:SHA256 $RUSTDESK_X86_64_DMG_SHA256" \
    "$release_dir/runtime-config.plist"
/usr/libexec/PlistBuddy -c "Set :RustDeskArtifacts:arm64:SHA256 $RUSTDESK_ARM64_DMG_SHA256" \
    "$release_dir/runtime-config.plist"

plutil -lint "$app_dir/Contents/Info.plist" "$release_dir/runtime-config.plist"

/usr/bin/codesign --force --timestamp --options runtime \
    --identifier "$helper_name" \
    --sign "$DEVELOPER_ID_APPLICATION" \
    "$release_dir/$helper_name"

/usr/bin/codesign --force --timestamp --options runtime \
    --entitlements "$project_dir/Entitlements.plist" \
    --sign "$DEVELOPER_ID_APPLICATION" \
    "$app_dir"

/usr/bin/codesign --verify --deep --strict --all-architectures --verbose=2 "$app_dir"
/usr/bin/codesign --verify --strict --all-architectures --verbose=2 \
    "$release_dir/$helper_name"

app_team="$(/usr/bin/codesign -d --verbose=4 "$app_dir" 2>&1 \
    | /usr/bin/sed -n 's/^TeamIdentifier=//p')"
helper_team="$(/usr/bin/codesign -d --verbose=4 "$release_dir/$helper_name" 2>&1 \
    | /usr/bin/sed -n 's/^TeamIdentifier=//p')"
[[ "$app_team" == "$SINBAR_TEAM_IDENTIFIER" \
   && "$helper_team" == "$SINBAR_TEAM_IDENTIFIER" ]] || {
    echo 'ERROR: signed Sinbar Team Identifier does not match the runtime pin' >&2
    exit 1
}

echo "PASS: signed universal app: $app_dir"
echo "PASS: signed universal helper: $release_dir/$helper_name"
echo "PASS: generated public runtime pins: $release_dir/runtime-config.plist"
