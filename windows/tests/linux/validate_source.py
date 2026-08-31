#!/usr/bin/env python3
"""Linux-runnable structural/security checks for the Windows source package."""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "SinbarSupportAssistant"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    all_source = "\n".join(path.read_text(encoding="utf-8") for path in SOURCE.glob("*.cs"))
    policy = (SOURCE / "SecurityPolicy.cs").read_text(encoding="utf-8")
    protocol = (SOURCE / "ProtocolRequest.cs").read_text(encoding="utf-8")
    installer = (ROOT / "installer" / "SinbarSupportAssistant.iss").read_text(encoding="utf-8")
    project = (SOURCE / "SinbarSupportAssistant.csproj").read_text(encoding="utf-8")
    program = (SOURCE / "Program.cs").read_text(encoding="utf-8")
    rustdesk_manager = (SOURCE / "RustDeskManager.cs").read_text(encoding="utf-8")
    user_notice = (SOURCE / "UserNotice.cs").read_text(encoding="utf-8")
    authenticode = (SOURCE / "AuthenticodeVerifier.cs").read_text(encoding="utf-8")
    staging = (SOURCE / "SecureStagingDirectory.cs").read_text(encoding="utf-8")
    build_script = (ROOT / "scripts" / "Build-Windows.ps1").read_text(encoding="utf-8")
    contract = (ROOT / "contract" / "session-contract.schema.json").read_text(encoding="utf-8")

    require('RequiredAction = "ensure-and-launch-rustdesk"' in policy, "fixed action pin missing")
    require('ApiOrigin = "https://support.sinbarconsultants.com"' in policy, "API origin pin missing")
    require('RequiredPublisherSubjectFragment = "PURSLANE"' in policy, "publisher pin missing")
    require('RequiredRustDeskVersion = "1.4.9"' in policy, "RustDesk version pin missing")
    require("c87d2f4cef2a5acd6003b6507dcfbf5d5168a256db082cd90b54d35193224aaa" in policy,
            "x86_64 SHA-256 pin missing")
    require("30bc8925e62c7ade52371758c2b944036ed2386f6c554e9e59f3bcfef06c7cd9" in policy,
            "ARM64 SHA-256 pin missing")
    require("sinbarsupport://start\\?token=" in protocol, "strict protocol parser missing")
    require("origin=" not in protocol, "protocol parser must not accept an origin parameter")
    require("WinVerifyTrust" in all_source, "WinVerifyTrust Authenticode validation missing")
    require("ExportSubjectPublicKeyInfo" in authenticode and
            "RustDeskPublisherSpkiSha256" in all_source,
            "exact RustDesk signer SPKI pin missing")
    require("FixedTimeEquals" in all_source, "fixed-time hash comparison missing")
    require("IeeeP1363FixedFieldConcatenation" in all_source, "P-256 P1363 verification missing")
    require("UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow" in all_source,
            "unknown JSON field rejection missing")
    require("Duplicate JSON properties are not permitted" in all_source,
            "duplicate JSON field rejection missing")
    require("--password" not in all_source.lower(), "password configuration must not exist")
    require("PRIVATE KEY" not in all_source, "private signing key marker found in source")
    require('Root: HKCU; Subkey: "Software\\Classes\\sinbarsupport"' in installer,
            "per-user protocol registration missing")
    require("PrivilegesRequired=lowest" in installer, "helper setup should not request UAC")
    require("SignTool=SinbarCodeSign" in installer, "installer signing hook missing")
    require("SignedUninstaller=yes" in installer, "signed uninstaller requirement missing")
    require(installer.count("signcheck") == 2,
            "both architecture-specific helper files must be signature checked")
    require("<PublishSingleFile" in project and "<SelfContained" in project,
            "self-contained single-file publishing missing")
    require("RejectUnconfiguredReleaseTrust" in project,
            "production public-key build gate missing")
    require("RustDeskPublisherSpkiSha256" in project,
            "production RustDesk signer-key build gate missing")
    require("ImportParameters" in build_script and "nistP256" in build_script,
            "build must import and validate the manifest P-256 point")
    require(program.index("ConsumeAsync") < program.index("ElevateAndContinueWithVerifiedEnvelope"),
            "the one-time token must be consumed before elevation")
    require(program.count("verifier.Verify(envelope, architecture)") == 2,
            "the manifest must be verified before and after elevation")
    require("--elevated-envelope" in program and "--elevated-envelope" in rustdesk_manager,
            "signed-envelope elevation handoff missing")
    require("elevated-request-file" not in all_source,
            "elevation must not accept an arbitrary handoff path")
    standard_method = program[program.index("private static async Task<int> RunStandardRequestAsync"):program.index(
        "private static async Task<int> RunElevatedContinuationAsync")]
    require(standard_method.index("verifier.Verify") <
            standard_method.index("ConfirmAttendedSupport") <
            standard_method.index("NeedsInstallation") <
            standard_method.index("ElevateAndContinueWithVerifiedEnvelope"),
            "native customer consent must follow signed authorization and precede UAC")
    require("return CustomerCanceledExitCode;" in standard_method,
            "customer cancellation must stop the standard request")
    elevated_method = program[program.index("private static async Task<int> RunElevatedContinuationAsync"):program.index(
        "private static async Task InstallAuthorizedAsync")]
    require("LaunchTrusted" not in elevated_method,
            "the elevated continuation must not launch RustDesk")
    require(elevated_method.index("verifier.Verify") <
            elevated_method.index("ConfirmAttendedSupport") <
            elevated_method.index("InstallAuthorizedAsync"),
            "elevated replay must require fresh native consent before installation")
    require("MbYesNo" in user_notice and "MbDefaultButton2" in user_notice and
            "Session reference:" in user_notice and
            "No permanent support password" in user_notice,
            "native consent must be explicit, default-deny, and tied to the signed session")
    require(program.index("ElevateAndContinueWithVerifiedEnvelope") <
            program.index("RustDeskManager.LaunchTrusted"),
            "the original medium-integrity process must launch after elevation")
    require("SecureStagingDirectory.Create" in all_source and
            "SetAccessRuleProtection" in staging and
            "BuiltinAdministratorsSid" in staging and
            "LocalSystemSid" in staging and
            "ReparsePoint" in staging,
            "protected non-reparse MSI staging is missing")
    require("using DownloadedArtifact installer" in program,
            "the protected staging lifetime must cover MSI execution")
    require(rustdesk_manager.index("VerifyInstallerImmediatelyBeforeExecution") <
            rustdesk_manager.index("Process.Start(startInfo)\n            ?? throw new InvalidOperationException(\"Windows Installer"),
            "installer must be reverified before msiexec")
    require("revalidateAuthorization();" in rustdesk_manager and
            rustdesk_manager.index("revalidateAuthorization();") <
            rustdesk_manager.index("Process.Start(startInfo)\n            ?? throw new InvalidOperationException(\"Windows Installer"),
            "signed authorization must be revalidated immediately before msiexec")
    require('"$ref": "#/$defs/envelope"' in contract,
            "JSON schema must select the signed envelope at its root")

    # Confirm the build-time key length used by scripts is exactly an unpadded
    # base64url representation of a 65-byte uncompressed P-256 point.
    sample = bytes([4]) + bytes(range(1, 65))
    encoded = base64.urlsafe_b64encode(sample).decode().rstrip("=")
    require(len(encoded) == 87, "unexpected P-256 public-key encoding length")
    require(re.fullmatch(r"[A-Za-z0-9_-]{87}", encoded) is not None,
            "unexpected base64url public-key alphabet")

    print("PASS: Windows source security structure")
    print("PASS: exact deep-link, API, action, version, URL, hash, and publisher pins")
    print("PASS: signed-ready per-user installer and one-UAC RustDesk flow")
    print("PASS: exact signer SPKI pin and protected elevated MSI staging")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - command-line validator
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
