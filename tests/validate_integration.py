#!/usr/bin/env python3
"""Fail-closed cross-component contract validation for release 2.0.0."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "2.0.0"
RUSTDESK_VERSION = "1.4.9"
KEY_ID = "sinbar-support-manifest-p256-v1"
ORIGIN = "https://support.sinbarconsultants.com"
WINDOWS_INSTALLER = "/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe"
MACOS_INSTALLER = "/download/v2.0.0/macos/Sinbar-Support-Assistant.pkg"
RUSTDESK = {
    ("windows", "x86_64"): (
        f"{ORIGIN}/download/vendor/rustdesk/1.4.9/windows/rustdesk-1.4.9-x86_64.msi",
        "c87d2f4cef2a5acd6003b6507dcfbf5d5168a256db082cd90b54d35193224aaa",
    ),
    ("windows", "arm64"): (
        f"{ORIGIN}/download/vendor/rustdesk/1.4.9/windows/rustdesk-1.4.9-aarch64.msi",
        "30bc8925e62c7ade52371758c2b944036ed2386f6c554e9e59f3bcfef06c7cd9",
    ),
    ("macos", "x86_64"): (
        f"{ORIGIN}/download/vendor/rustdesk/1.4.9/macos/rustdesk-1.4.9-x86_64.dmg",
        "fa1129a0635019f9c5841937942cc2b08be028a192f47c009edde7e53812904e",
    ),
    ("macos", "arm64"): (
        f"{ORIGIN}/download/vendor/rustdesk/1.4.9/macos/rustdesk-1.4.9-aarch64.dmg",
        "f7935597b247d42c8f2a2ed71176a9f5868018cd9e1a33b8096418a668c8caf0",
    ),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(relative: str) -> str:
    path = ROOT / relative
    require(path.is_file(), f"missing {relative}")
    return path.read_text(encoding="utf-8")


def env_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name] = value
    return values


def main() -> int:
    portal = json.loads(read("portal/download/manifest.json"))
    portal_js = read("portal/assets/app.js")
    server_registry = json.loads(read("server/config/artifacts.template.json"))
    server_env = env_values(read("server/guardian.env.example"))
    windows_policy = read("windows/src/SinbarSupportAssistant/SecurityPolicy.cs")
    mac_runtime = read("macos/Config/runtime-config.plist.template")
    deploy_nginx = read("deploy/nginx.conf")
    deploy_compose = read("deploy/compose.assistant.yaml")

    require(portal["portalVersion"] == VERSION, "portal version mismatch")
    require(
        portal["sessionContract"]["maximumLifetimeSeconds"] == 120,
        "portal session TTL mismatch",
    )
    require("[A-Za-z0-9_-]{43}" in portal_js, "portal token length is not exact")
    installers = {item["platform"]: item["path"] for item in portal["installers"]}
    require(installers == {"windows": WINDOWS_INSTALLER, "macos": MACOS_INSTALLER},
            "portal installer paths mismatch")

    require(server_env["MANIFEST_KEY_ID"] == KEY_ID, "server key ID mismatch")
    require(server_env["SESSION_TTL_SECONDS"] == "120", "server session TTL mismatch")
    require(
        server_env["MANIFEST_SIGNING_KEY_FILE"]
        == "/run/secrets/support-manifest-p256.pem",
        "server key mount path mismatch",
    )
    require(
        f'ManifestKeyId = "{KEY_ID}"' in windows_policy,
        "Windows key ID mismatch",
    )
    require("<string>__MANIFEST_KEY_ID__</string>" in mac_runtime,
            "macOS key ID must be injected at signed build time")

    rows = {
        (row["platform"], row["architecture"]): row
        for row in server_registry["artifacts"]
    }
    require(set(rows) == set(RUSTDESK), "server artifact target set mismatch")
    env_hash_names = {
        ("windows", "x86_64"): "RUSTDESK_WINDOWS_X86_64_SHA256",
        ("windows", "arm64"): "RUSTDESK_WINDOWS_ARM64_SHA256",
        ("macos", "x86_64"): "RUSTDESK_MACOS_X86_64_SHA256",
        ("macos", "arm64"): "RUSTDESK_MACOS_ARM64_SHA256",
    }
    for target, (url, digest) in RUSTDESK.items():
        row = rows[target]
        require(row["version"] == RUSTDESK_VERSION, f"version mismatch for {target}")
        require(row["url"] == url, f"URL mismatch for {target}")
        require(row["sha256"] == "${" + env_hash_names[target] + "}",
                f"server digest variable mismatch for {target}")
        require(server_env[env_hash_names[target]] == digest,
                f"recorded digest mismatch for {target}")
        require(url in deploy_nginx or "/download/vendor/rustdesk/" in deploy_nginx,
                f"Nginx mirror route missing for {target}")

    for value in (WINDOWS_INSTALLER, MACOS_INSTALLER):
        require(value in portal_js, f"portal JavaScript missing {value}")
        require(value in deploy_nginx, f"Nginx missing {value}")
    for endpoint in (
        "/api/v1/support/sessions",
        "/api/v1/support/sessions/consume",
    ):
        require(endpoint in deploy_nginx, f"Nginx missing {endpoint}")

    require(
        "/etc/sinbar/secrets/support-manifest-p256.pem:"
        "/run/secrets/support-manifest-p256.pem:ro" in deploy_compose,
        "deployment key mount mismatch",
    )
    require("internal: true" in deploy_compose, "session API network must be internal")
    require("read_only: true" in deploy_compose, "session API root filesystem must be read-only")
    require("no-new-privileges:true" in deploy_compose, "session API privilege lock missing")

    placeholder_markers = (
        "REPLACE_WITH_REVIEWED_IMAGE_DIGEST",
        "REPLACE_WITH_VERIFIED_TEAM_ID",
        "__SINBAR_TEAM_IDENTIFIER__",
        "__MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL__",
    )
    combined = "\n".join((
        read("server/Dockerfile"),
        read("server/guardian.env.example"),
        mac_runtime,
    ))
    for marker in placeholder_markers:
        require(marker in combined, f"fail-closed production gate was removed: {marker}")

    print("PASS: portal, API, Windows, macOS, Nginx, and Compose contracts align")
    print("PASS: exact 120-second/43-character one-use launch contract is pinned")
    print("PASS: RustDesk 1.4.9 paths and four recorded SHA-256 values align")
    print("PASS: unresolved signing/vendor identities remain fail-closed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
