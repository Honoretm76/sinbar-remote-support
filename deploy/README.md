# NOC production deployment tools

`sinbar-support-deploy` is the only supported production entry point. It does
not build, sign, notarize, weaken, or replace either operating system's trust
controls. It refuses unsigned/unstapled release evidence, placeholder trust
pins, mutable Docker tags, wrong RustDesk bytes, broad proxy trust, and a
manifest public key that does not match the NOC private key.

Commands:

```bash
sudo ./deploy/sinbar-support-deploy status
sudo ./deploy/sinbar-support-deploy preflight \
  --release-dir /srv/sinbar-support/release-v2.0.0 \
  --rustdesk-dir /srv/sinbar-support/rustdesk-1.4.9
sudo ./deploy/sinbar-support-deploy deploy \
  --release-dir /srv/sinbar-support/release-v2.0.0 \
  --rustdesk-dir /srv/sinbar-support/rustdesk-1.4.9
```

The preflight performs all validation, renders the existing Compose file plus
the overlay, and runs `nginx -t` in the exact currently deployed portal image.
It does not recreate a container. Deployment then creates a checksummed backup,
uses an atomic `current` symlink, starts the private API, recreates the portal,
and checks local and public paths. Any post-commit failure invokes rollback.

Native verification receipts are mandatory and hash-bound to the installers:

- Run `verify-windows-release.ps1` on a clean Windows signing verifier with
  PowerShell and SignTool.
- Run `verify-macos-release.sh` on a clean Mac with Apple command-line tools.
- Add `attended-acceptance.json` only after two reviewers complete clean-device
  and already-preconfigured Windows and macOS tests. The latter must prove that
  existing RustDesk services, stored permanent passwords, and unattended access
  are rejected or deterministically remediated, and that launch aborts if this
  cannot be proven. Preflight defaults to failure without that receipt; its
  exact schema is enforced by `preflight.py`.

Copy `production.env.example` to `/etc/sinbar/support-deployment.env`, replace
every value, then apply `root:root` and mode `0600`. The API environment at
`/etc/sinbar/support-session-api.env` must trust only
`SUPPORT_PORTAL_SESSION_IP/32`. `CLOUDFLARED_PROXY_CIDR` should normally be the
current `sinbar-noc-cloudflared` address on `CLOUDFLARED_NETWORK` as a `/32`;
preflight confirms all three values. Re-run deployment after any tunnel
recreation that changes this IP (or assign that container a reviewed static IP).
This prevents the tunnel from collapsing all visitors into one global Nginx
rate-limit identity and prevents spoofed `CF-Connecting-IP` input.

See the top-level `DEPLOYMENT.md` for the complete input tree and rollback
procedure.
