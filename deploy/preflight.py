#!/usr/bin/env python3
"""Fail-closed validation and staging for Sinbar Support Assistant 2.0."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import ipaddress
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
from typing import Any, NoReturn


VERSION = "2.0.0"
ORIGIN = "https://support.sinbarconsultants.com"
KEY_FILE = pathlib.Path("/etc/sinbar/secrets/support-manifest-p256.pem")
WINDOWS_INSTALLER = "Sinbar-Support-Assistant-Setup.exe"
MACOS_INSTALLER = "Sinbar-Support-Assistant.pkg"
INSTALLERS = {
    "windows": WINDOWS_INSTALLER,
    "macos": MACOS_INSTALLER,
}
RUSTDESK = {
    ("windows", "x86_64"): (
        "rustdesk-1.4.9-x86_64.msi",
        "c87d2f4cef2a5acd6003b6507dcfbf5d5168a256db082cd90b54d35193224aaa",
    ),
    ("windows", "arm64"): (
        "rustdesk-1.4.9-aarch64.msi",
        "30bc8925e62c7ade52371758c2b944036ed2386f6c554e9e59f3bcfef06c7cd9",
    ),
    ("macos", "x86_64"): (
        "rustdesk-1.4.9-x86_64.dmg",
        "fa1129a0635019f9c5841937942cc2b08be028a192f47c009edde7e53812904e",
    ),
    ("macos", "arm64"): (
        "rustdesk-1.4.9-aarch64.dmg",
        "f7935597b247d42c8f2a2ed71176a9f5868018cd9e1a33b8096418a668c8caf0",
    ),
}
DEPLOYMENT_KEYS = {
    "SUPPORT_API_IMAGE",
    "REVIEWED_SOURCE_COMMIT",
    "SUPPORT_SESSION_SUBNET",
    "SUPPORT_PORTAL_SESSION_IP",
    "SUPPORT_API_SESSION_IP",
    "CLOUDFLARED_CONTAINER",
    "CLOUDFLARED_NETWORK",
    "CLOUDFLARED_PROXY_CIDR",
    "MANIFEST_KEY_ID",
    "MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL",
    "WINDOWS_SIGNER_CERT_SHA256",
    "WINDOWS_SIGNER_SUBJECT",
    "APPLE_INSTALLER_TEAM_ID",
    "RUSTDESK_MACOS_TEAM_IDENTIFIER",
}
PLACEHOLDER = re.compile(
    r"(?:REPLACE|PLACEHOLDER|CHANGEME|CHANGE_ME|EXAMPLE|YOUR[_-]|"
    r"example[.]invalid|__[^_]+__|<[A-Z][A-Z0-9 _.-]*>)",
    re.IGNORECASE,
)
HEX64 = re.compile(r"[0-9a-f]{64}")
RFC3339 = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def fail(message: str) -> NoReturn:
    raise SystemExit(f"ERROR: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def regular_file(path: pathlib.Path, label: str, minimum_size: int = 1) -> pathlib.Path:
    require(path.exists(), f"missing {label}: {path}")
    require(not path.is_symlink(), f"{label} must not be a symlink: {path}")
    require(path.is_file(), f"{label} must be a regular file: {path}")
    require(path.stat().st_size >= minimum_size, f"{label} is empty or implausibly small: {path}")
    return path


def privileged_file(path: pathlib.Path, label: str, allowed_modes: set[int]) -> pathlib.Path:
    regular_file(path, label)
    mode = stat.S_IMODE(path.stat().st_mode)
    require(mode in allowed_modes, f"{label} mode must be one of {sorted(oct(x) for x in allowed_modes)}")
    require(path.stat().st_uid in {0, 10001}, f"{label} must be owned by root or API uid 10001")
    return path


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: pathlib.Path, label: str) -> dict[str, Any]:
    regular_file(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {label}: {exc}")
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def parse_env(path: pathlib.Path, label: str, *, privileged: bool = True) -> dict[str, str]:
    if privileged:
        privileged_file(path, label, {0o600})
    else:
        regular_file(path, label)
    result: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        require("=" in line and not line.startswith("export "), f"invalid {label} line {number}")
        name, value = line.split("=", 1)
        require(re.fullmatch(r"[A-Z][A-Z0-9_]*", name) is not None, f"invalid name on {label} line {number}")
        require(name not in result, f"duplicate {name} in {label}")
        require(value == value.strip() and value != "", f"empty or padded {name} in {label}")
        require(not PLACEHOLDER.search(value), f"{name} still contains a placeholder")
        result[name] = value
    return result


def decode_b64(value: str, label: str, *, urlsafe: bool = False) -> bytes:
    try:
        if urlsafe:
            require("=" not in value, f"{label} must be unpadded base64url")
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        return base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        fail(f"{label} is not valid base64: {exc}")


def validate_timestamp(value: Any, label: str) -> None:
    require(isinstance(value, str) and RFC3339.fullmatch(value) is not None, f"{label} must be RFC3339 UTC")
    parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    require(parsed <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5), f"{label} is in the future")


def validate_team_id(value: str, label: str) -> None:
    require(re.fullmatch(r"[A-Z0-9]{10}", value) is not None, f"{label} must be a verified ten-character Team ID")
    require(value not in {"0000000000", "ABCDEFGHIJ", "TEAMID0000", "REPLACE10"}, f"{label} is a placeholder")


def validate_deployment_env(path: pathlib.Path) -> dict[str, str]:
    env = parse_env(path, "deployment environment")
    require(set(env) == DEPLOYMENT_KEYS, f"deployment environment fields differ: missing={sorted(DEPLOYMENT_KEYS-set(env))}, extra={sorted(set(env)-DEPLOYMENT_KEYS)}")

    image = env["SUPPORT_API_IMAGE"]
    match = re.fullmatch(r"[a-z0-9][a-z0-9._/:+-]*@sha256:([0-9a-f]{64})", image)
    require(match is not None, "SUPPORT_API_IMAGE must be an immutable repository@sha256 digest")
    require(match.group(1) != "0" * 64, "SUPPORT_API_IMAGE digest is a placeholder")
    require(re.fullmatch(r"[0-9a-f]{40}", env["REVIEWED_SOURCE_COMMIT"]) is not None, "REVIEWED_SOURCE_COMMIT must be a full lowercase Git commit")

    try:
        subnet = ipaddress.ip_network(env["SUPPORT_SESSION_SUBNET"], strict=True)
        portal_ip = ipaddress.ip_address(env["SUPPORT_PORTAL_SESSION_IP"])
        api_ip = ipaddress.ip_address(env["SUPPORT_API_SESSION_IP"])
        cloud_cidr = ipaddress.ip_network(env["CLOUDFLARED_PROXY_CIDR"], strict=False)
    except ValueError as exc:
        fail(f"invalid deployment network value: {exc}")
    require(subnet.version == 4 and subnet.prefixlen >= 28, "support-session subnet must be a dedicated IPv4 /28 or smaller")
    require(portal_ip in subnet and api_ip in subnet and portal_ip != api_ip, "support service IPs must be distinct members of support-session subnet")
    require(portal_ip not in {subnet.network_address, subnet.broadcast_address}, "portal IP is not usable")
    require(api_ip not in {subnet.network_address, subnet.broadcast_address}, "API IP is not usable")
    require(cloud_cidr.version == 4 and cloud_cidr.prefixlen == 32, "Cloudflared trust must be its exact current IPv4 /32")
    require(not subnet.overlaps(cloud_cidr), "Cloudflared and API trust networks must not overlap")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", env["CLOUDFLARED_CONTAINER"]) is not None, "invalid Cloudflared container name")
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", env["CLOUDFLARED_NETWORK"]) is not None, "invalid Cloudflared network name")

    require(re.fullmatch(r"[A-Za-z0-9._-]{1,64}", env["MANIFEST_KEY_ID"]) is not None, "invalid manifest key ID")
    pin = decode_b64(env["MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL"], "manifest public key", urlsafe=True)
    require(len(env["MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL"]) == 87, "manifest public key pin must be 87 base64url characters")
    require(len(pin) == 65 and pin[0] == 4, "manifest public key must be a P-256 uncompressed X9.63 point")

    require(HEX64.fullmatch(env["WINDOWS_SIGNER_CERT_SHA256"]) is not None, "invalid Windows signer SHA-256 fingerprint")
    require(env["WINDOWS_SIGNER_CERT_SHA256"] != "0" * 64, "Windows signer fingerprint is a placeholder")
    require(3 <= len(env["WINDOWS_SIGNER_SUBJECT"]) <= 200, "invalid Windows signer subject")
    validate_team_id(env["APPLE_INSTALLER_TEAM_ID"], "Apple installer Team ID")
    validate_team_id(env["RUSTDESK_MACOS_TEAM_IDENTIFIER"], "RustDesk macOS Team ID")
    require(env["APPLE_INSTALLER_TEAM_ID"] != env["RUSTDESK_MACOS_TEAM_IDENTIFIER"], "Sinbar and RustDesk Team IDs unexpectedly match; independently verify both")
    return env


def validate_session_env(path: pathlib.Path, deploy: dict[str, str]) -> dict[str, str]:
    env = parse_env(path, "session API environment")
    required = {
        "SUPPORT_PUBLIC_ORIGIN", "DATABASE_PATH", "ARTIFACT_MANIFEST_PATH",
        "MANIFEST_SIGNING_KEY_FILE", "MANIFEST_KEY_ID", "SESSION_HMAC_KEY_BASE64",
        "AUDIT_HMAC_KEY_BASE64", "TRUSTED_PROXY_CIDRS", "SESSION_TTL_SECONDS",
        "MANIFEST_TTL_SECONDS", "CREATE_RATE_LIMIT", "CONSUME_RATE_LIMIT",
        "RATE_WINDOW_SECONDS", "MAX_BODY_BYTES", "RUSTDESK_WINDOWS_X86_64_SHA256",
        "RUSTDESK_WINDOWS_ARM64_SHA256", "RUSTDESK_MACOS_X86_64_SHA256",
        "RUSTDESK_MACOS_ARM64_SHA256", "RUSTDESK_MACOS_TEAM_IDENTIFIER",
    }
    require(set(env) == required, f"session API environment fields differ: missing={sorted(required-set(env))}, extra={sorted(set(env)-required)}")
    require(env["SUPPORT_PUBLIC_ORIGIN"] == ORIGIN, "support public origin mismatch")
    require(env["DATABASE_PATH"] == "/data/sessions.sqlite3", "database path mismatch")
    require(env["ARTIFACT_MANIFEST_PATH"] == "/run/config/artifacts.json", "artifact manifest path mismatch")
    require(env["MANIFEST_SIGNING_KEY_FILE"] == "/run/secrets/support-manifest-p256.pem", "signing key mount path mismatch")
    require(env["MANIFEST_KEY_ID"] == deploy["MANIFEST_KEY_ID"], "manifest key IDs do not match")
    require(env["SESSION_TTL_SECONDS"] == "120", "session TTL must be exactly 120 seconds")
    require(60 <= int(env["MANIFEST_TTL_SECONDS"]) <= 600, "manifest TTL is out of range")
    require(env["TRUSTED_PROXY_CIDRS"] == f'{deploy["SUPPORT_PORTAL_SESSION_IP"]}/32', "API must trust only the portal Nginx /32")
    first = decode_b64(env["SESSION_HMAC_KEY_BASE64"], "session HMAC key")
    second = decode_b64(env["AUDIT_HMAC_KEY_BASE64"], "audit HMAC key")
    require(len(first) >= 32 and len(second) >= 32, "HMAC keys must decode to at least 32 bytes")
    require(first != second, "session and audit HMAC keys must be independent")
    require(len(set(first)) > 8 and len(set(second)) > 8, "HMAC key material is implausibly weak")
    hash_names = {
        ("windows", "x86_64"): "RUSTDESK_WINDOWS_X86_64_SHA256",
        ("windows", "arm64"): "RUSTDESK_WINDOWS_ARM64_SHA256",
        ("macos", "x86_64"): "RUSTDESK_MACOS_X86_64_SHA256",
        ("macos", "arm64"): "RUSTDESK_MACOS_ARM64_SHA256",
    }
    for target, name in hash_names.items():
        require(env[name] == RUSTDESK[target][1], f"unexpected recorded RustDesk digest for {target}")
    require(env["RUSTDESK_MACOS_TEAM_IDENTIFIER"] == deploy["RUSTDESK_MACOS_TEAM_IDENTIFIER"], "RustDesk Team IDs do not match")
    return env


def validate_private_key(path: pathlib.Path, expected_pin: str) -> None:
    privileged_file(path, "manifest private key", {0o400})
    result = subprocess.run(
        ["openssl", "pkey", "-in", str(path), "-pubout", "-outform", "DER"],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    require(result.returncode == 0, "manifest private key is not readable by OpenSSL")
    pin = decode_b64(expected_pin, "manifest public key", urlsafe=True)
    require(result.stdout.endswith(pin), "manifest public pin does not match the production private key")
    details = subprocess.run(
        ["openssl", "pkey", "-in", str(path), "-text_pub", "-noout"],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    require(details.returncode == 0 and ("prime256v1" in details.stdout or "P-256" in details.stdout), "manifest key is not ECDSA P-256")


def parse_sums(path: pathlib.Path) -> dict[str, str]:
    regular_file(path, "release checksum list")
    result: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
        require(match is not None, f"invalid checksum line {number}")
        require(match.group(2) not in result, f"duplicate checksum entry {match.group(2)}")
        result[match.group(2)] = match.group(1)
    return result


def validate_receipt(path: pathlib.Path, platform: str, artifact: pathlib.Path, deploy: dict[str, str]) -> None:
    receipt = load_json(path, f"{platform} native verification receipt")
    common = {"schemaVersion", "platform", "artifact", "sha256", "verifiedAt"}
    if platform == "windows":
        expected = common | {"authenticodeStatus", "signerCertificateSha256", "signerSubject", "timestampVerified"}
        require(set(receipt) == expected, "Windows verification receipt schema mismatch")
        require(receipt["authenticodeStatus"] == "Valid" and receipt["timestampVerified"] is True, "Windows signature or RFC3161 timestamp was not validated")
        require(receipt["signerCertificateSha256"] == deploy["WINDOWS_SIGNER_CERT_SHA256"], "Windows signer fingerprint mismatch")
        require(deploy["WINDOWS_SIGNER_SUBJECT"].casefold() in str(receipt["signerSubject"]).casefold(), "Windows signer subject mismatch")
    else:
        expected = common | {"gatekeeperAccepted", "installerTeamIdentifier", "notarizationStapled", "pkgSignatureValid", "signerSubject"}
        require(set(receipt) == expected, "macOS verification receipt schema mismatch")
        require(receipt["gatekeeperAccepted"] is True and receipt["notarizationStapled"] is True and receipt["pkgSignatureValid"] is True, "macOS signing, Gatekeeper, or notarization validation failed")
        require(receipt["installerTeamIdentifier"] == deploy["APPLE_INSTALLER_TEAM_ID"], "macOS installer Team ID mismatch")
    require(receipt["schemaVersion"] == 1 and receipt["platform"] == platform, f"{platform} receipt identity mismatch")
    require(receipt["artifact"] == artifact.name and receipt["sha256"] == sha256(artifact), f"{platform} receipt does not bind the exact installer")
    validate_timestamp(receipt["verifiedAt"], f"{platform} verifiedAt")


def validate_release(release_dir: pathlib.Path, deploy: dict[str, str]) -> dict[str, Any]:
    require(release_dir.is_dir() and not release_dir.is_symlink(), "release directory is invalid")
    manifest_path = release_dir / "release-manifest.json"
    sums_path = release_dir / "SHA256SUMS.txt"
    manifest = load_json(manifest_path, "release manifest")
    require(set(manifest) == {"schemaVersion", "release", "assets"} and manifest["schemaVersion"] == 1, "release manifest schema mismatch")
    release = manifest["release"]
    require(isinstance(release, dict) and set(release) == {"commit", "createdAt", "tag", "version"}, "release metadata schema mismatch")
    require(release["version"] == VERSION and release["tag"] == f"v{VERSION}", "release version mismatch")
    require(re.fullmatch(r"[0-9a-f]{40}", str(release["commit"])) is not None, "release commit is not a full Git object ID")
    require(release["commit"] == deploy["REVIEWED_SOURCE_COMMIT"], "release manifest commit does not match reviewed source commit")
    validate_timestamp(release["createdAt"], "release createdAt")
    assets = manifest["assets"]
    require(isinstance(assets, list) and len(assets) == 2, "release must contain exactly two installer assets")
    rows = {item.get("platform"): item for item in assets if isinstance(item, dict)}
    require(set(rows) == set(INSTALLERS), "release installer platforms mismatch")
    sums = parse_sums(sums_path)
    require(set(sums) == {WINDOWS_INSTALLER, MACOS_INSTALLER, "release-manifest.json"}, "release checksum set must contain exactly both installers and the manifest")
    require(sums["release-manifest.json"] == sha256(manifest_path), "release manifest checksum mismatch")
    for platform, name in INSTALLERS.items():
        path = regular_file(release_dir / name, f"{platform} signed installer", 1024 * 1024)
        row = rows[platform]
        require(set(row) == {"bytes", "downloadPath", "name", "platform", "sha256"}, f"{platform} asset schema mismatch")
        require(row["name"] == name and row["bytes"] == path.stat().st_size, f"{platform} release metadata mismatch")
        require(row["downloadPath"] == f"/download/v{VERSION}/{platform}/{name}", f"{platform} download path mismatch")
        require(row["sha256"] == sha256(path) == sums[name], f"{platform} installer checksum mismatch")
    require((release_dir / WINDOWS_INSTALLER).read_bytes()[:2] == b"MZ", "Windows installer is not a PE file")
    require((release_dir / MACOS_INSTALLER).read_bytes()[:4] == b"xar!", "macOS installer is not a flat PKG")
    validate_receipt(release_dir / "windows-native-verification.json", "windows", release_dir / WINDOWS_INSTALLER, deploy)
    validate_receipt(release_dir / "macos-native-verification.json", "macos", release_dir / MACOS_INSTALLER, deploy)
    validate_attended_acceptance(release_dir / "attended-acceptance.json", release_dir, deploy)

    tool = shutil.which("osslsigncode")
    require(tool is not None, "osslsigncode is required for independent NOC Authenticode verification")
    verification = subprocess.run(
        [tool, "verify", "-in", str(release_dir / WINDOWS_INSTALLER), "-require-leaf-hash", f'sha256:{deploy["WINDOWS_SIGNER_CERT_SHA256"]}'],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    require(verification.returncode == 0, "NOC Authenticode verification failed")
    require("Signature verification: ok" in verification.stdout, "osslsigncode did not report a valid Windows signature")
    return manifest


def validate_attended_acceptance(path: pathlib.Path, release_dir: pathlib.Path, deploy: dict[str, str]) -> None:
    receipt = load_json(path, "attended-support acceptance receipt")
    expected = {
        "schemaVersion", "releaseVersion", "sourceCommit", "reviewedAt",
        "reviewedBy", "reviewTicket", "supportMode", "manifestKeyId",
        "manifestPublicKeyPinSha256", "installerSha256", "cleanDeviceTests",
        "preconfiguredHostTests",
    }
    require(set(receipt) == expected, "attended-support acceptance receipt schema mismatch")
    require(receipt["schemaVersion"] == 1 and receipt["releaseVersion"] == VERSION, "attended acceptance version mismatch")
    require(receipt["sourceCommit"] == deploy["REVIEWED_SOURCE_COMMIT"], "attended acceptance source commit mismatch")
    require(receipt["supportMode"] == "attended", "acceptance did not approve attended-only support")
    require(receipt["manifestKeyId"] == deploy["MANIFEST_KEY_ID"], "acceptance manifest key ID mismatch")
    pin_digest = hashlib.sha256(deploy["MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL"].encode("ascii")).hexdigest()
    require(receipt["manifestPublicKeyPinSha256"] == pin_digest, "acceptance manifest public key pin mismatch")
    reviewers = receipt["reviewedBy"]
    require(isinstance(reviewers, list) and len(reviewers) >= 2 and len(set(reviewers)) == len(reviewers), "attended acceptance requires two distinct named reviewers")
    require(all(isinstance(item, str) and 3 <= len(item) <= 120 for item in reviewers), "invalid acceptance reviewer")
    require(isinstance(receipt["reviewTicket"], str) and 3 <= len(receipt["reviewTicket"]) <= 120, "acceptance review ticket is required")
    validate_timestamp(receipt["reviewedAt"], "attended acceptance reviewedAt")
    expected_hashes = {
        "windows": sha256(release_dir / WINDOWS_INSTALLER),
        "macos": sha256(release_dir / MACOS_INSTALLER),
    }
    require(receipt["installerSha256"] == expected_hashes, "attended acceptance does not bind both exact installers")
    tests = receipt["cleanDeviceTests"]
    require(isinstance(tests, dict) and set(tests) == {"windows", "macos"}, "both clean-device acceptance test sets are required")
    required_checks = {
        "firstInstallTrustPromptObserved", "returningProtocolLaunchSucceeded",
        "noPermanentPasswordConfigured", "remoteControlRequiresCustomerAcceptance",
        "assistantClosedAfterLaunch", "temporaryFilesRemoved",
    }
    for platform in ("windows", "macos"):
        row = tests[platform]
        require(isinstance(row, dict) and set(row) == required_checks, f"{platform} acceptance checks are incomplete")
        require(all(value is True for value in row.values()), f"{platform} attended-only acceptance has a failed or unreviewed check")
    preconfigured = receipt["preconfiguredHostTests"]
    require(isinstance(preconfigured, dict) and set(preconfigured) == {"windows", "macos"}, "both preconfigured-host test sets are required")
    preconfigured_checks = {
        "existingRustDeskServiceDetected",
        "storedPermanentPasswordRejectedOrRemoved",
        "unattendedAccessDisabled",
        "customerAttendedControlVerified",
        "launchAbortedIfRemediationFailed",
    }
    for platform in ("windows", "macos"):
        row = preconfigured[platform]
        require(isinstance(row, dict) and set(row) == preconfigured_checks, f"{platform} preconfigured-host checks are incomplete")
        require(all(value is True for value in row.values()), f"{platform} preconfigured-host attended-only enforcement failed or is unreviewed")


def validate_rustdesk(root: pathlib.Path) -> dict[tuple[str, str], pathlib.Path]:
    require(root.is_dir() and not root.is_symlink(), "RustDesk input directory is invalid")
    result: dict[tuple[str, str], pathlib.Path] = {}
    for target, (name, digest) in RUSTDESK.items():
        path = regular_file(root / target[0] / name, f"RustDesk {target}", 1024 * 1024)
        require(sha256(path) == digest, f"RustDesk {target} SHA-256 mismatch")
        result[target] = path
    return result


def validate_sources(project_root: pathlib.Path, deploy: dict[str, str]) -> dict[str, pathlib.Path]:
    required = {
        "index": project_root / "portal/index.html",
        "app": project_root / "portal/assets/app.js",
        "styles": project_root / "portal/assets/styles.css",
        "logo": project_root / "portal/assets/sinbar-primary-logo.jpg",
        "portal_manifest": project_root / "portal/download/manifest.json",
        "nginx": project_root / "deploy/nginx.conf",
        "overlay": project_root / "deploy/compose.assistant.yaml",
        "server_app": project_root / "server/app/__init__.py",
        "server_template": project_root / "server/config/artifacts.template.json",
    }
    for label, path in required.items():
        regular_file(path, label)
    portal = load_json(required["portal_manifest"], "portal manifest")
    require(portal.get("portalVersion") == VERSION, "portal source version mismatch")
    require(portal.get("supportMode") == "attended" and portal.get("permanentPasswordConfigured") is False, "portal is not attended-only")
    nginx = required["nginx"].read_text(encoding="utf-8")
    require(nginx.count("__CLOUDFLARED_PROXY_CIDR__") == 1, "Nginx Cloudflared trust placeholder missing or duplicated")
    require("access_log off" in nginx and "/api/v1/support/sessions/consume" in nginx, "Nginx API token logging protection is missing")
    git = shutil.which("git")
    require(git is not None, "git is required to bind deployment source to the release commit")
    revision = subprocess.run([git, "-C", str(project_root), "rev-parse", "HEAD"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    require(revision.returncode == 0, "project root must be a reviewed Git checkout; an unversioned ZIP cannot be deployed")
    require(revision.stdout.strip() == deploy["REVIEWED_SOURCE_COMMIT"], "current project Git commit does not match reviewed source/release commit")
    dirty = subprocess.run([git, "-C", str(project_root), "status", "--porcelain", "--untracked-files=no"], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    require(dirty.returncode == 0 and dirty.stdout.strip() == "", "tracked project files are modified; deploy the exact reviewed commit")
    return required


def artifacts_document(team_id: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for (platform, architecture), (name, digest) in RUSTDESK.items():
        suffix = "aarch64" if architecture == "arm64" else architecture
        row: dict[str, Any] = {
            "platform": platform,
            "architecture": architecture,
            "version": "1.4.9",
            "url": f"{ORIGIN}/download/vendor/rustdesk/1.4.9/{platform}/rustdesk-1.4.9-{suffix}.{('msi' if platform == 'windows' else 'dmg')}",
            "sha256": digest,
            "kind": "msi" if platform == "windows" else "dmg",
        }
        if platform == "windows":
            row["publisherSubjectContains"] = "PURSLANE"
        else:
            row["bundleIdentifier"] = "com.carriez.rustdesk"
            row["teamIdentifier"] = team_id
        rows.append(row)
    return {"schemaVersion": 1, "action": "ensure-and-launch-rustdesk", "attended": True, "artifacts": rows}


def copy_regular(source: pathlib.Path, destination: pathlib.Path, mode: int = 0o644) -> None:
    regular_file(source, f"source {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(mode)


def stage(args: argparse.Namespace, deploy: dict[str, str], release_manifest: dict[str, Any], rustdesk: dict[tuple[str, str], pathlib.Path], sources: dict[str, pathlib.Path]) -> None:
    destination = args.stage_root.resolve()
    require(not destination.exists(), f"stage destination already exists: {destination}")
    destination.mkdir(parents=True, mode=0o755)
    site = destination / "site"
    copy_regular(sources["index"], site / "index.html")
    copy_regular(sources["app"], site / "assets/app.js")
    copy_regular(sources["styles"], site / "assets/styles.css")
    copy_regular(sources["logo"], site / "assets/sinbar-primary-logo.jpg")

    release_dir = args.release_dir.resolve()
    for platform, name in INSTALLERS.items():
        copy_regular(release_dir / name, site / f"download/v{VERSION}/{platform}/{name}")
    copy_regular(release_dir / "release-manifest.json", site / f"download/v{VERSION}/release-manifest.json")
    copy_regular(release_dir / "SHA256SUMS.txt", destination / "release-evidence/SHA256SUMS.txt")
    copy_regular(release_dir / "windows-native-verification.json", destination / "release-evidence/windows-native-verification.json")
    copy_regular(release_dir / "macos-native-verification.json", destination / "release-evidence/macos-native-verification.json")
    copy_regular(release_dir / "attended-acceptance.json", destination / "release-evidence/attended-acceptance.json")
    for target, path in rustdesk.items():
        copy_regular(path, site / f"download/vendor/rustdesk/1.4.9/{target[0]}/{path.name}")

    portal_manifest = load_json(sources["portal_manifest"], "portal manifest")
    release_rows = {row["platform"]: row for row in release_manifest["assets"]}
    for item in portal_manifest["installers"]:
        row = release_rows[item["platform"]]
        item["publicationStatus"] = "published"
        item["bytes"] = row["bytes"]
        item["sha256"] = row["sha256"]
    (site / "download").mkdir(parents=True, exist_ok=True)
    (site / "download/manifest.json").write_text(json.dumps(portal_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (site / "download/manifest.json").chmod(0o644)

    public_files: list[pathlib.Path] = []
    for platform, name in INSTALLERS.items():
        public_files.append(site / f"download/v{VERSION}/{platform}/{name}")
    for target, path in rustdesk.items():
        public_files.append(site / f"download/vendor/rustdesk/1.4.9/{target[0]}/{path.name}")
    sums = [f"{sha256(path)}  {path.relative_to(site / 'download').as_posix()}" for path in sorted(public_files)]
    (site / "download/SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="ascii")
    (site / "download/SHA256SUMS.txt").chmod(0o644)

    api = destination / "support-session-api"
    shutil.copytree(
        args.project_root.resolve() / "server/app", api / "app",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("wsgi.py", "gunicorn.conf.py", "requirements.txt", "requirements.lock"):
        copy_regular(args.project_root.resolve() / "server" / name, api / name)
    (api / "config").mkdir(parents=True, exist_ok=True)
    (api / "config/artifacts.json").write_text(json.dumps(artifacts_document(deploy["RUSTDESK_MACOS_TEAM_IDENTIFIER"]), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (api / "config/artifacts.json").chmod(0o644)

    rendered_nginx = sources["nginx"].read_text(encoding="utf-8").replace("__CLOUDFLARED_PROXY_CIDR__", deploy["CLOUDFLARED_PROXY_CIDR"])
    require(not PLACEHOLDER.search(rendered_nginx), "rendered Nginx still contains a placeholder")
    (destination / "nginx.conf").write_text(rendered_nginx, encoding="utf-8")
    (destination / "nginx.conf").chmod(0o644)
    copy_regular(sources["overlay"], destination / "compose.assistant.yaml")

    provenance = {
        "schemaVersion": 1,
        "releaseVersion": VERSION,
        "releaseCommit": release_manifest["release"]["commit"],
        "releaseManifestSha256": sha256(release_dir / "release-manifest.json"),
        "apiImage": deploy["SUPPORT_API_IMAGE"],
        "manifestKeyId": deploy["MANIFEST_KEY_ID"],
        "manifestPublicKeyPinSha256": hashlib.sha256(deploy["MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL"].encode("ascii")).hexdigest(),
        "rustDeskVersion": "1.4.9",
    }
    (destination / "DEPLOYED_RELEASE.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (destination / "DEPLOYED_RELEASE.json").chmod(0o644)

    for path in destination.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".json", ".yaml", ".yml", ".conf", ".py", ".txt"}:
            text = path.read_text(encoding="utf-8")
            require(not PLACEHOLDER.search(text), f"staged text still contains a placeholder: {path.relative_to(destination)}")
    print(f"PASS: staged complete production release at {destination}")


def validate_all(args: argparse.Namespace) -> tuple[dict[str, str], dict[str, Any], dict[tuple[str, str], pathlib.Path], dict[str, pathlib.Path]]:
    deploy = validate_deployment_env(args.deployment_env.resolve())
    validate_session_env(args.session_env.resolve(), deploy)
    validate_private_key(args.private_key.resolve(), deploy["MANIFEST_P256_PUBLIC_KEY_X963_BASE64URL"])
    release = validate_release(args.release_dir.resolve(), deploy)
    rustdesk = validate_rustdesk(args.rustdesk_dir.resolve())
    sources = validate_sources(args.project_root.resolve(), deploy)
    print("PASS: no production placeholders remain in trusted configuration")
    print("PASS: immutable API image digest, P-256 key pin, Team IDs, and native receipts validated")
    print("PASS: both signed assistant installers and all four RustDesk SHA-256 pins validated")
    return deploy, release, rustdesk, sources


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("validate", "stage"))
    result.add_argument("--project-root", required=True, type=pathlib.Path)
    result.add_argument("--release-dir", required=True, type=pathlib.Path)
    result.add_argument("--rustdesk-dir", required=True, type=pathlib.Path)
    result.add_argument("--deployment-env", required=True, type=pathlib.Path)
    result.add_argument("--session-env", required=True, type=pathlib.Path)
    result.add_argument("--private-key", default=KEY_FILE, type=pathlib.Path)
    result.add_argument("--stage-root", type=pathlib.Path)
    return result


def main() -> int:
    args = parser().parse_args()
    deploy, release, rustdesk, sources = validate_all(args)
    if args.command == "stage":
        require(args.stage_root is not None, "--stage-root is required for stage")
        stage(args, deploy, release, rustdesk, sources)
    elif args.stage_root is not None:
        fail("--stage-root is valid only with stage")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
