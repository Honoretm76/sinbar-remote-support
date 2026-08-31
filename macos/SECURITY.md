# Security invariants

Changes must preserve all of the following:

- A launch URL is an untrusted wake-up signal, never a command or credential for remote
  access.
- The token is opaque, one-time, short-lived, exactly 256 bits, and never logged.
- The assistant accepts one action: ensure and launch verified RustDesk for attended use.
- The customer must explicitly approve a native AppKit confirmation after manifest
  verification and before any download, helper request, installation, or RustDesk launch.
  Cancel is first and Return-default, Escape also cancels, and only deliberate Continue
  selection authorizes the action. Cancellation terminates without performing it.
- No API field may control an origin, executable, command, argument, environment variable,
  local destination, Apple Team ID, bundle ID, or permanent access setting.
- The signed manifest is authenticated before JSON decoding and all JSON object key sets
  are exact.
- P-256 signature verification uses the raw payload bytes, a pinned key ID, a pinned
  X9.63 public point, and a 64-byte IEEE-P1363 signature.
- Release identity and hashes are pinned in a root-owned, non-writable configuration file.
- HTTPS uses Apple's normal trust evaluation and rejects redirects.
- The root helper verifies the signed caller, artifact path ownership, signed manifest,
  SHA-256, RustDesk identity, version, and Gatekeeper result independently.
- Only allowlisted absolute Apple system-tool paths may be executed; no shell is involved
  in app/helper runtime operations.
- The helper exposes only a local launchd Mach service and never opens a network socket.
- Both XPC directions require a pinned identifier and Team ID under the Developer ID
  Application leaf and Developer ID intermediate certificate OIDs.
- Installation rejects symlinks and untrusted pre-existing applications, stages updates,
  and restores the previous valid app if replacement fails.
- Quarantine, Gatekeeper, Screen Recording, Accessibility, and other macOS protections are
  never removed, disabled, or bypassed.
- No RustDesk password, private server key, signing private key, API key, or reusable
  support credential may be embedded in source, packages, manifests, or URLs.

Any proposal that weakens one of these boundaries requires a new threat review and must
not be merged as a convenience change.
