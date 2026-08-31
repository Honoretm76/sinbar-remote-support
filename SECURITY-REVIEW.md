# Security review disposition

The 2.0.0 source tree received an adversarial cross-component review after the
portable test suite passed. This file records the disposition; it is not a
substitute for native Windows and macOS release testing.

## Closed in source

- A valid signed manifest is verified before either assistant presents native
  customer consent. Consent defaults to **No** and cancellation performs no
  elevation, installation, helper request, or RustDesk launch.
- The Windows elevated continuation repeats consent, re-verifies the signed
  envelope, rechecks expiration immediately before execution, and cannot turn
  a captured envelope into a consent-free privileged action.
- Windows vendor artifacts are held in protected administrator/SYSTEM-only
  staging and are rechecked by SHA-256, Authenticode, publisher subject, and
  exact signer-SPKI pin before `msiexec`.
- The macOS helper authenticates its signed caller, uses root-owned no-follow
  staging, independently re-verifies the signed manifest and vendor identity,
  and performs an atomic, rollback-capable application replacement.
- The alternate Nginx route snippet now overwrites untrusted forwarding input.
  The canonical deployment verifies the exact Cloudflared container, network,
  and current IPv4 `/32` before trusting `CF-Connecting-IP`.
- Production preflight binds the clean Git revision, release manifest commit,
  API image revision/version labels, installer hashes, trust pins, native
  verification receipts, and attended-support acceptance receipt.

## Intentional production stop

The assistants create and transmit no permanent RustDesk password. They do not
yet themselves prove that a pre-existing RustDesk service, stored password, or
unattended configuration was removed or rejected. Production preflight
therefore requires two-reviewer clean-device and preconfigured-host acceptance
evidence, including abort-on-remediation-failure tests, before staging is
allowed.

No signed Windows installer, notarized macOS package, production manifest key,
or vendor-identity pin is included in this source bundle. Missing or placeholder
values fail closed.

## Native release tests still required

- Compile and test Windows x64 and ARM64 on clean Windows 10/11 hosts.
- Verify both RustDesk MSIs have the recorded hashes, valid Authenticode chains,
  and the same reviewed signer-SPKI pin.
- Compile and test Intel and Apple-silicon macOS builds with Xcode.
- Verify both RustDesk DMGs have the recorded hashes, valid nested signatures,
  Gatekeeper acceptance, and the same reviewed bundle and Team identifiers.
- Authenticode-sign/timestamp the Sinbar EXE; Developer-ID sign, notarize, and
  staple the Sinbar PKG; then run the guarded deployment and rollback drill.
