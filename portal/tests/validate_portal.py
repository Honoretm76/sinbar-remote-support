#!/usr/bin/env python3
"""Static safety checks for the vendor-signed Sinbar support portal."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
APP = ROOT / "assets/app.js"
STYLES = ROOT / "assets/styles.css"
LOGO = ROOT / "assets/sinbar-primary-logo.jpg"
MANIFEST = ROOT / "download/manifest.json"
CHECKSUMS = ROOT / "download/SHA256SUMS.txt"
NGINX = ROOT.parent / "deploy/nginx.conf"
DEPLOYER = ROOT.parent / "deploy/sinbar-support-deploy"

LOGO_SHA256 = "984ed311238503646099debb13ab82369b795b8e289c4a7b6a98de3f4bfed9ed"
PUBLIC_KEY_SHA256 = "2f9f17cd56abc92fe53c75aafb97184841f5c4030d39f06164c47f1e0b2cd6aa"
WINDOWS_PUBLISHER_PIN = "85a1152301ba31d625ce06294584deaee9cf32c2dd7bdfdf72821499cd745116"
ROUTES = {
    ("windows", "x86_64"): (
        "/download/windows/x64",
        "eaedeb0088e687bf46f7c46a9c6ea5493ce51f3134dfd6acbedb47b5b9136274",
    ),
    ("windows", "arm64"): (
        "/download/windows/arm64",
        "c717bf52fdd601c58419e46c503176dd87187d174ebf8b3b5854ca381e8e9145",
    ),
    ("macos", "arm64"): (
        "/download/macos/apple-silicon",
        "f7935597b247d42c8f2a2ed71176a9f5868018cd9e1a33b8096418a668c8caf0",
    ),
    ("macos", "x86_64"): (
        "/download/macos/intel",
        "fa1129a0635019f9c5841937942cc2b08be028a192f47c009edde7e53812904e",
    ),
}


class PortalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.inline_scripts: list[str] = []
        self.inline_styles: list[str] = []
        self.script_sources: list[str] = []
        self.stylesheets: list[str] = []
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.csp = ""
        self._inside_script = False
        self._inside_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        for name, _value in attrs:
            require(not name.lower().startswith("on"), f"Inline event handler found: {name}")
            require(name.lower() != "style", "Inline style attribute found")
        if tag == "script":
            self._inside_script = True
            if values.get("src"):
                self.script_sources.append(str(values["src"]))
        if tag == "style":
            self._inside_style = True
        if tag == "link" and values.get("rel") == "stylesheet":
            self.stylesheets.append(str(values.get("href", "")))
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))
        if tag == "meta" and str(values.get("http-equiv", "")).lower() == "content-security-policy":
            self.csp = str(values.get("content", ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._inside_script = False
        if tag == "style":
            self._inside_style = False

    def handle_data(self, data: str) -> None:
        if self._inside_script and data.strip():
            self.inline_scripts.append(data)
        if self._inside_style and data.strip():
            self.inline_styles.append(data)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode_reversed_urlsafe(value: str) -> dict[str, str]:
    restored = value[::-1]
    restored += "=" * ((4 - len(restored) % 4) % 4)
    payload = base64.urlsafe_b64decode(restored)
    result = json.loads(payload)
    require(isinstance(result, dict), "RustDesk configuration is not an object")
    return result


def validate_configuration(javascript: str, nginx: str) -> None:
    export_match = re.search(r'var SERVER_CONFIG = "([A-Za-z0-9_=-]+)";', javascript)
    require(export_match is not None, "macOS exported configuration missing")
    exported = decode_reversed_urlsafe(export_match.group(1))
    require(set(exported) == {"api", "host", "key", "relay"}, "exported configuration fields mismatch")
    require(exported["host"] == "remote.sinbarconsultants.net", "exported host mismatch")
    require(exported["relay"] == "remote.sinbarconsultants.net", "exported relay mismatch")
    require(exported["api"] == "", "unexpected API server")
    require(len(exported["key"]) == 44, "public key length mismatch")
    require(hashlib.sha256(exported["key"].encode()).hexdigest() == PUBLIC_KEY_SHA256, "public key digest mismatch")

    filename_tokens = re.findall(r'-qs--([A-Za-z0-9_-]+)[.]exe\\?"', nginx)
    require(len(filename_tokens) == 2, "both configured Windows filenames are required")
    require(len(set(filename_tokens)) == 1, "Windows architectures use different configuration tokens")
    portable = decode_reversed_urlsafe(filename_tokens[0])
    require(portable == {
        "key": exported["key"],
        "host": exported["host"],
        "api": "",
        "relay": "",
    }, "Windows compact filename configuration mismatch")


def main() -> int:
    for path in (INDEX, APP, STYLES, MANIFEST, CHECKSUMS, NGINX, DEPLOYER):
        require(path.is_file(), f"Missing required file: {path}")
        require(path.stat().st_size > 0, f"Empty required file: {path}")

    html = INDEX.read_text(encoding="utf-8")
    javascript = APP.read_text(encoding="utf-8")
    css = STYLES.read_text(encoding="utf-8")
    nginx = NGINX.read_text(encoding="utf-8")
    deployer = DEPLOYER.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    checksums: dict[str, str] = {}
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        digest, relative_path = line.split(maxsplit=1)
        require(relative_path not in checksums, f"Duplicate checksum path: {relative_path}")
        checksums[relative_path] = digest

    parser = PortalParser()
    parser.feed(html)

    require(not parser.inline_scripts, "Inline JavaScript is not allowed")
    require(not parser.inline_styles, "Inline CSS is not allowed")
    require(parser.script_sources == ["/assets/app.js"], "Unexpected JavaScript source")
    require(parser.stylesheets == ["/assets/styles.css"], "Unexpected stylesheet source")
    require("'unsafe-inline'" not in parser.csp, "CSP must not allow inline code")
    require("script-src 'self'" in parser.csp, "CSP script-src must be self-only")
    require("connect-src 'none'" in parser.csp, "Portal must not call an API")
    require("object-src 'none'" in parser.csp, "CSP must disable plugins")

    required_ids = {
        "start-support",
        "launch-status",
        "assistant-dialog",
        "windows-x64",
        "windows-arm64",
        "macos-arm64",
        "macos-x64",
        "copy-config",
    }
    require(required_ids.issubset(parser.ids), "Required accessible controls are missing")

    for route, _digest in ROUTES.values():
        require(route in parser.links, f"Portal link missing: {route}")
        require(route in javascript, f"JavaScript allowlist missing: {route}")
        require(f"location = {route}" in nginx, f"Nginx exact route missing: {route}")

    require("Start Remote Support" in html, "Primary support action is missing")
    require("PURSLANE" in html, "Windows publisher disclosure is missing")
    require("one-time password" in html.lower(), "Attended password guidance is missing")
    require("navigator.clipboard.writeText(SERVER_CONFIG)" in javascript, "macOS configuration copy missing")
    require("window.location.assign(url)" in javascript, "customer-click download action missing")

    forbidden_javascript = (
        "fetch(",
        "sinbarsupport://",
        "eval(",
        "new Function",
        ".innerHTML",
        "document.write",
        "localStorage",
        "sessionStorage",
        "document.cookie",
        "console.log",
    )
    for forbidden in forbidden_javascript:
        require(forbidden not in javascript, f"Forbidden JavaScript primitive found: {forbidden}")

    require(manifest["schemaVersion"] == 3, "Unexpected manifest schema")
    require(manifest["portalVersion"] == "2.1.0", "Unexpected portal version")
    require(manifest["experience"] == "vendor-signed-rustdesk-download", "Unexpected portal experience")
    require(manifest["supportMode"] == "attended", "Portal must remain attended-only")
    require(manifest["permanentPasswordConfigured"] is False, "Permanent password must stay disabled")
    require(manifest["brand"]["logoSha256"] == LOGO_SHA256, "Manifest logo digest mismatch")
    if LOGO.is_file():
        require(sha256(LOGO) == LOGO_SHA256, "Sinbar logo digest changed")

    packages = {
        (item["platform"], item["architecture"]): item
        for item in manifest["packages"]
    }
    require(set(packages) == set(ROUTES), "Manifest package matrix mismatch")
    expected_checksums = {
        item["sourcePath"].removeprefix("/download/"): item["sha256"]
        for item in packages.values()
    }
    require(checksums == expected_checksums, "SHA256SUMS does not match the release manifest")
    for target, (route, digest) in ROUTES.items():
        item = packages[target]
        require(item["path"] == route, f"{target} path mismatch")
        require(item["sha256"] == digest, f"{target} SHA-256 mismatch")
        require(item["publicationStatus"] == "verified", f"{target} is not verified")
        if target[0] == "windows":
            require(item["signature"]["status"] == "Valid", f"{target} signature status mismatch")
            require(item["signature"]["publisherSubjectContains"] == "PURSLANE", f"{target} publisher mismatch")
            require(item["signature"]["publisherSpkiSha256"] == WINDOWS_PUBLISHER_PIN, f"{target} publisher pin mismatch")
        else:
            require(item["signature"]["requireCodeSignature"] is True, f"{target} code-sign requirement missing")
            require(item["signature"]["requireGatekeeperAcceptance"] is True, f"{target} Gatekeeper requirement missing")

    validate_configuration(javascript, nginx)

    combined = "\n".join((html, javascript, css, json.dumps(manifest), nginx, deployer))
    for marker in ("-----BEGIN PRIVATE KEY-----", "dop_v1_", "ghp_", "AKIA"):
        require(marker not in combined, f"Possible embedded secret found: {marker}")

    require(re.search(r"@media \(prefers-reduced-motion: reduce\)", css) is not None, "Reduced-motion support missing")
    require("Content-Disposition" in nginx and "-qs--" in nginx, "Configured Windows download filename missing")
    require("add_header_inherit" not in nginx, "Nginx config requires a newer add_header inheritance directive")
    require("access_log /dev/stdout;" in nginx, "Nginx access logging contract changed")
    require("frame-ancestors 'none'" in nginx, "Server CSP must block framing")
    require("location /" in nginx and "return 404;" in nginx, "Default deny route missing")
    require("restore_backup" in deployer, "Production deployer has no automatic rollback")
    require("verify_portal_endpoint \"$PUBLIC_BASE\"" in deployer, "Production deployer does not verify public routes")
    require("support-session-api" not in deployer, "Legacy session API remains in production deployer")
    require(".msi" not in deployer and ".pkg" not in deployer, "Legacy custom installer remains in production deployer")
    require("/api/v1/support/sessions" not in combined, "Paid-assistant session API remains active")
    require("Sinbar-Support-Assistant" not in combined, "Unavailable custom assistant remains referenced")

    print("PASS: four vendor download routes and exact hashes agree")
    print("PASS: Windows PURSLANE signature and publisher-key pins are declared")
    print("PASS: Windows compact filename configuration decodes to the approved Sinbar server")
    print("PASS: macOS exported configuration decodes to the approved Sinbar server")
    print("PASS: strict CSP portal has no API, custom protocol, inline code, or embedded secret")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, TypeError, ValueError, UnicodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
