# Sinbar Remote Support — vendor-signed portable release

Version `2.1.0` is the no-cost production path for
<https://support.sinbarconsultants.com/>.

It removes the unavailable custom Sinbar EXE/PKG signing requirement. The portal
publishes byte-for-byte official RustDesk 1.4.9 artifacts and never changes
their executable contents.

## Customer experience

| Platform | Customer flow |
|---|---|
| Windows | Select **Start Remote Support**, open the downloaded PURSLANE-signed portable EXE, approve Windows, and give the one-time RustDesk ID/password to the Sinbar technician. The download filename supplies the approved Sinbar host and public key without changing the signed EXE. |
| macOS | Select the correct Apple silicon or Intel DMG, install the unchanged official RustDesk app, copy/import the Sinbar server configuration, and approve Apple's Screen Recording and Accessibility permissions. |

A website cannot execute an EXE or DMG directly. The customer must open the
download and approve the operating-system security prompt.

## Fixed upstream release

- RustDesk version: `1.4.9`
- Release: <https://github.com/rustdesk/rustdesk/releases/tag/1.4.9>
- License: AGPL-3.0
- Windows publisher: `PURSLANE`
- Windows publisher SPKI SHA-256:
  `85a1152301ba31d625ce06294584deaee9cf32c2dd7bdfdf72821499cd745116`

Exact artifact hashes and routes are recorded in
`portal/download/manifest.json` and enforced by GitHub Actions.

## Safety properties

- No Sinbar-built executable is published.
- No upstream executable or app bundle is modified or re-signed.
- No permanent RustDesk password is created or embedded.
- The browser makes no support-session API call and registers no custom protocol.
- Windows configuration is an encoded public server configuration in the
  download filename; it contains no credential or private key.
- macOS configuration is copied only after a customer action.
- The portal retains Sinbar's black, gold, white, and logo presentation while
  honestly identifying RustDesk/PURSLANE as the software publisher.

## Validate

Run `python3 portal/tests/validate_portal.py`.

GitHub Actions independently re-downloads both Windows EXEs and both macOS
DMGs, enforces their SHA-256 values, verifies Windows Authenticode and the
publisher key pin, and verifies Apple Developer ID/Gatekeeper acceptance.

Legacy custom-assistant source remains in repository history only. It is not
part of this release or customer flow.

