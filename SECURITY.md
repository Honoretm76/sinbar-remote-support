# Security policy

## Supported release

Only a production release that passes the signing gates in `release/` may be
published. Source builds and unsigned artifacts are for development only.

## Required production controls

- Windows executables and installers are Authenticode signed and timestamped.
- The macOS app, helper, and package are signed with the appropriate Developer
  ID identities, notarized, stapled, and accepted by Gatekeeper.
- The manifest signing private key is generated outside the repository and is
  readable only by the session API service account.
- The corresponding P-256 public key and key ID are compiled into both clients.
- RustDesk artifacts are mirrored only after SHA-256 and native publisher
  verification. Clients repeat those checks before installation.
- Session tokens expire in 120 seconds, are stored only as hashes, and are
  atomically invalidated on first consumption.
- Public API and download routes are rate-limited at the reverse proxy.
- Audit logs exclude raw launch tokens, RustDesk passwords, signing material,
  full client IP addresses, and arbitrary request bodies.

## Attended-support release invariants

- The Sinbar workflow creates or distributes no permanent RustDesk password.
- Production publication remains blocked until pre-existing RustDesk service,
  stored-password, and unattended configuration are rejected or remediated and
  covered by clean and preconfigured-host tests.
- A launch never grants a technician control by itself.
- The customer sees RustDesk and can disconnect.
- macOS privacy permissions remain under customer or approved MDM control.
- The assistants expose no shell, script, command, path, environment, or
  argument execution interface.

## Key rotation

Manifest keys use explicit key IDs. Deploy a client release containing both
the current and next public keys before the server begins signing with the new
private key. Retire the old server key only after the supported client window
has elapsed.

## Incident response

If a signing key or release channel may be compromised:

1. Disable `/api/v1/support/sessions` at the reverse proxy.
2. Remove the affected assistant installers and manifest signing key.
3. Preserve API, proxy, release, and code-signing audit records.
4. Revoke the affected platform certificate or server key.
5. Publish a new, independently reviewed client and key set.
6. Re-enable session creation only after clean-device validation.

Report suspected security issues privately to
`support@sinbarconsultants.com`; do not include customer passwords or active
session tokens.
