# Windows assistant security model

The assistant exposes one operation: ensure the locally pinned RustDesk release is installed and open it for attended support. It is not a remote command runner.

## Trust boundaries

- The browser may provide only `sinbarsupport://start?token=<43-character-base64url>`.
- The token is sent once to the pinned HTTPS consume endpoint. It is never written to logs or a handoff file.
- A server response is accepted only after ECDSA P-256/SHA-256 verification with a public key embedded at release build time.
- The signed payload is rejected unless its action, attended flag, platform, architecture, timestamps, artifact URL, version, SHA-256, and publisher rule match local constants.
- The response signature is 64-byte IEEE-P1363 `r || s`; the embedded public key is the 65-byte uncompressed X9.63 P-256 point.
- Unknown and duplicate JSON properties are rejected. Manifests live for at most five minutes.
- The RustDesk MSI must come from the exact HTTPS NOC URL, match the locally pinned SHA-256, pass Windows `WinVerifyTrust`, have `PURSLANE` in the signing subject, and match the exact build-time SHA-256 pin of the signer certificate's DER SubjectPublicKeyInfo.
- SHA-256 and Authenticode are checked after download and repeated immediately before `msiexec`.
- The authorization expiry is checked again immediately before `msiexec`.
- The MSI is held through execution in a random, non-reparse staging directory created atomically under ProgramData with protected SYSTEM/Administrators-only ACLs, then removed.
- No RustDesk password, private key, API credential, deployment secret, shell command, or server-supplied process argument is accepted.
- After signed-manifest verification, a native default-No dialog identifies the signed session and requires explicit customer confirmation before UAC, installation, or RustDesk launch. Cancellation performs none of those actions.

## UAC behavior

The small assistant installer is per-user and registers the custom protocol under HKCU, so installing the assistant does not require elevation. On the first authorized support request, the normal process consumes the one-time token and verifies the signed manifest before invoking UAC. The elevated process receives only the already-signed envelope (not the token), verifies it again, installs RustDesk silently, and exits. The original medium-integrity process then launches RustDesk and exits, so the support window is not unnecessarily left elevated.

The elevated continuation repeats the confirmation before installation. This deliberately adds a second confirmation on first install so direct local replay of a still-valid signed envelope cannot bypass customer consent.

Normal protocol activations are serialized across token consumption and the UAC wait. A separate installation mutex protects the elevated staging/install section. The signed envelope contains no bearer credential or secret and cannot authorize another action; replay remains limited by its signed expiry and the fixed local action/pins.

Consequently, a random website cannot trigger UAC merely by constructing a syntactically valid custom-protocol link. Returning customers with the approved RustDesk version receive no UAC prompt.

## Signing separation

The server manifest private key and Authenticode private key must stay outside this source tree and outside the NOC web root. Only the P-256 manifest public key and certificate thumbprint enter the release build. The assistant EXEs, Setup EXE, and Inno uninstaller are Authenticode signed and RFC 3161 timestamped.

## Residual platform prompts

Windows controls browser external-protocol confirmation, SmartScreen reputation, and UAC. The assistant does not attempt to bypass those controls. A new certificate or low-reputation release can still produce SmartScreen guidance even when its signature is valid.
