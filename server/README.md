# Sinbar Support Session API v2

This service is the narrow, server-side control plane for Sinbar's Intel-style
support launch experience. It does **not** remotely execute software in a web
browser. The signed Sinbar Support Assistant installed on the customer device
consumes a 120-second, one-use session and performs the allowlisted local action.

## Security contract

- `POST /api/v1/support/sessions` accepts exactly `platform` and `architecture`.
  It returns `protocolUrl`, `expiresAt`, and the platform installer fallback.
- The protocol URL is exactly
  `sinbarsupport://start?token=<43-character-base64url-token>`.
- `POST /api/v1/support/sessions/consume` accepts exactly `token`, `platform`,
  `architecture`, and `assistantVersion`.
- A token is 32 random bytes, exists for exactly 120 seconds, is bound to one
  platform and, when known, one architecture, and is atomically consumed once.
  The portal may issue `unknown`; the signed local assistant then supplies its
  exact `x86_64` or `arm64` architecture during consume.
- Only an HMAC-SHA-256 digest is stored. The bearer token, raw client IP, request
  body, and user-agent are never placed in application audit logs.
- The only action is `ensure-and-launch-rustdesk`; `attended` is always `true`.
  There is no command, script, password, hostname, or arbitrary argument field.
- Artifact URLs must use HTTPS, must have no query/fragment/user-info, and must
  use exactly `support.sinbarconsultants.com` on port 443/default.
- The server is single-worker by design so SQLite is the sole state authority.
  Atomic `BEGIN IMMEDIATE` transactions enforce single-use behavior.

## API examples

Create a session from the same-origin portal:

```http
POST /api/v1/support/sessions
Content-Type: application/json
Origin: https://support.sinbarconsultants.com

{"platform":"windows","architecture":"unknown"}
```

```json
{
  "protocolUrl": "sinbarsupport://start?token=<opaque-base64url>",
  "expiresAt": "2026-08-31T12:02:00Z",
  "installerUrl": "/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe"
}
```

The local assistant consumes it:

```http
POST /api/v1/support/sessions/consume
Content-Type: application/json

{"token":"<opaque-base64url>","platform":"windows","architecture":"x86_64","assistantVersion":"2.0.0"}
```

## Signed envelope (normative)

The response has exactly `keyId`, `payload`, and `signature`:

```json
{"keyId":"sinbar-support-manifest-p256-v1","payload":"<base64url>","signature":"<base64url>"}
```

Verification is deliberately portable to Windows CNG/.NET and macOS Security:

1. The assistant must have an expected `keyId` and its public key compiled into
   the signed application. Never download the trust key alongside the manifest.
2. Decode `payload` as unpadded base64url to obtain the exact raw UTF-8 JSON
   bytes emitted by the server.
3. Decode `signature` as unpadded base64url. It must be exactly 64 bytes in
   IEEE-P1363 form: 32-byte big-endian `r` followed by 32-byte big-endian `s`.
4. Verify ECDSA P-256 with SHA-256 over the **raw payload bytes**. Verify before
   parsing JSON. The server currently emits compact, sorted-key JSON, but the
   client never reserializes it for verification.
5. The pinned public key is unpadded base64url of the 65-byte ANSI X9.63
   uncompressed point `04 || X || Y` (32 bytes each).
6. Only after verification, strictly validate the fixed schema, UUID-D
   `sessionId`, RFC3339 UTC timestamps, `action`, `attended`,
   platform/architecture, HTTPS host, version, and lowercase SHA-256. Windows
   must also enforce `kind=msi` and signer subject containment `PURSLANE`.
   macOS must enforce `kind=dmg`, bundle ID `com.carriez.rustdesk`, and the
   verified configured Team Identifier. Reject unknown fields and expired
   manifests.

Generate a private key outside the repository/image, then derive the pin:

```bash
./scripts/generate_signing_key.sh /etc/sinbar/secrets/support-manifest-p256.pem
python3 scripts/print_public_key_pin.py /etc/sinbar/secrets/support-manifest-p256.pem
chown 10001:10001 /etc/sinbar/secrets/support-manifest-p256.pem
chmod 0400 /etc/sinbar/secrets/support-manifest-p256.pem
```

Protect key rotation as a software release: ship a new assistant containing both
old and new public keys, rotate the server key, then remove the old key in a
later assistant release.

## Artifact configuration

Copy `config/artifacts.template.json` to `config/artifacts.json`. The root-owned
service environment records the SHA-256 values for the exact RustDesk 1.4.9
artifacts. The macOS Team Identifier deliberately remains a fail-closed
placeholder until it is extracted and verified from both approved DMGs on a
Mac. Re-download from the official release, verify every artifact again, and
mirror the exact bytes before starting the API.

The installer fallback locations are fixed by the API contract:

- `/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe`
- `/download/v2.0.0/macos/Sinbar-Support-Assistant.pkg`

The first visit still requires the customer to download and approve the signed
assistant. Later visits use `sinbarsupport://` to launch it directly. If the
assistant is absent, the portal waits briefly and then presents the appropriate
installer URL. A newly installed assistant needs a fresh session because the
original token may have reached its 120-second limit.

## Build and deployment gates

The provided Dockerfile intentionally fails closed until its Python base-image
placeholder is replaced with a reviewed current immutable digest. A generated
hash-locked dependency file is already included; review it with the image pin.

Then, from the existing support-portal Compose project (whose default network is
`support-portal_default`):

```bash
cp guardian.env.example /etc/sinbar/support-session-api.env
chmod 0600 /etc/sinbar/support-session-api.env
cp config/artifacts.template.json config/artifacts.json
install -d -o 10001 -g 10001 -m 0700 data
docker compose -p support-portal -f compose.yaml -f compose.support-api.yaml config --quiet
docker compose -p support-portal -f compose.yaml -f compose.support-api.yaml up -d --build support-session-api
```

Merge the two `limit_req_zone` directives into Nginx's `http{}` context and the
three locations into the support virtual host. Keep the API unpublished on the
existing support-portal Docker network; expose only the same-origin Nginx
routes. Configure the exact proxy CIDR in `TRUSTED_PROXY_CIDRS`. Do not broadly
trust private address space.

The app has its own persistent rate limiter; Nginx is the first layer. Gunicorn
access logging is disabled, and the consume location disables Nginx access logs,
so bearer tokens in JSON bodies are never logged. Also confirm that CDN/WAF
request-body logging is disabled for the consume route.

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```

Tests cover the exact API contract, CORS/origin rejection, fixed target schema,
hash-at-rest, ECDSA P-256/P1363 verification, platform binding, replay rejection,
and concurrent atomic consume.

## Production blockers

- Signed Windows EXE and notarized/stapled macOS PKG do not yet exist at the
  fixed fallback paths.
- The four exact RustDesk artifacts must be re-verified and staged on the
  support host; the exact RustDesk Apple Team Identifier must be proven from
  both approved DMGs.
- The production P-256 private key and public-key pin must be generated and
  handled through the signing/agent release process.
- A reviewed immutable Python image digest is required before the image will
  build. The generated hashed Python dependency lock is included and must be
  refreshed through the same review process when dependencies change.
- The existing portal Nginx topology must be merged with the supplied private
  upstream locations and tested through Cloudflare before deployment.
