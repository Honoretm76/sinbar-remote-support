from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import stat
from typing import Any, Iterable

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from .config import ConfigurationError, Settings


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class ManifestSigner:
    def __init__(self, private_key: ec.EllipticCurvePrivateKey, key_id: str):
        if not isinstance(private_key.curve, ec.SECP256R1):
            raise ConfigurationError("Manifest signing key must use ECDSA P-256")
        self._private_key = private_key
        self._key_id = key_id

    @classmethod
    def load(cls, settings: Settings) -> "ManifestSigner":
        try:
            mode = stat.S_IMODE(settings.manifest_signing_key_path.stat().st_mode)
            pem = settings.manifest_signing_key_path.read_bytes()
        except OSError as exc:
            raise ConfigurationError("Manifest signing key cannot be read") from exc
        if mode & 0o077:
            raise ConfigurationError("Manifest signing key must not be group/world accessible")
        try:
            key = serialization.load_pem_private_key(pem, password=None)
        except (ValueError, TypeError) as exc:
            raise ConfigurationError("Manifest signing key is not valid unencrypted PEM") from exc
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ConfigurationError("Manifest signing key must be an EC private key")
        return cls(key, settings.manifest_key_id)

    def sign(self, manifest: dict[str, Any]) -> dict[str, str]:
        payload_bytes = json.dumps(
            manifest,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        der_signature = self._private_key.sign(payload_bytes, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_signature)
        p1363_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return {
            "keyId": self._key_id,
            "payload": base64url(payload_bytes),
            "signature": base64url(p1363_signature),
        }

    def public_key_pin(self) -> str:
        point = self._private_key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        return base64url(point)


def client_actor_key(
    remote_address: str,
    forwarded_for: str | None,
    trusted_proxy_cidrs: Iterable[ipaddress._BaseNetwork],
    audit_key: bytes,
) -> str:
    address = _parse_ip(remote_address)
    if address is not None and any(address in network for network in trusted_proxy_cidrs):
        if forwarded_for:
            candidate = _parse_ip(forwarded_for.split(",", 1)[0].strip())
            if candidate is not None:
                address = candidate
    normalized = str(address) if address is not None else "unknown"
    return hmac.new(audit_key, b"client-ip-v1:" + normalized.encode(), hashlib.sha256).hexdigest()[:24]


def token_digest(token: str, key: bytes) -> bytes:
    return hmac.new(key, b"session-token-v1:" + token.encode("ascii"), hashlib.sha256).digest()


def session_reference(digest: bytes) -> str:
    return digest.hex()[:16]


def _parse_ip(value: str) -> ipaddress._BaseAddress | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None
