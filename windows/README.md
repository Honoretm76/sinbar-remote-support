# Sinbar Support Assistant for Windows 2.0.0

This is the Windows half of Sinbar's Intel-style support experience. It replaces a ZIP/manual script workflow with a signed local assistant and the `sinbarsupport://` protocol. The NOC server authorizes a short-lived attended-support session; all executable code still runs locally under Windows security controls.

No compiled binaries are checked in or represented as complete. A production build requires Sinbar's manifest public key, the approved RustDesk signing-key SPKI hash, and a Windows Authenticode certificate.

## Customer flow

1. The portal attempts `sinbarsupport://start?token=<one-time-256-bit-token>`.
2. If the assistant is absent, the portal downloads `/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe`.
3. The signed per-user Setup installs the assistant, registers the protocol, closes automatically, and returns to `https://support.sinbarconsultants.com/?assistant=installed`.
4. The portal issues a new token and launches the protocol again.
5. The assistant consumes the token at `POST /api/v1/support/sessions/consume` and verifies the returned signed manifest before elevation.
6. A native, default-No confirmation displays a reference derived from the signed session. The customer should continue only if they clicked Start Remote Support while speaking with Sinbar.
7. If RustDesk 1.4.9 is missing, one UAC prompt authorizes its silent MSI installation. The elevated continuation asks for confirmation again so a direct local replay cannot bypass consent. RustDesk then opens from the original customer process; the helper exits. Returning visits skip installation and UAC but still require session-specific confirmation before launch.

Choosing No at either confirmation exits without elevation, installation, or launching RustDesk.

The helper never configures a permanent password. Version 2.0 uses RustDesk's public network and attended-support window only.

## API contract

The consume request is exactly:

```json
{
  "token": "43-character-base64url-value",
  "platform": "windows",
  "architecture": "x86_64",
  "assistantVersion": "2.0.0"
}
```

The response is an ECDSA-signed envelope:

```json
{
  "keyId": "sinbar-support-manifest-p256-v1",
  "payload": "base64url-utf8-json",
  "signature": "base64url-64-byte-p1363-signature"
}
```

The exact payload schema is in `contract/session-contract.schema.json`. The signature covers the decoded payload bytes exactly. The issue endpoint used by the portal is `POST /api/v1/support/sessions`; the assistant only calls the consume endpoint.

## Source layout

- `src/SinbarSupportAssistant`: self-contained .NET 8 WinExe source.
- `installer/SinbarSupportAssistant.iss`: per-user Inno Setup and HKCU protocol registration.
- `scripts/Build-Windows.ps1`: x64/ARM64 publish, Authenticode signing, signed Inno Setup/uninstaller, verification, and release manifest generation.
- `tests/ContractTests`: dependency-free .NET contract tests.
- `tests/linux/validate_source.py`: Linux-runnable security/structure checks.
- `config/production.build.example.json`: public build-input template; no secrets belong there.

## Prerequisites

- Windows build host with .NET 8 SDK.
- Inno Setup 6.7.1 or later (`iscc.exe`).
- Windows SDK `signtool.exe`.
- Authenticode code-signing certificate/private key accessible to `signtool`.
- The production P-256 manifest public key. Keep its private counterpart only in the session-signing service or managed signing system.
- The SHA-256 of the DER SubjectPublicKeyInfo for the exact approved RustDesk Authenticode leaf signing key. This is a public pin, but it must be measured from the independently verified official MSI on Windows before release.

The NOC server must publish the two already-pinned RustDesk artifacts:

| Architecture | NOC path | SHA-256 |
|---|---|---|
| x86_64 | `/download/vendor/rustdesk/1.4.9/windows/rustdesk-1.4.9-x86_64.msi` | `c87d2f4cef2a5acd6003b6507dcfbf5d5168a256db082cd90b54d35193224aaa` |
| ARM64 | `/download/vendor/rustdesk/1.4.9/windows/rustdesk-1.4.9-aarch64.msi` | `30bc8925e62c7ade52371758c2b944036ed2386f6c554e9e59f3bcfef06c7cd9` |

Both files must retain a valid Authenticode signature whose certificate subject contains `PURSLANE` and whose leaf certificate public key matches the build-time SPKI SHA-256 pin.

Measure the public signer-key pin from an independently acquired MSI only after matching its approved file hash:

```powershell
.\scripts\Get-RustDeskSignerPin.ps1 `
  -MsiPath .\rustdesk-1.4.9-x86_64.msi `
  -ExpectedSha256 c87d2f4cef2a5acd6003b6507dcfbf5d5168a256db082cd90b54d35193224aaa
```

Repeat for ARM64 and confirm both approved artifacts report the signer key expected by release policy before supplying the pin to the canonical build.

The support portal Nginx allowlist must explicitly serve the assistant `.exe` and the two versioned vendor `.msi` paths as `application/octet-stream` and `application/x-msi` (or `application/octet-stream`) respectively. Keep arbitrary file serving disabled. Example route shapes:

```nginx
location = /download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe { try_files $uri =404; }
location ~ ^/download/vendor/rustdesk/1\.4\.9/windows/rustdesk-1\.4\.9-(x86_64|aarch64)\.msi$ { try_files $uri =404; }
```

These HTTP responses are downloads by design. The Intel-style experience comes from the installed, signed assistant handling `sinbarsupport://`; browsers cannot directly execute a server-hosted installer without a local trusted component and normal Windows confirmations.

## Test and build

Linux structural validation:

```bash
python3 tests/linux/validate_source.py
python3 tests/linux/validate_crypto_contract.py
```

Dependency-free .NET contract tests:

```powershell
dotnet run --project .\tests\ContractTests\ContractTests.csproj
```

Production build from PowerShell 7.4 on the Windows signing host:

```powershell
.\scripts\Build-Windows.ps1 `
  -ManifestPublicKeyX963Base64Url '<87-character-public-key>' `
  -RustDeskPublisherSpkiSha256 '<64-hex-SPKI-SHA256>' `
  -CodeSigningCertificateThumbprint '<40-hex-thumbprint>'
```

Expected release outputs:

```text
artifacts/win-x64/SinbarSupportAssistant.exe
artifacts/win-arm64/SinbarSupportAssistant.exe
artifacts/installer/Sinbar-Support-Assistant-Setup.exe
artifacts/installer/Sinbar-Support-Assistant-Setup.manifest.json
```

Deploy only after `signtool verify /pa /all /v` succeeds for both assistants and Setup, the exact Sinbar signing-certificate thumbprint is confirmed, clean Windows x64 and ARM64 tests pass, the protocol round-trip succeeds, and RustDesk remains open after all Sinbar installer/helper windows close.
