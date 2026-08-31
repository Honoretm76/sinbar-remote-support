#!/usr/bin/env python3
"""Validate that every platform agrees on release names, paths, and versions."""

from __future__ import annotations

import argparse
import json
import pathlib
import plistlib
import re
import sys
import xml.etree.ElementTree as ET


WINDOWS_ASSET = "Sinbar-Support-Assistant-Setup.exe"
MACOS_ASSET = "Sinbar-Support-Assistant.pkg"
MANIFEST_KEY_ID = "sinbar-support-manifest-p256-v1"


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"ERROR: {message}")


def regex_value(path: pathlib.Path, pattern: str, label: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        fail(f"could not determine {label} from {path}")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True, type=pathlib.Path)
    parser.add_argument("--tag", default="")
    parser.add_argument("--manifest-key-id", required=True)
    args = parser.parse_args()

    root = args.repository_root.resolve(strict=True)
    if args.manifest_key_id != MANIFEST_KEY_ID:
        fail(f"manifest key ID must be exactly {MANIFEST_KEY_ID}")
    required = (
        root / "windows/scripts/Build-Windows.ps1",
        root / "windows/installer/SinbarSupportAssistant.iss",
        root / "macos/scripts/release.sh",
        root / "macos/scripts/notarize.sh",
        root / "portal/download/manifest.json",
    )
    for path in required:
        if not path.is_file():
            fail(f"required release source is missing: {path.relative_to(root)}")

    notarize_source = (root / "macos/scripts/notarize.sh").read_text(
        encoding="utf-8"
    )
    if "NOTARYTOOL_KEYCHAIN" not in notarize_source or "--keychain" not in notarize_source:
        fail("macOS notarization must support an explicit ephemeral file keychain")

    project = ET.parse(
        root / "windows/src/SinbarSupportAssistant/SinbarSupportAssistant.csproj"
    )
    version_node = project.find(".//VersionPrefix")
    if version_node is None or not version_node.text:
        fail("Windows VersionPrefix is missing")
    windows_version = version_node.text.strip()

    inno_version = regex_value(
        root / "windows/installer/SinbarSupportAssistant.iss",
        r'^#define\s+MyAppVersion\s+"([0-9]+\.[0-9]+\.[0-9]+)"$',
        "Inno Setup version",
    )
    package_version = regex_value(
        root / "macos/scripts/build-pkg.sh",
        r"^\s*--version\s+([0-9]+\.[0-9]+\.[0-9]+)\s*\\?$",
        "macOS package version",
    )

    with (root / "macos/Info.plist.template").open("rb") as handle:
        info = plistlib.load(handle)
    macos_version = str(info.get("CFBundleShortVersionString", ""))

    portal = json.loads(
        (root / "portal/download/manifest.json").read_text(encoding="utf-8")
    )
    portal_version = str(portal.get("portalVersion", ""))
    versions = {
        "Windows project": windows_version,
        "Windows installer": inno_version,
        "macOS app": macos_version,
        "macOS package": package_version,
        "portal": portal_version,
    }
    if len(set(versions.values())) != 1:
        fail(f"release version mismatch: {versions}")
    version = windows_version
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        fail(f"release version is not semantic: {version}")
    if args.tag and args.tag != f"v{version}":
        fail(f"tag {args.tag!r} does not match source version v{version}")

    installers = {
        item.get("platform"): item
        for item in portal.get("installers", [])
        if isinstance(item, dict)
    }
    expected_paths = {
        "windows": f"/download/v{version}/windows/{WINDOWS_ASSET}",
        "macos": f"/download/v{version}/macos/{MACOS_ASSET}",
    }
    for platform, expected_path in expected_paths.items():
        entry = installers.get(platform)
        if entry is None:
            fail(f"portal installer entry is missing: {platform}")
        if entry.get("path") != expected_path:
            fail(f"portal {platform} path must be {expected_path}")
        if entry.get("publicationStatus") != "artifact-required":
            fail("source portal must fail closed until signed artifacts are deployed")

    windows_rustdesk = regex_value(
        root / "windows/src/SinbarSupportAssistant/SecurityPolicy.cs",
        r'RequiredRustDeskVersion\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"',
        "Windows RustDesk version pin",
    )
    with (root / "macos/Config/runtime-config.plist.template").open("rb") as handle:
        runtime = plistlib.load(handle)
    macos_rustdesk = {
        str(item.get("Version", ""))
        for item in runtime.get("RustDeskArtifacts", {}).values()
        if isinstance(item, dict)
    }
    if not windows_rustdesk or macos_rustdesk != {windows_rustdesk}:
        fail("Windows and macOS RustDesk version pins do not agree")
    if "latest" in (
        root / "macos/Config/runtime-config.plist.template"
    ).read_text(encoding="utf-8").lower():
        fail("macOS runtime artifacts must not use an unpinned latest URL")

    print(
        "PASS: release contract is consistent "
        f"(version={version}, RustDesk={windows_rustdesk})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ET.ParseError, plistlib.InvalidFileException, json.JSONDecodeError) as exc:
        print(f"ERROR: invalid release source: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
