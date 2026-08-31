# Sinbar Remote Support — Intel-style experience

Version 2.0.0 replaces the ZIP-and-script workflow with one customer action:
**Start Remote Support**.

The NOC server creates a 120-second, one-use authorization. If the signed
Sinbar Support Assistant is already installed, the browser opens it through the
registered `sinbarsupport://` protocol. On a first visit, the same page offers
the correct signed installer, then the customer returns and selects the button
again. The assistant verifies a signed fixed-action manifest, ensures the exact
approved RustDesk 1.4.9 build is installed, opens it for attended support, and
closes its own status window.

## What customers experience

| Visit | Customer action | Result |
|---|---|---|
| First | Select **Start Remote Support**, install the signed assistant, approve the OS prompt, then select the button again and confirm the signed request | RustDesk is verified, silently installed where the OS permits, and opened |
| Returning | Select **Start Remote Support**, approve the browser's “Open Sinbar Support” prompt, then confirm the signed request | The installed assistant opens RustDesk directly |

The browser cannot execute Windows or macOS software “from the server.” Modern
browsers intentionally require a local, signed application and explicit OS
approval. This design provides the same safe pattern used by driver-detection
sites: install a small trusted local assistant once, then let the website wake
that assistant on later visits.

## Safety properties

- The Sinbar workflow creates or sends no permanent RustDesk password. A
  production release must additionally reject or remediate pre-existing
  unattended/password state before it may claim attended-only enforcement.
- Exact 43-character random launch token; hashed at rest, 120-second expiry,
  bound to platform/architecture, and atomically usable once.
- No command, script, path, password, hostname, or generic argument can be sent
  by the portal or API.
- ECDSA P-256/SHA-256 signed fixed-action manifest, verified before elevation.
- Native customer consent after signature verification; cancellation performs
  no elevation, installation, helper request, or RustDesk launch.
- Exact HTTPS origin, artifact path, version, SHA-256, and native publisher
  identity pins in both assistants.
- Windows displays UAC only after token consumption and manifest verification.
- macOS uses a signed privileged XPC helper and preserves Gatekeeper, Screen
  Recording, Accessibility, SIP, and TCC controls.
- API logs exclude tokens, raw request bodies, and full client IP addresses.

See [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md), and
[SECURITY-REVIEW.md](SECURITY-REVIEW.md) for the normative contract, review
disposition, production stops, and incident-response policy.

## Source layout

- `portal/` — responsive black, gold, and white customer interface.
- `server/` — one-use session API and signed manifest service.
- `windows/` — .NET 8 assistant and Authenticode/Inno Setup release project.
- `macos/` — Swift assistant, signed XPC helper, PKG and notarization project.
- `release/` — vendor verification and signed release pipelines.
- `deploy/` — NOC preflight, backup, deployment, validation, and rollback.
- `tests/` — portable cross-component contract suite.

## Portable validation

From this directory:

```bash
bash tests/run-all.sh
```

This validates the static portal, both platform security contracts, release
paths and versions, Nginx/Compose alignment, and API tests. Windows
Authenticode/Inno compilation must additionally run on a Windows signing host;
Apple signing/notarization and Swift/AppKit tests must run on macOS.

## Production release gates

This source package intentionally cannot be deployed as a trusted production
release until all of these public/trust inputs are supplied and verified:

1. A Sinbar Windows Authenticode certificate/private key and timestamp service.
2. Sinbar Apple Developer ID Application and Installer identities plus an Apple
   notary profile.
3. A production manifest P-256 key generated outside the repository, with its
   public point compiled into both signed assistants.
4. The exact RustDesk macOS Team Identifier verified from both official 1.4.9
   DMGs; the build refuses placeholders.
5. All four official RustDesk 1.4.9 artifacts re-downloaded, native signatures
   checked, SHA-256 values matched, and mirrored byte-for-byte on the NOC host.
6. The session API's Python base image replaced with a reviewed immutable
   digest.
7. NOC deployment preflight, local smoke tests, Cloudflare/public tests, and a
   clean rollback drill.
8. A reviewed, tested policy that rejects or remediates any pre-existing
   RustDesk service, stored permanent password, or unattended configuration.

Unsigned, ad-hoc-signed, unnotarized, placeholder, or identity-mismatched
artifacts must never be published to customers.

## Vendor release

The approved artifact names and architectures correspond to RustDesk's official
1.4.9 release page:
<https://github.com/rustdesk/rustdesk/releases/tag/1.4.9>.

RustDesk's official deployment guidance also confirms that local client
installation requires an administrator/root-capable deployment method:
<https://rustdesk.com/docs/en/self-host/client-deployment/>.
