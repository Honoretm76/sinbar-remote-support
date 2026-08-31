from __future__ import annotations

import base64
import ipaddress
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigurationError(RuntimeError):
    pass


SEMVER_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required")
    return value


def _decode_secret(name: str, minimum_bytes: int = 32) -> bytes:
    encoded = _required(name)
    try:
        value = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ConfigurationError(f"{name} must be standard base64") from exc
    if len(value) < minimum_bytes:
        raise ConfigurationError(f"{name} must decode to at least {minimum_bytes} bytes")
    return value


def _positive_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class Settings:
    public_origin: str
    support_hostname: str
    database_path: Path
    artifact_manifest_path: Path
    manifest_signing_key_path: Path
    manifest_key_id: str
    token_hash_key: bytes
    audit_key: bytes
    trusted_proxy_cidrs: tuple[ipaddress._BaseNetwork, ...]
    session_ttl_seconds: int = 120
    manifest_ttl_seconds: int = 300
    create_rate_limit: int = 10
    consume_rate_limit: int = 30
    rate_window_seconds: int = 60
    max_body_bytes: int = 4096
    version_pattern: re.Pattern[str] = SEMVER_PATTERN

    @classmethod
    def from_environment(cls) -> "Settings":
        public_origin = _required("SUPPORT_PUBLIC_ORIGIN").rstrip("/")
        parsed = urlparse(public_origin)
        try:
            origin_port = parsed.port
        except ValueError as exc:
            raise ConfigurationError("SUPPORT_PUBLIC_ORIGIN has an invalid port") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.path
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
            or origin_port is not None
        ):
            raise ConfigurationError("SUPPORT_PUBLIC_ORIGIN must be an HTTPS origin without a path")
        if public_origin != "https://support.sinbarconsultants.com":
            raise ConfigurationError(
                "SUPPORT_PUBLIC_ORIGIN must be https://support.sinbarconsultants.com"
            )

        proxy_networks: list[ipaddress._BaseNetwork] = []
        for item in os.environ.get("TRUSTED_PROXY_CIDRS", "127.0.0.1/32,::1/128").split(","):
            try:
                proxy_networks.append(ipaddress.ip_network(item.strip(), strict=False))
            except ValueError as exc:
                raise ConfigurationError(f"Invalid TRUSTED_PROXY_CIDRS entry: {item}") from exc

        key_id = _required("MANIFEST_KEY_ID")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", key_id):
            raise ConfigurationError("MANIFEST_KEY_ID contains invalid characters")

        return cls(
            public_origin=public_origin,
            support_hostname=parsed.hostname.lower(),
            database_path=Path(os.environ.get("DATABASE_PATH", "/data/sessions.sqlite3")),
            artifact_manifest_path=Path(
                os.environ.get("ARTIFACT_MANIFEST_PATH", "/run/config/artifacts.json")
            ),
            manifest_signing_key_path=Path(_required("MANIFEST_SIGNING_KEY_FILE")),
            manifest_key_id=key_id,
            token_hash_key=_decode_secret("SESSION_HMAC_KEY_BASE64"),
            audit_key=_decode_secret("AUDIT_HMAC_KEY_BASE64"),
            trusted_proxy_cidrs=tuple(proxy_networks),
            session_ttl_seconds=_positive_int("SESSION_TTL_SECONDS", 120, 120, 120),
            manifest_ttl_seconds=_positive_int("MANIFEST_TTL_SECONDS", 300, 60, 600),
            create_rate_limit=_positive_int("CREATE_RATE_LIMIT", 10, 1, 1000),
            consume_rate_limit=_positive_int("CONSUME_RATE_LIMIT", 30, 1, 2000),
            rate_window_seconds=_positive_int("RATE_WINDOW_SECONDS", 60, 10, 3600),
            max_body_bytes=_positive_int("MAX_BODY_BYTES", 4096, 512, 16384),
        )

    def installer_url(self, platform: str) -> str:
        paths = {
            "windows": "/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe",
            "macos": "/download/v2.0.0/macos/Sinbar-Support-Assistant.pkg",
        }
        try:
            return paths[platform]
        except KeyError as exc:
            raise ConfigurationError(f"Unsupported platform: {platform}") from exc
