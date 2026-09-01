# Sinbar Remote Support portal 2.1.0

This black, gold, and white portal provides an Intel-style attended-support
download flow using unchanged official RustDesk 1.4.9 binaries.

- Windows downloads use the exact PURSLANE-signed portable EXE. Nginx supplies
  the approved Sinbar host and public key through RustDesk's supported compact
  filename configuration.
- macOS downloads use the unchanged signed and notarized RustDesk DMGs. The
  customer imports the exported Sinbar configuration and approves Apple's
  Screen Recording and Accessibility permissions.
- No permanent support password, custom browser protocol, session API, or
  Sinbar-built executable is used.

Validate with:

    python3 portal/tests/validate_portal.py

The canonical Nginx configuration is `deploy/nginx.conf`.
