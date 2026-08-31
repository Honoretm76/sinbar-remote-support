#!/usr/bin/env python3
"""Static safety and integration checks for the Sinbar portal."""

from __future__ import annotations

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
NGINX = ROOT / "nginx/intel-style-routes.conf"

SESSION_PATH = "/api/v1/support/sessions"
WINDOWS_PATH = "/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe"
MACOS_PATH = "/download/v2.0.0/macos/Sinbar-Support-Assistant.pkg"
LOGO_SHA256 = "984ed311238503646099debb13ab82369b795b8e289c4a7b6a98de3f4bfed9ed"


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

        for name, value in attrs:
            assert not name.lower().startswith("on"), f"Inline event handler found: {name}"
            assert name.lower() != "style", "Inline style attribute found"

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


def main() -> int:
    for path in (INDEX, APP, STYLES, LOGO, MANIFEST, NGINX):
        require(path.is_file(), f"Missing required file: {path.relative_to(ROOT)}")
        require(path.stat().st_size > 0, f"Empty required file: {path.relative_to(ROOT)}")

    html = INDEX.read_text(encoding="utf-8")
    javascript = APP.read_text(encoding="utf-8")
    css = STYLES.read_text(encoding="utf-8")
    nginx = NGINX.read_text(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    parser = PortalParser()
    parser.feed(html)

    require(not parser.inline_scripts, "Inline JavaScript is not allowed")
    require(not parser.inline_styles, "Inline CSS is not allowed")
    require(parser.script_sources == ["/assets/app.js"], "Unexpected JavaScript source")
    require(parser.stylesheets == ["/assets/styles.css"], "Unexpected stylesheet source")
    require("'unsafe-inline'" not in parser.csp, "CSP must not allow inline code")
    require("script-src 'self'" in parser.csp, "CSP script-src must be self-only")
    require("connect-src 'self'" in parser.csp, "CSP connect-src must be self-only")
    require("object-src 'none'" in parser.csp, "CSP must disable plugins")

    required_ids = {
        "start-support",
        "launch-status",
        "assistant-dialog",
        "windows-installer",
        "macos-installer",
        "try-again",
    }
    require(required_ids.issubset(parser.ids), "Required accessible controls are missing")
    require(WINDOWS_PATH in parser.links, "Windows fallback installer link is missing")
    require(MACOS_PATH in parser.links, "macOS fallback installer link is missing")
    require(".zip" not in html.lower(), "Legacy ZIP download remains in the portal")
    require("Start Remote Support" in html, "Primary support action is missing")
    require("First visit" in html and "Returning visit" in html, "Visit guidance is incomplete")

    require(sha256(LOGO) == LOGO_SHA256, "Sinbar logo digest changed")
    require(manifest["portalVersion"] == "2.0.0", "Unexpected portal version")
    require(manifest["supportMode"] == "attended", "Portal must remain attended-only")
    require(manifest["permanentPasswordConfigured"] is False, "Permanent password must stay disabled")
    require(manifest["brand"]["logoSha256"] == LOGO_SHA256, "Manifest logo digest mismatch")
    require(manifest["sessionContract"]["path"] == SESSION_PATH, "Session API path mismatch")
    require(manifest["sessionContract"]["method"] == "POST", "Session API must use POST")
    require(
        manifest["sessionContract"]["maximumLifetimeSeconds"] == 120,
        "Session lifetime must remain exactly 120 seconds",
    )

    installers = {item["platform"]: item for item in manifest["installers"]}
    require(installers["windows"]["path"] == WINDOWS_PATH, "Windows manifest path mismatch")
    require(installers["macos"]["path"] == MACOS_PATH, "macOS manifest path mismatch")
    require(
        all(item["publicationStatus"] == "artifact-required" for item in installers.values()),
        "Unsigned/unverified installer artifacts must not be marked published",
    )

    require(SESSION_PATH in javascript, "JavaScript session API path mismatch")
    require(WINDOWS_PATH in javascript, "JavaScript Windows installer path mismatch")
    require(MACOS_PATH in javascript, "JavaScript macOS installer path mismatch")
    require("sinbarsupport://start?token=" in javascript, "Canonical protocol builder missing")
    require("PROTOCOL_PATTERN" in javascript, "Protocol allowlist validation missing")
    require("payload.installerUrl !== expectedInstaller" in javascript, "Installer allowlist validation missing")
    require('mode: "same-origin"' in javascript, "Fetch must be same-origin")
    require('redirect: "error"' in javascript, "Fetch redirects must be rejected")
    require('cache: "no-store"' in javascript, "Session fetch must disable caching")
    require("TOKEN_PATTERN" in javascript, "Token validation missing")
    require("{43}" in javascript, "Launch token must be exactly 43 base64url characters")

    forbidden_javascript = (
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

    combined_text = "\n".join((html, javascript, css, json.dumps(manifest), nginx))
    secret_markers = (
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "dop_v1_",
        "ghp_",
        "AKIA",
    )
    for marker in secret_markers:
        require(marker not in combined_text, f"Possible embedded secret found: {marker}")

    require(re.search(r"@media \(prefers-reduced-motion: reduce\)", css) is not None, "Reduced-motion support missing")
    require(SESSION_PATH in nginx, "Nginx session route missing")
    require(WINDOWS_PATH in nginx, "Nginx Windows installer route missing")
    require(MACOS_PATH in nginx, "Nginx macOS installer route missing")
    require("access_log off;" in nginx, "Session access logging must be disabled")
    require('add_header Cache-Control "no-store, max-age=0" always;' in nginx, "Session no-store header missing")
    require("frame-ancestors 'none'" in nginx, "Server CSP must block framing")
    require("location /" in nginx and "return 404;" in nginx, "Default deny route missing")

    print("PASS: required portal files are present")
    print("PASS: strict CSP-compatible HTML has no inline code")
    print("PASS: session protocol and installer URLs are allowlisted")
    print("PASS: manifest, JavaScript, HTML, and Nginx routes agree")
    print("PASS: Sinbar logo SHA-256 verified")
    print("PASS: attended-workflow security messaging verified")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
