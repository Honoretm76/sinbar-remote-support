# Sinbar Support Assistant 2.0 deployment

This release produces an Intel-style **local assistant** experience. A browser
cannot execute server-side software on a customer's Windows PC or Mac. First
use downloads one signed assistant and requires the normal UAC or Gatekeeper
approval. Later clicks open the already-installed assistant through
`sinbarsupport://`; no ZIP extraction is involved.

## Production prerequisites

1. Build and verify `sinbar/support-session-api` from `server/`, publish it to
   the approved registry, and record its immutable `repository@sha256:digest`.
   Deployment never builds from the placeholder Dockerfile and never runs a
   mutable tag.
2. Generate the P-256 signing key outside the repository. Compile its exact
   key ID and 87-character X9.63 public pin into both assistants before they are
   signed. Install the private key at
   `/etc/sinbar/secrets/support-manifest-p256.pem`, owner API uid `10001`, mode
   `0400`.
3. Produce the Windows Authenticode-signed/timestamped EXE and macOS Developer
   ID-signed/notarized/stapled PKG. Native verification is never bypassed.
4. Verify the RustDesk Apple Team ID on both approved DMGs. Keep support
   attended-only; do not configure a permanent password.
5. Install `osslsigncode`, Docker Compose v2, OpenSSL, Python 3, and curl on the
   NOC host.

## Input layout

```text
/srv/sinbar-support/release-v2.0.0/
  Sinbar-Support-Assistant-Setup.exe
  Sinbar-Support-Assistant.pkg
  release-manifest.json
  SHA256SUMS.txt
  windows-native-verification.json
  macos-native-verification.json
  attended-acceptance.json

/srv/sinbar-support/rustdesk-1.4.9/
  windows/rustdesk-1.4.9-x86_64.msi
  windows/rustdesk-1.4.9-aarch64.msi
  macos/rustdesk-1.4.9-x86_64.dmg
  macos/rustdesk-1.4.9-aarch64.dmg
```

Generate the receipts on the native platforms:

```powershell
.\deploy\verify-windows-release.ps1 `
  -Installer .\Sinbar-Support-Assistant-Setup.exe `
  -SignerCertificateSha256 '<64 lowercase hex>' `
  -SignerSubject 'Sinbar Consultants LLC' `
  -Output .\windows-native-verification.json
```

```bash
./deploy/verify-macos-release.sh \
  ./Sinbar-Support-Assistant.pkg \
  YOUR10CHARTEAMID \
  'Developer ID Installer: Sinbar Consultants LLC' \
  ./macos-native-verification.json
```

Create `attended-acceptance.json` from the provided example only after two
reviewers test both clean devices and devices with a pre-existing RustDesk
service/permanent-password configuration. Every enforced boolean must be true;
the deployment hard-stops if unattended state cannot be removed or if the
assistant does not abort safely when remediation cannot be proven.

## Configure, check, deploy

Copy `deploy/production.env.example` to
`/etc/sinbar/support-deployment.env`; replace every placeholder and set mode
`0600`. Configure `/etc/sinbar/support-session-api.env` from the server example,
using independent random HMAC keys and the portal's exact private `/32` as
`TRUSTED_PROXY_CIDRS`. Confirm the Cloudflared container's exact address:

```bash
sudo docker inspect sinbar-noc-cloudflared \
  --format '{{range .NetworkSettings.Networks}}{{println .NetworkID .IPAddress}}{{end}}'
```

Then run:

```bash
sudo ./deploy/sinbar-support-deploy preflight \
  --release-dir /srv/sinbar-support/release-v2.0.0 \
  --rustdesk-dir /srv/sinbar-support/rustdesk-1.4.9

sudo ./deploy/sinbar-support-deploy deploy \
  --release-dir /srv/sinbar-support/release-v2.0.0 \
  --rustdesk-dir /srv/sinbar-support/rustdesk-1.4.9

sudo ./deploy/sinbar-support-deploy status
```

The deployment backs up `site`, `nginx.conf`, `compose.yaml`, any previous
overlay, and the prior `current` pointer under
`/opt/sinbar/backups/support-portal/`. It validates checksums before every
rollback. Automatic rollback runs after any failed container health, local
download hash, session API, or public HTTPS test.

Manual recovery uses the exact backup path printed by deployment:

```bash
sudo ./deploy/sinbar-support-deploy rollback \
  --backup /opt/sinbar/backups/support-portal/TIMESTAMP-pre-v2.0.0
```

Never hand-edit the deployed manifest, weaken SmartScreen/UAC/Gatekeeper/TCC,
accept a mutable image tag, broadly trust RFC1918 proxy ranges, or publish an
installer without the matching native verification receipt.

Production also requires a clean reviewed Git checkout: the current `HEAD`,
`REVIEWED_SOURCE_COMMIT`, post-signing release manifest, attended-acceptance
receipt, and API image OCI revision label must all be the same 40-character
commit. The immutable API image must also carry
`org.opencontainers.image.version=2.0.0`. A source ZIP is suitable for review,
but deliberately cannot pass production deployment preflight.
