from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app import create_app
from app.config import Settings


@pytest.fixture()
def app(tmp_path: Path):
    private_key = ec.generate_private_key(ec.SECP256R1())
    key_path = tmp_path / "manifest-key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)

    digest = "a" * 64
    artifact_path = tmp_path / "artifacts.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "action": "ensure-and-launch-rustdesk",
                "attended": True,
                "artifacts": [
                    ({
                        "platform": platform,
                        "architecture": architecture,
                        "version": "1.4.9",
                        "url": (
                            "https://support.sinbarconsultants.com/download/test/"
                            f"rustdesk-{platform}-{architecture}.bin"
                        ),
                        "sha256": digest,
                        "kind": "msi",
                        "publisherSubjectContains": "PURSLANE",
                    } if platform == "windows" else {
                        "platform": platform,
                        "architecture": architecture,
                        "version": "1.4.9",
                        "url": (
                            "https://support.sinbarconsultants.com/download/test/"
                            f"rustdesk-{platform}-{architecture}.bin"
                        ),
                        "sha256": digest,
                        "kind": "dmg",
                        "bundleIdentifier": "com.carriez.rustdesk",
                        "teamIdentifier": "ABCDEFGHIJ",
                    })
                    for platform, architecture in (
                        ("windows", "x86_64"),
                        ("windows", "arm64"),
                        ("macos", "x86_64"),
                        ("macos", "arm64"),
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        public_origin="https://support.sinbarconsultants.com",
        support_hostname="support.sinbarconsultants.com",
        database_path=tmp_path / "sessions.sqlite3",
        artifact_manifest_path=artifact_path,
        manifest_signing_key_path=key_path,
        manifest_key_id="test-key-1",
        token_hash_key=b"T" * 32,
        audit_key=b"A" * 32,
        trusted_proxy_cidrs=(),
        create_rate_limit=100,
        consume_rate_limit=100,
    )
    application = create_app(settings)
    application.config.update(TESTING=True)
    application.testing_private_key = private_key
    return application


@pytest.fixture()
def client(app):
    return app.test_client()
