# Sinbar Support Assistant for macOS 2.0.0

This directory contains the **source** for the macOS half of Sinbar's Intel-style
remote-support experience. It deliberately contains no compiled, signed, or notarized
binary. A real Apple Developer ID and independently verified RustDesk release identities
are required before a production package can exist.

## Customer experience

1. On the first visit, the customer downloads and opens
   `Sinbar-Support-Assistant.pkg` and approves one normal macOS administrator prompt.
   The signed package installs the Sinbar app and its narrowly scoped local helper.
2. The customer clicks **Start Remote Support** on
   `https://support.sinbarconsultants.com`.
3. The browser opens `sinbarsupport://start?token=<one-time-token>` in the installed app.
4. The app redeems the one-time token only with the pinned Sinbar HTTPS endpoint and
   verifies a P-256 signed release manifest.
5. A native macOS confirmation names the attended RustDesk action. **Cancel** is the
   first, Return-default, and Escape action. Only deliberate selection of **Continue**
   permits download, installation, or launch; cancellation closes the assistant without
   invoking its helper or opening RustDesk.
6. After consent, the app downloads the exact locally pinned RustDesk DMG and asks the
   root helper to install it. The helper independently repeats the manifest, hash,
   publisher, version, and Gatekeeper checks before installing RustDesk in `/Applications`.
7. RustDesk opens in attended mode and the Sinbar assistant closes. No password,
   unattended access credential, shell command, or arbitrary executable argument is
   accepted from the website or API.

The software still executes on the Mac. The NOC server authenticates and coordinates the
flow; macOS does not permit a website to execute a native installer remotely.

## Security boundaries

- The only accepted deep link is exactly
  `sinbarsupport://start?token=<43-character-base64url-token>`.
- The only API call is `POST
  https://support.sinbarconsultants.com/api/v1/support/sessions/consume`.
- Redirects, cookies, caches, alternate origins, explicit ports, fragments, userinfo,
  duplicate parameters, extra parameters, and encoded token characters are rejected.
- The API response is an ECDSA P-256/SHA-256 envelope. The public verification key and
  key ID are installed as root-owned public configuration. The 64-byte signature is
  IEEE-P1363 `r || s`; the public key is a 65-byte ANSI X9.63 uncompressed point.
- The signed manifest is verified **before** its payload is parsed. Its action is fixed to
  `ensure-and-launch-rustdesk`, `attended` must be `true`, and its lifetime cannot exceed
  five minutes.
- After manifest authentication, a native AppKit confirmation is mandatory before both
  the already-installed launch path and the download/helper/install path. Cancellation
  terminates without installing or launching anything.
- The exact RustDesk URL, SHA-256, version, bundle identifier, and Apple Team Identifier
  must match a root-owned local release catalog. A signed server response cannot replace
  these local pins.
- The helper has no network listener and no network client. It accepts one XPC method
  from the correctly signed Sinbar GUI app and performs one fixed RustDesk install. Both
  XPC peers require the pinned identifier and Team ID under a Developer ID Application
  leaf and Developer ID intermediate certificate.
- The downloaded artifact must be a private `0600` regular file owned by the invoking
  user under Sinbar's `0700` cache directory.
- A DMG is mounted read-only. Exactly one non-symlink `RustDesk.app` is accepted. Strict
  Apple code-signature, all-architecture, nested-code, Team ID, bundle ID, version, and
  Gatekeeper checks run before and after installation.
- Existing `/Applications/RustDesk.app` is never replaced unless it already has the
  pinned identity. The candidate is staged under a root-only directory on the same
  volume, then exchanged with `RENAME_SWAP` in one filesystem transaction. A crash can
  leave either verified version installed, but cannot create a missing-app interval.
- The code never removes quarantine attributes, disables Gatekeeper, opens Terminal,
  runs a remote command, creates a permanent password, or bypasses macOS privacy controls.

Screen Recording and Accessibility approval remain visible Apple-controlled customer
steps. They cannot and must not be bypassed. Managed Macs may pre-authorize supported
privacy settings through an approved MDM/PPPC policy, subject to Apple's rules.

## Canonical API contract

Request body:

```json
{
  "token": "43-character-base64url-token",
  "platform": "macos",
  "architecture": "arm64",
  "assistantVersion": "2.0.0"
}
```

Envelope (the API's JSON response):

```json
{
  "keyId": "release-key-2026-01",
  "payload": "base64url-of-the-exact-UTF8-manifest-bytes",
  "signature": "base64url-of-64-byte-P256-IEEE-P1363-signature"
}
```

Signed manifest payload:

```json
{
  "schemaVersion": 1,
  "sessionId": "9a1c4aec-fd8c-4be5-acca-a863cfb2a433",
  "action": "ensure-and-launch-rustdesk",
  "attended": true,
  "platform": "macos",
  "architecture": "arm64",
  "issuedAt": "2026-08-31T12:00:00Z",
  "expiresAt": "2026-08-31T12:02:00Z",
  "artifact": {
    "kind": "dmg",
    "url": "https://support.sinbarconsultants.com/download/vendor/rustdesk/1.4.9/macos/rustdesk-1.4.9-aarch64.dmg",
    "sha256": "64-lowercase-hex-characters",
    "version": "1.4.9",
    "bundleIdentifier": "com.carriez.rustdesk",
    "teamIdentifier": "VERIFIED10"
  }
}
```

The server must generate a random 256-bit token, store only a token hash, enforce a short
TTL, redeem it atomically once, never log it, and bind the response to the requested
platform and architecture. The token authorizes only creation of this attended launch
manifest; it is not a RustDesk credential.

## Required production values

All values below are public release metadata, not secrets:

| Environment variable | Requirement |
|---|---|
| `BUILD_NUMBER` | Positive integer `CFBundleVersion` |
| `DEVELOPER_ID_APPLICATION` | Keychain identity for the app and helper |
| `DEVELOPER_ID_INSTALLER` | Keychain identity for the installer package |
| `SINBAR_TEAM_IDENTIFIER` | Team ID matching both Sinbar code signatures |
| `MANIFEST_KEY_ID` | Active server manifest verification key ID |
| `MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL` | 65-byte public P-256 X9.63 point, base64url |
| `RUSTDESK_BUNDLE_IDENTIFIER` | Must be the protocol pin `com.carriez.rustdesk` |
| `RUSTDESK_TEAM_IDENTIFIER` | Inspected from the exact approved RustDesk release |
| `RUSTDESK_X86_64_DMG_SHA256` | SHA-256 of the mirrored Intel DMG |
| `RUSTDESK_ARM64_DMG_SHA256` | SHA-256 of the mirrored Apple Silicon DMG |
| `NOTARYTOOL_PROFILE` | Existing `notarytool` keychain profile name |
| `NOTARYTOOL_KEYCHAIN` | Optional file keychain path containing that profile |

Never guess the RustDesk Team ID, bundle ID, or hashes. Inspect the exact official release,
verify it independently, mirror those unchanged bytes, and then populate these values.

## Build, sign, package, and notarize

Requirements: macOS 13 or newer, current Xcode command-line tools, Swift 5.9 or newer,
Developer ID Application and Installer certificates, and a configured notarytool profile.

```bash
cd macos
export BUILD_NUMBER=1
export DEVELOPER_ID_APPLICATION='Developer ID Application: Sinbar Consultants LLC (TEAMID)'
export DEVELOPER_ID_INSTALLER='Developer ID Installer: Sinbar Consultants LLC (TEAMID)'
export SINBAR_TEAM_IDENTIFIER='TEAMIDHERE'
export MANIFEST_KEY_ID='release-key-2026-01'
export MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL='PUBLIC_KEY_ONLY'
export RUSTDESK_BUNDLE_IDENTIFIER='INSPECTED_VALUE'
export RUSTDESK_TEAM_IDENTIFIER='INSPECTED_VALUE'
export RUSTDESK_X86_64_DMG_SHA256='INSPECTED_64_HEX_VALUE'
export RUSTDESK_ARM64_DMG_SHA256='INSPECTED_64_HEX_VALUE'
export NOTARYTOOL_PROFILE='sinbar-notary'
scripts/release.sh
```

Expected outputs:

- `build/release/Sinbar Support Assistant.app`
- `build/release/com.sinbarconsultants.supportassistant.installhelper`
- `build/release/runtime-config.plist`
- `dist/Sinbar-Support-Assistant.pkg` (signed, notarized, and stapled)

The deployment path is:

`/download/v2.0.0/macos/Sinbar-Support-Assistant.pkg`

## Tests

Linux-safe static and policy tests:

```bash
tests/run-linux-tests.sh
```

On a macOS CI runner, run the Swift policy tests before signing:

```bash
swift test
```

After release:

```bash
codesign --verify --deep --strict --all-architectures \
  'build/release/Sinbar Support Assistant.app'
pkgutil --check-signature dist/Sinbar-Support-Assistant.pkg
spctl --assess --type install --verbose=4 dist/Sinbar-Support-Assistant.pkg
xcrun stapler validate dist/Sinbar-Support-Assistant.pkg
```

Complete acceptance testing must use clean Intel and Apple Silicon Macs. Validate first
install, returning deep-link launch, expired/replayed token rejection, offline failure,
tampered manifest rejection, tampered DMG rejection, wrong publisher rejection, rollback,
RustDesk launch, and the genuine Apple Screen Recording/Accessibility prompts.

## Current release blockers

1. Sinbar must obtain/configure Apple Developer ID Application and Installer identities.
2. The exact official RustDesk 1.4.9 Intel and Apple Silicon DMGs must be mirrored.
3. Both DMG SHA-256 values and the real RustDesk Team ID must be independently verified.
   This repository intentionally does not invent them.
4. The server's production P-256 manifest public key and key ID must be supplied.
5. The server issue/consume endpoints and one-time-token store must be deployed.
6. Signing, notarization, stapling, and clean-Mac tests require a macOS/Xcode runner.
