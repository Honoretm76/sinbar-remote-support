#!/usr/bin/env python3
"""Exercise the cross-platform ECDSA P-256 envelope byte contract."""

from __future__ import annotations

import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()
    x963 = b"\x04" + public_numbers.x.to_bytes(32, "big") + public_numbers.y.to_bytes(32, "big")

    payload = json.dumps(
        {
            "schemaVersion": 1,
            "sessionId": "ea2d83c4-5669-4b6a-9c62-2c2dccb1fcc9",
            "action": "ensure-and-launch-rustdesk",
            "attended": True,
            "platform": "windows",
            "architecture": "x86_64",
            "issuedAt": "2026-08-31T12:00:00Z",
            "expiresAt": "2026-08-31T12:04:00Z",
            "artifact": {
                "kind": "msi",
                "url": "https://support.sinbarconsultants.com/download/vendor/rustdesk/1.4.9/windows/rustdesk-1.4.9-x86_64.msi",
                "sha256": "c87d2f4cef2a5acd6003b6507dcfbf5d5168a256db082cd90b54d35193224aaa",
                "version": "1.4.9",
                "publisherSubjectContains": "PURSLANE",
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")

    der_signature = private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_signature)
    p1363_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    assert len(x963) == 65 and x963[0] == 4
    assert len(b64url(x963)) == 87
    assert len(p1363_signature) == 64
    assert len(b64url(p1363_signature)) == 86

    restored_der = encode_dss_signature(
        int.from_bytes(p1363_signature[:32], "big"),
        int.from_bytes(p1363_signature[32:], "big"),
    )
    private_key.public_key().verify(restored_der, payload, ec.ECDSA(hashes.SHA256()))

    try:
        private_key.public_key().verify(
            restored_der,
            payload + b" ",
            ec.ECDSA(hashes.SHA256()),
        )
    except InvalidSignature:
        pass
    else:
        raise AssertionError("tampered payload unexpectedly verified")

    envelope = {
        "keyId": "sinbar-support-manifest-p256-v1",
        "payload": b64url(payload),
        "signature": b64url(p1363_signature),
    }
    assert set(envelope) == {"keyId", "payload", "signature"}

    print("PASS: ECDSA P-256/SHA-256 envelope contract")
    print("PASS: 65-byte X9.63 public key and 64-byte IEEE-P1363 signature")
    print("PASS: signature verification rejects a modified payload")


if __name__ == "__main__":
    main()
