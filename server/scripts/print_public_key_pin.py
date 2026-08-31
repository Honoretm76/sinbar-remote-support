#!/usr/bin/env python3
from __future__ import annotations

import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


if len(sys.argv) != 2:
    raise SystemExit(f"Usage: {sys.argv[0]} PRIVATE_KEY.pem")

key = serialization.load_pem_private_key(Path(sys.argv[1]).read_bytes(), password=None)
if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
    raise SystemExit("Key must be ECDSA P-256")

point = key.public_key().public_bytes(
    serialization.Encoding.X962,
    serialization.PublicFormat.UncompressedPoint,
)
print(b64url(point))

