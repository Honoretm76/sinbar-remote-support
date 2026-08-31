# Sinbar Support Assistant 2.0 architecture

## Purpose

Sinbar Support Assistant gives `https://support.sinbarconsultants.com` an
Intel-style launch experience without weakening Windows or macOS security.
The NOC server coordinates each launch, while all installation and execution
still occurs locally on the customer's computer.

## Customer flow

### First visit

1. The customer selects **Start Remote Support**.
2. The portal requests a 120-second, one-use launch token.
3. The browser attempts `sinbarsupport://start?token=...`.
4. If the assistant is not installed, the portal offers exactly one signed
   Windows installer or one signed/notarized macOS installer.
5. The customer opens it and approves the operating-system elevation prompt,
   then returns to the portal and selects **Start Remote Support** again.
6. The installed assistant consumes the new launch token and verifies a signed
   fixed-action manifest.
7. A native, fail-safe customer confirmation names the verified support action.
   Cancel performs no elevation, helper request, installation, or launch.
8. After explicit approval, the assistant installs or updates the reviewed
   RustDesk build, opens it for the attended-support workflow, removes temporary
   files, and closes.

### Returning visit

The same button launches the installed assistant through the
`sinbarsupport://` protocol. The signed request is shown for native customer
confirmation before RustDesk opens. No ZIP extraction or Start script is
involved.

## Trust boundaries

- The portal is an untrusted wake-up surface. A URL does not authorize an
  installation by itself.
- Launch tokens are opaque random values, stored as hashes, expire after 120
  seconds, and are atomically consumed once.
- The assistant pins `https://support.sinbarconsultants.com` and accepts no
  alternate origin from the browser or server response.
- The only accepted action is `ensure-and-launch-rustdesk` with
  `attended: true`.
- The manifest is signed with ECDSA P-256/SHA-256. The private signing key
  remains on the NOC server; assistants contain only the public key.
- The assistant verifies the release SHA-256 and native publisher signature
  before elevation or installation.
- The Sinbar workflow accepts no permanent RustDesk password, shell command,
  executable path, environment variable, or arbitrary argument from the
  network. Production remains blocked until pre-existing unattended/password
  state passes the reviewed preconfigured-host policy.
- Windows UAC, macOS Gatekeeper, Screen Recording, and Accessibility approval
  are never bypassed.

## API contract

### Issue a launch

`POST /api/v1/support/sessions`

```json
{"platform":"windows","architecture":"unknown"}
```

Successful response:

```json
{
  "protocolUrl": "sinbarsupport://start?token=<base64url>",
  "expiresAt": "2026-08-31T12:02:00Z",
  "installerUrl": "/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe"
}
```

### Consume a launch

`POST /api/v1/support/sessions/consume`

```json
{
  "token": "<base64url>",
  "platform": "windows",
  "architecture": "x86_64",
  "assistantVersion": "2.0.0"
}
```

The successful response is an envelope:

```json
{
  "keyId": "sinbar-support-manifest-p256-v1",
  "payload": "<base64url UTF-8 JSON>",
  "signature": "<base64url 64-byte IEEE-P1363 ECDSA signature>"
}
```

The signature covers the decoded `payload` bytes. The assistant verifies the
signature before parsing the JSON. The pinned public key is the 65-byte
uncompressed ANSI X9.63 point (`04 || X || Y`).

The signed payload has a closed schema:

```json
{
  "schemaVersion": 1,
  "sessionId": "<uuid>",
  "action": "ensure-and-launch-rustdesk",
  "attended": true,
  "platform": "windows",
  "architecture": "x86_64",
  "issuedAt": "2026-08-31T12:00:00Z",
  "expiresAt": "2026-08-31T12:02:00Z",
  "artifact": {
    "kind": "msi",
    "url": "https://support.sinbarconsultants.com/download/vendor/rustdesk/1.4.9/windows/rustdesk-1.4.9-x86_64.msi",
    "sha256": "c87d2f4cef2a5acd6003b6507dcfbf5d5168a256db082cd90b54d35193224aaa",
    "version": "1.4.9",
    "publisherSubjectContains": "PURSLANE"
  }
}
```

macOS uses `kind: dmg`, bundle identifier `com.carriez.rustdesk`, and a
production-pinned Apple Team ID verified from the approved RustDesk release.

## Components

- `portal/` — black, gold, and white customer launch interface.
- `server/` — same-origin session API and signed release manifests.
- `windows/` — Windows assistant and signed installer project.
- `macos/` — macOS assistant and signed/notarized installer project.
- `release/` — production build, signing, notarization, and release checks.
- `deploy/` — NOC staging, validation, deployment, and rollback tooling.

## Explicit non-goals

- Browser-only silent software installation.
- Unattended remote-control authorization.
- Permanent passwords.
- Generic remote execution.
- Disabling SmartScreen, UAC, Gatekeeper, quarantine, SIP, or TCC.
