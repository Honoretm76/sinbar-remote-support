# Sinbar Remote Support Portal 2.0

This directory contains the static Intel-style launch experience for the
Sinbar Support Assistant. It is deliberately separate from the v1.1.2 portal
and is not a production deployment.

## User flow

1. The visitor selects **Start Remote Support**.
2. The page detects Windows or macOS and requests a short-lived session from
   `POST /api/v1/support/sessions` with `{platform, architecture}`.
3. The response must contain a strictly validated
   `sinbarsupport://start?token=<base64url>` URL, expiration time, and the fixed
   installer path for that platform.
4. The page asks the browser to open the already-installed assistant.
5. If the browser remains visible, a first-visit dialog offers the signed
   Windows or macOS installer.

The browser never receives permission to execute server-side code on the
customer device. The assistant runs locally after the customer installs and
approves it once.

## API contract

Request:

```http
POST /api/v1/support/sessions
Accept: application/json
Content-Type: application/json
Cache-Control: no-store

{"platform":"windows","architecture":"x86_64"}
```

Supported platform values are `windows` and `macos`. Supported architecture
values are `x86_64`, `arm64`, and `unknown`; the API must safely select a
universal or platform-appropriate installer when architecture is unknown.

Successful response:

```json
{
  "protocolUrl": "sinbarsupport://start?token=<base64url>",
  "expiresAt": "2026-08-31T12:05:00Z",
  "installerUrl": "/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe"
}
```

Requirements:

- Tokens are cryptographically random, base64url, one-time use, and 32 to 512
  characters.
- Expiration must be in the future and no more than 15 minutes away.
- Responses and all intermediary layers must use `Cache-Control: no-store`.
- Never place a token in access logs, analytics, HTML, persistent storage, or
  the installer URL.
- Rate-limit session creation by trusted edge signals without blocking shared
  customer networks.
- Return JSON errors without reflecting request values.

## Production blockers

- Implement and deploy the same-origin session API.
- Publish the Windows assistant at the exact manifest path after Authenticode
  signing and signature verification.
- Publish the macOS assistant at the exact manifest path after Developer ID
  signing, notarization, stapling, and Gatekeeper verification.
- Register the `sinbarsupport` protocol in both installers and ensure the
  assistant consumes each token only once.
- Replace `support-launch-api:8080` in the Nginx snippet only if the production
  Compose service name differs.

## Validation

Run:

```bash
./tests/run.sh
```

The validator checks the logo digest, strict CSP-compatible asset layout,
fixed API/installer/protocol contracts, manifest alignment, and Nginx routes.
