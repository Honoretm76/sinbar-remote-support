# Production readiness checklist

## Completed in this source release

- [x] One-button responsive Sinbar portal; no ZIP extraction workflow.
- [x] Exact one-use session issue/consume API.
- [x] Fixed signed-manifest schema and P-256/P1363 interoperability contract.
- [x] Windows assistant source, custom protocol, verified elevation boundary,
      RustDesk hash/native-signature checks, silent MSI install, and attended launch.
- [x] macOS universal assistant source, privileged XPC helper, strict caller
      identity, root-owned staging, Gatekeeper/code-signature checks, atomic install,
      signed PKG and notarization pipeline.
- [x] Exact NOC download/API routes and private API network design.
- [x] Portable portal, API, Windows, macOS, release, and integration tests.
- [x] The Sinbar workflow creates or sends no permanent password and exposes no
      arbitrary command channel or browser security bypass.

## Required before production publication

- [ ] Generate and protect the production P-256 manifest private key.
- [ ] Compile the derived public point and canonical key ID into both assistants.
- [ ] Supply the reviewed immutable Python image digest.
- [ ] Re-download all four official RustDesk 1.4.9 artifacts and re-check the
      recorded SHA-256 values.
- [ ] Verify Windows RustDesk native signature and the exact configured signer pin.
- [ ] Verify the exact RustDesk Apple Team ID from both DMGs on macOS.
- [ ] Build and timestamp the Windows assistant with Sinbar Authenticode.
- [ ] Build, Developer-ID sign, notarize, and staple the macOS package.
- [ ] Run native Windows contract/build/install tests on clean Windows 10/11
      x64 and ARM64 VMs.
- [ ] Run native macOS tests on clean Intel and Apple-silicon VMs, including TCC guidance.
- [ ] Stage artifacts on NOC and run deployment preflight.
- [ ] Back up the current live portal and perform the guarded deployment.
- [ ] Verify local API/downloads, then Cloudflare/public behavior.
- [ ] Verify first-visit and returning-visit flows on every supported platform.
- [ ] Prove on preconfigured hosts that existing RustDesk unattended service,
      stored permanent password, and unattended settings are rejected or
      deterministically remediated before launch.
- [ ] Test rollback to the current v1.1.2 portal.

## Go/no-go rule

Production is **NO-GO** while any item above is incomplete. A portal page alone
must never be deployed before the signed installers and mirrored, verified
RustDesk artifacts exist at their fixed paths.
