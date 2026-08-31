#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import plistlib
import re
import subprocess
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCES = ROOT / "Sources"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    with (ROOT / "Info.plist.template").open("rb") as handle:
        info = plistlib.load(handle)
    require(info["CFBundleIdentifier"] == "com.sinbarconsultants.supportassistant", "bundle ID")
    schemes = [
        scheme
        for item in info["CFBundleURLTypes"]
        for scheme in item["CFBundleURLSchemes"]
    ]
    require(schemes == ["sinbarsupport"], "URL scheme must be exact")
    require("NSAppTransportSecurity" not in info, "ATS exceptions are prohibited")

    with (ROOT / "Entitlements.plist").open("rb") as handle:
        entitlements = plistlib.load(handle)
    forbidden_entitlements = {
        "com.apple.security.get-task-allow",
        "com.apple.security.cs.disable-library-validation",
        "com.apple.security.cs.allow-jit",
        "com.apple.security.cs.allow-unsigned-executable-memory",
        "com.apple.security.network.server",
    }
    require(not forbidden_entitlements.intersection(entitlements), "dangerous entitlement")

    with (ROOT / "Config/runtime-config.plist.template").open("rb") as handle:
        runtime = plistlib.load(handle)
    require(runtime["APIBaseURL"] == "https://support.sinbarconsultants.com", "API pin")
    require(runtime["ArtifactPathPrefix"] == "/download/vendor/rustdesk/", "artifact prefix")
    require(set(runtime["RustDeskArtifacts"]) == {"x86_64", "arm64"}, "architecture catalog")
    require(runtime["RustDeskArtifacts"]["x86_64"]["URL"].endswith("rustdesk-1.4.9-x86_64.dmg"), "x64 URL")
    require(runtime["RustDeskArtifacts"]["arm64"]["URL"].endswith("rustdesk-1.4.9-aarch64.dmg"), "arm URL")
    runtime_source = read(SOURCES / "SinbarSupportCore/RuntimeConfiguration.swift")
    require('rustDeskBundleIdentifier == "com.carriez.rustdesk"' in runtime_source, "RustDesk bundle ID pin")

    with (ROOT / "Config/com.sinbarconsultants.supportassistant.installhelper.plist.template").open("rb") as handle:
        daemon = plistlib.load(handle)
    require(set(daemon["MachServices"]) == {"com.sinbarconsultants.supportassistant.installhelper"}, "Mach service")
    require("Sockets" not in daemon, "helper must not listen on a network socket")

    source_text = "\n".join(read(path) for path in sorted(SOURCES.rglob("*.swift")))
    forbidden_source = [
        "http" + "://",
        "NSAllowsArbitraryLoads",
        "allowsAnyHTTPSCertificate",
        "osascript",
        " /bin/sh",
        " /bin/bash",
        " /bin/zsh",
        "sudo ",
        "--password",
        "--get-id",
        "--config",
        "removeExtendedAttribute",
    ]
    for value in forbidden_source:
        require(value not in source_text, f"forbidden source capability: {value}")

    repository_text = "\n".join(
        read(path)
        for path in sorted(ROOT.rglob("*"))
        if path.is_file()
        and path.name != "static_security_tests.py"
        and (path.suffix in {".swift", ".md", ".plist", ".template", ".sh"}
             or path.name in {"preinstall", "postinstall"})
    )
    for secret_marker in (
        "BEGIN PRIVATE KEY",
        "BEGIN EC PRIVATE KEY",
        "dop_v1_",
        "ghp_",
        "xoxb-",
    ):
        require(secret_marker not in repository_text, f"possible embedded secret: {secret_marker}")

    deep_link = read(SOURCES / "SinbarSupportCore/DeepLink.swift")
    require('== "sinbarsupport"' in deep_link, "scheme is not fixed")
    require('== "start"' in deep_link, "action host is not fixed")
    require('queryItems.count == 1' in deep_link, "query field count is not fixed")
    require('queryItems[0].name == "token"' in deep_link, "token is not the only query field")
    require("{43}" in deep_link, "launch token is not a 256-bit base64url token")

    request_model = read(SOURCES / "SinbarSupportCore/ManifestModels.swift")
    for field in ("token", "platform", "architecture", "assistantVersion"):
        require(re.search(rf"public let {field}: String", request_model) is not None, f"missing request field {field}")
    require("command" not in request_model.lower(), "remote commands are prohibited")
    require("arguments" not in request_model.lower(), "remote arguments are prohibited")

    tool_source = read(SOURCES / "SinbarSupportCore/SystemTool.swift")
    tool_paths = set(re.findall(r'case \w+ = "([^"]+)"', tool_source))
    require(tool_paths == {"/usr/bin/hdiutil", "/usr/sbin/spctl", "/usr/bin/ditto", "/usr/sbin/pkgutil", "/usr/sbin/installer"}, "system tool allowlist changed")
    process_users = [path for path in SOURCES.rglob("*.swift") if "Process()" in read(path)]
    require(process_users == [SOURCES / "SinbarSupportCore/SystemTool.swift"], "Process escaped the fixed tool runner")

    helper_main = read(SOURCES / "SinbarSupportInstallHelper/main.swift")
    helper_client = read(SOURCES / "SinbarSupportAssistant/PrivilegedHelperClient.swift")
    require("setConnectionCodeSigningRequirement" in helper_main, "helper does not authenticate clients")
    require("setCodeSigningRequirement" in helper_client, "client does not authenticate helper peer")
    require("auditToken" not in source_text, "non-public XPC audit-token access is prohibited")
    require("RENAME_SWAP" in source_text, "RustDesk replacement must be crash-atomic")
    require("InstallTransactions" in source_text, "replacement staging must be root-only")
    require("asyncAfter(deadline: .now() + 300)" not in helper_main, "helper timer may not kill an active install")

    app_delegate = read(SOURCES / "SinbarSupportAssistant/AppDelegate.swift")
    coordinator = read(SOURCES / "SinbarSupportAssistant/SupportCoordinator.swift")
    status_window = read(SOURCES / "SinbarSupportAssistant/StatusWindowController.swift")
    require("CommandLine.arguments" not in app_delegate, "support tokens may not be accepted through argv")
    verified_index = coordinator.index("let manifest = try verifier.verify")
    consent_index = coordinator.index("guard await consent(manifest)")
    install_index = coordinator.index("installedRustDeskIsApproved")
    require(verified_index < consent_index < install_index, "native consent must gate install and launch")
    require("NSAlert()" in status_window, "customer consent must use a native AppKit alert")
    require("SupportError.userCancelled" in coordinator, "cancellation must stop the workflow")
    cancel_index = status_window.index('alert.addButton(withTitle: "Cancel")')
    continue_index = status_window.index('alert.addButton(withTitle: "Continue")')
    require(cancel_index < continue_index, "Cancel must be the first consent action")
    require('alert.buttons.first?.keyEquivalent = "\\r"' in status_window, "Return must default to Cancel")
    require("event.keyCode == 53" in status_window, "Escape must cancel consent")
    require(".alertSecondButtonReturn" in status_window, "only explicit Continue may authorize support")

    runtime_configuration = read(SOURCES / "SinbarSupportCore/RuntimeConfiguration.swift")
    require(
        runtime_configuration.count("certificate 1[field.1.2.840.113635.100.6.2.6] exists") == 2,
        "both XPC peers must require the Developer ID intermediate",
    )
    require(
        runtime_configuration.count("certificate leaf[field.1.2.840.113635.100.6.1.13] exists") == 2,
        "both XPC peers must require a Developer ID Application leaf",
    )

    for script in sorted((ROOT / "scripts").rglob("*")):
        if script.is_file() and script.suffix == ".sh":
            subprocess.run(["bash", "-n", str(script)], check=True)
    for script in sorted((ROOT / "scripts/package-scripts").iterdir()):
        subprocess.run(["sh", "-n", str(script)], check=True)

    print("PASS: macOS source security policy and packaging syntax")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
