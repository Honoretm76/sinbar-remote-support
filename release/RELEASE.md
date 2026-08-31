# Sinbar Support Assistant release and signing runbook

This directory contains the production release pipeline for the real Windows and
macOS assistant sources in the sibling `windows/` and `macos/` directories. It
does **not** contain, generate, or substitute placeholder binaries.

The production outputs are exactly:

- `Sinbar-Support-Assistant-Setup.exe` — Windows x64/ARM64 Inno Setup bundle,
  Authenticode signed and RFC 3161 timestamped.
- `Sinbar-Support-Assistant.pkg` — universal macOS package, Developer ID signed,
  Apple-notarized, and stapled.
- `release-manifest.json` — sizes and SHA-256 digests generated only after both
  platform trust processes finish.
- `SHA256SUMS.txt` — SHA-256 verification list for both installers and the JSON
  manifest.

## Install the workflow

GitHub only discovers workflows at the repository-root `.github/workflows/`
path. This copy is deliberately stored under `release/` so this work remains
isolated. After review, install it without modifying its contents:

```bash
install -D -m 0644 \
  release/.github/workflows/sinbar-support-release.yml \
  .github/workflows/sinbar-support-release.yml
```

Protect changes to `.github/workflows/**`, `release/**`, `windows/**`, and
`macos/**` with CODEOWNERS and required reviews. Do not enable
`pull_request_target` for this workflow.

## GitHub environments

Create these environments with required reviewers, prevent self-approval, and
restrict deployment branches/tags as shown:

| Environment | Allowed ref | Purpose |
|---|---|---|
| `windows-signing` | protected `v*` tags | Access to Authenticode private key |
| `macos-signing` | protected `v*` tags | Access to Developer ID and notary credentials |
| `production-release` | protected `v*` tags | Final GitHub Release publication approval |

The signing jobs never run on pull requests or ordinary branch builds. A `v*`
tag build fails if a required secret, public trust pin, signature, timestamp,
notarization result, staple, or expected artifact is absent.

## Exact GitHub secret names

### `windows-signing` environment secrets

| Secret | Required value |
|---|---|
| `WINDOWS_SIGNING_PFX_BASE64` | Base64 of the Authenticode PFX bytes |
| `WINDOWS_SIGNING_PFX_PASSWORD` | PFX import password |

The PFX must contain the private key for the certificate identified by
`WINDOWS_CERT_THUMBPRINT`. The workflow imports it only into the ephemeral
runner's current-user certificate store and removes it in a `finally` block.
If the CA does not permit an exportable PFX, replace this import stage with an
approved HSM/cloud signing action; do not export or weaken the key.

### `macos-signing` environment secrets

| Secret | Required value |
|---|---|
| `APPLE_APPLICATION_P12_BASE64` | Base64 of the Developer ID Application P12 |
| `APPLE_APPLICATION_P12_PASSWORD` | Application P12 import password |
| `APPLE_INSTALLER_P12_BASE64` | Base64 of the Developer ID Installer P12 |
| `APPLE_INSTALLER_P12_PASSWORD` | Installer P12 import password |
| `APPLE_NOTARY_KEY_P8_BASE64` | Base64 of the App Store Connect API `.p8` key |
| `APPLE_NOTARY_KEY_ID` | App Store Connect API key ID |
| `APPLE_NOTARY_ISSUER_ID` | App Store Connect API issuer UUID |

The workflow creates a random temporary keychain, imports only these two
identities, validates the API credentials, and deletes the keychain, P12 files,
and P8 file on every exit path. Use the least-privileged App Store Connect API
key that can submit notarization requests.

Never store any PFX, P12, P8, password, private manifest signing key, or bearer
token in repository files, workflow variables, artifacts, logs, or release
notes. Do not enable shell tracing (`set -x`) or PowerShell transcript logging
in signing jobs.

## Exact GitHub repository variable names

These values are public trust/configuration pins, not private keys:

| Variable | Format |
|---|---|
| `WINDOWS_CERT_THUMBPRINT` | 40 hexadecimal characters, no spaces |
| `WINDOWS_TIMESTAMP_URL` | Authenticode RFC 3161 HTTPS timestamp URL |
| `MANIFEST_KEY_ID` | Must be exactly `sinbar-support-manifest-p256-v1` |
| `MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL` | 87-character unpadded base64url encoding of a 65-byte P-256 X9.63 public point |
| `RUSTDESK_WINDOWS_PUBLISHER_SPKI_SHA256` | Verified 64-hex SHA-256 of the native RustDesk Authenticode leaf certificate's SubjectPublicKeyInfo; both approved MSIs must match |
| `APPLE_DEVELOPER_ID_APPLICATION` | Full identity, e.g. `Developer ID Application: Sinbar Consultants LLC (TEAMID)` |
| `APPLE_DEVELOPER_ID_INSTALLER` | Full identity, e.g. `Developer ID Installer: Sinbar Consultants LLC (TEAMID)` |
| `APPLE_TEAM_ID` | Ten-character Apple Developer Team ID |
| `RUSTDESK_BUNDLE_IDENTIFIER` | Must be the independently verified protocol pin `com.carriez.rustdesk` |
| `RUSTDESK_TEAM_IDENTIFIER` | Verified ten-character RustDesk Apple Team ID |
| `RUSTDESK_X86_64_DMG_SHA256` | 64 lowercase hexadecimal characters |
| `RUSTDESK_ARM64_DMG_SHA256` | 64 lowercase hexadecimal characters |

The manifest **public** key is embedded in both assistants. Its private key
belongs only in the server-side manifest signer and is not used by this release
workflow.

## RustDesk 1.4.9 vendor acceptance and mirroring

Do not approve a vendor artifact from its filename or SHA-256 alone. Download
each exact upstream RustDesk 1.4.9 artifact through an independently reviewed
release URL, validate its native platform signature, record the publisher-key
identity, and then mirror those unchanged bytes. The four expected byte hashes
are:

| Platform | Architecture | Portal mirror name | SHA-256 |
|---|---|---|---|
| Windows | x86_64 | `rustdesk-1.4.9-x86_64.msi` | `c87d2f4cef2a5acd6003b6507dcfbf5d5168a256db082cd90b54d35193224aaa` |
| Windows | ARM64 | `rustdesk-1.4.9-aarch64.msi` | `30bc8925e62c7ade52371758c2b944036ed2386f6c554e9e59f3bcfef06c7cd9` |
| macOS | x86_64 | `rustdesk-1.4.9-x86_64.dmg` | `fa1129a0635019f9c5841937942cc2b08be028a192f47c009edde7e53812904e` |
| macOS | ARM64 | `rustdesk-1.4.9-aarch64.dmg` | `f7935597b247d42c8f2a2ed71176a9f5868018cd9e1a33b8096418a668c8caf0` |

On a clean Windows validation machine, run `signtool verify /pa /all /v` on
both MSIs and require a valid native Authenticode chain. Inspect both leaf
certificates with `Get-AuthenticodeSignature`; the reviewed client policy also
requires the expected publisher subject containing `PURSLANE`. Derive the SPKI
pin from the actual signing certificate rather than its display name:

```powershell
$signature = Get-AuthenticodeSignature .\rustdesk-1.4.9-x86_64.msi
if ($signature.Status -ne 'Valid') { throw 'RustDesk signature is not valid' }
$spki = $signature.SignerCertificate.PublicKey.ExportSubjectPublicKeyInfo()
$pin = [Convert]::ToHexString(
  [Security.Cryptography.SHA256]::HashData($spki)
).ToLowerInvariant()
$pin
```

Repeat this for ARM64. Both pins must be identical and must become
`RUSTDESK_WINDOWS_PUBLISHER_SPKI_SHA256`. A signer mismatch is a release stop,
even when both file hashes match their recorded values.

On a clean Mac, mount each DMG read-only. For the one `RustDesk.app` in each,
run `codesign --verify --deep --strict --all-architectures`, inspect
`codesign -dv --verbose=4`, and run `spctl --assess --type execute --verbose=4`.
Both architectures must have a valid native Apple signature and the same
reviewed `Identifier` and `TeamIdentifier`. Put those exact values in
`RUSTDESK_BUNDLE_IDENTIFIER` and `RUSTDESK_TEAM_IDENTIFIER`. A Team ID, bundle
ID, nested-code, Gatekeeper, or signature mismatch is a release stop.

After copying the four files into
`/download/vendor/rustdesk/1.4.9/{windows,macos}/`, hash the mirrored bytes
again and repeat the native signature checks against the mirrored copies. Never
repackage, re-sign, or transform an approved vendor artifact.

## Attended-only acceptance blocker

The reviewed assistants do not create or accept a RustDesk password, but the
release must not infer from that alone that a previously installed RustDesk is
attended-only. Before production publication, verify on both platforms that the
runtime either rejects an existing unattended/service/permanent-password
configuration or deterministically removes it under a separately reviewed,
testable policy. Until that behavior exists and is covered by clean and
preconfigured-host acceptance tests, "attended-only" is a production blocker,
not a release claim.

## One-time setup checklist

- [ ] Verify the Windows certificate subject, SHA-1 thumbprint, private-key
  availability, expiration, and code-signing EKU.
- [ ] Add both Windows environment secrets and all Windows/shared public trust variables, including the signer SPKI pin.
- [ ] Verify the Developer ID Application and Developer ID Installer identities
  are issued to the same `APPLE_TEAM_ID`.
- [ ] Add all seven macOS environment secrets.
- [ ] Add the Apple identity, Team ID, manifest, and RustDesk public variables.
- [ ] Set `MANIFEST_KEY_ID` to exactly `sinbar-support-manifest-p256-v1`.
- [ ] Confirm all four RustDesk hashes, both Windows native signatures and one
  common SPKI pin, and both macOS native signatures with one common Team ID and
  bundle identifier before mirroring unchanged bytes.
- [ ] Resolve and test the attended-only blocker on hosts with a pre-existing
  RustDesk service, stored permanent password, and unattended configuration.
- [ ] Protect `v*` tags; require reviewed source and workflow changes.
- [ ] Configure required reviewers on all three GitHub environments.
- [ ] Enable GitHub immutable releases for the repository.
- [ ] Install the reviewed workflow at the repository-root path.
- [ ] Run an ordinary `main`/pull-request validation build before creating a tag.

## Release checklist

1. Confirm every source version and portal path agrees:

   ```bash
   python3 release/scripts/validate_release_contract.py \
     --repository-root "$PWD" \
     --tag v2.0.0 \
     --manifest-key-id sinbar-support-manifest-p256-v1
   python3 tests/validate_integration.py
   ```

2. Review and merge through the protected branch. Create the release tag from
   that exact commit. For the current sources the only valid tag is `v2.0.0`.

3. Approve `windows-signing` only after the workflow commit and source commit
   match the reviewed tag. The Windows job:

   - imports the PFX into the ephemeral runner;
   - compiles self-contained x64 and ARM64 assistants;
   - signs each assistant executable, the Inno installer, and its uninstaller;
   - applies an RFC 3161 SHA-256 timestamp;
   - runs SignTool `/pa /all /tw` and checks the exact certificate thumbprint.

4. Approve `macos-signing` after the same review. The macOS job:

   - compiles universal app/helper binaries;
   - signs the helper and app inside-out with hardened runtime and timestamps;
   - signs the PKG with Developer ID Installer;
   - waits for Apple notarization;
   - staples and validates the ticket;
   - runs `spctl --type install` and checks the exact installer identity/Team ID.

5. Inspect the `release-bundle-v2.0.0` workflow artifact. Approve
   `production-release` only when it contains exactly the two installers,
   `release-manifest.json`, and `SHA256SUMS.txt`.

6. The publish job creates a draft, verifies the exact four uploaded asset
   names, and only then publishes it. It refuses to overwrite an existing
   release and never uses `--clobber`.

7. Verify the downloaded public files independently:

   ```powershell
   signtool verify /pa /all /tw /v .\Sinbar-Support-Assistant-Setup.exe
   Get-AuthenticodeSignature .\Sinbar-Support-Assistant-Setup.exe
   ```

   ```bash
   pkgutil --check-signature Sinbar-Support-Assistant.pkg
   xcrun stapler validate Sinbar-Support-Assistant.pkg
   spctl --assess --type install --verbose=4 Sinbar-Support-Assistant.pkg
   shasum -a 256 -c SHA256SUMS.txt
   ```

8. Only after those checks pass, deploy the exact release assets to the portal's
   fixed `/download/v2.0.0/{windows,macos}/` paths and update the portal's
   publication state through its reviewed deployment process.

The contract job also installs production and test dependencies only from
`server/requirements.lock` and `release/server-test-requirements.lock` with
`pip --require-hashes`, then runs the Support Session API test suite with
`PYTHONPATH=server`. Treat any lock drift or missing distribution hash as a hard
failure; do not fall back to `pip install` from an unhashed requirements file.

## Failure recovery

- A missing production secret or variable is a hard failure; configure it and
  rerun. Never insert fallback development identities or ad-hoc signatures.
- A signature, timestamp, notarization, stapling, Team ID, filename, or checksum
  mismatch is a hard stop. Rotate/reissue credentials or correct the reviewed
  source before retrying.
- If publication fails after draft creation, inspect and remove the incomplete
  draft manually before rerunning. The workflow intentionally will not overwrite
  it.
- GitHub Actions artifacts are staging copies, not the public distribution
  location. Only the verified GitHub Release assets may be deployed.
