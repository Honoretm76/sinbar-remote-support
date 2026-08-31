from __future__ import annotations

import base64
import json
import sqlite3
import threading
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature


ORIGIN = "https://support.sinbarconsultants.com"


def decode64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue(client, platform="windows", architecture="unknown"):
    return client.post(
        "/api/v1/support/sessions",
        json={"platform": platform, "architecture": architecture},
        headers={"Origin": ORIGIN},
    )


def token_from(response) -> str:
    return response.get_json()["protocolUrl"].split("token=", 1)[1]


def test_create_contract_and_exact_installer(client):
    response = issue(client)
    assert response.status_code == 201
    assert set(response.get_json()) == {"protocolUrl", "expiresAt", "installerUrl"}
    assert response.get_json()["protocolUrl"].startswith("sinbarsupport://start?token=")
    assert len(token_from(response)) == 43
    assert response.get_json()["installerUrl"] == (
        "/download/v2.0.0/windows/Sinbar-Support-Assistant-Setup.exe"
    )
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert response.headers["Cache-Control"].startswith("no-store")


def test_macos_installer_contract(client):
    response = issue(client, "macos", "arm64")
    assert response.status_code == 201
    assert response.get_json()["installerUrl"].endswith(
        "/download/v2.0.0/macos/Sinbar-Support-Assistant.pkg"
    )


def test_consume_once_and_verify_p1363_signature(app, client):
    token = token_from(issue(client))
    body = {
        "token": token,
        "platform": "windows",
        "architecture": "x86_64",
        "assistantVersion": "2.0.0",
    }
    response = client.post("/api/v1/support/sessions/consume", json=body)
    assert response.status_code == 200
    envelope = response.get_json()
    assert set(envelope) == {"keyId", "payload", "signature"}
    assert envelope["keyId"] == "test-key-1"

    payload_bytes = decode64(envelope["payload"])
    signature = decode64(envelope["signature"])
    assert len(signature) == 64
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")
    app.testing_private_key.public_key().verify(
        encode_dss_signature(r, s), payload_bytes, ec.ECDSA(hashes.SHA256())
    )
    manifest = json.loads(payload_bytes)
    assert manifest["action"] == "ensure-and-launch-rustdesk"
    assert manifest["attended"] is True
    assert set(manifest) == {
        "schemaVersion",
        "sessionId",
        "action",
        "attended",
        "platform",
        "architecture",
        "issuedAt",
        "expiresAt",
        "artifact",
    }
    assert manifest["platform"] == "windows"
    assert manifest["architecture"] == "x86_64"
    assert set(manifest["artifact"]) == {
        "kind",
        "url",
        "sha256",
        "version",
        "publisherSubjectContains",
    }
    assert manifest["artifact"]["kind"] == "msi"
    assert manifest["artifact"]["publisherSubjectContains"] == "PURSLANE"
    assert manifest["artifact"]["sha256"] == "a" * 64
    assert manifest["issuedAt"].endswith("Z")
    assert manifest["expiresAt"].endswith("Z")

    replay = client.post("/api/v1/support/sessions/consume", json=body)
    assert replay.status_code == 410


def test_token_is_hashed_at_rest(app, client):
    token = token_from(issue(client))
    database: Path = app.extensions["support_settings"].database_path
    connection = sqlite3.connect(database)
    stored = connection.execute("SELECT token_hash FROM support_sessions").fetchone()[0]
    connection.close()
    assert token.encode() not in bytes(stored)
    assert len(bytes(stored)) == 32


def test_binding_mismatch_does_not_consume(client):
    token = token_from(issue(client, "windows", "x86_64"))
    wrong = client.post(
        "/api/v1/support/sessions/consume",
        json={
            "token": token,
            "platform": "windows",
            "architecture": "arm64",
            "assistantVersion": "2.0.0",
        },
    )
    assert wrong.status_code == 409
    correct = client.post(
        "/api/v1/support/sessions/consume",
        json={
            "token": token,
            "platform": "windows",
            "architecture": "x86_64",
            "assistantVersion": "2.0.0",
        },
    )
    assert correct.status_code == 200


def test_unknown_portal_architecture_cannot_be_consumed_by_unsupported_target(client):
    token = token_from(issue(client, "windows", "unknown"))
    invalid = client.post(
        "/api/v1/support/sessions/consume",
        json={
            "token": token,
            "platform": "windows",
            "architecture": "x86",
            "assistantVersion": "2.0.0",
        },
    )
    assert invalid.status_code == 400
    valid = client.post(
        "/api/v1/support/sessions/consume",
        json={
            "token": token,
            "platform": "windows",
            "architecture": "x86_64",
            "assistantVersion": "2.0.0",
        },
    )
    assert valid.status_code == 200


def test_unknown_architecture_is_atomically_bound_at_consume(app, client):
    token = token_from(issue(client, "macos", "unknown"))
    response = client.post(
        "/api/v1/support/sessions/consume",
        json={
            "token": token,
            "platform": "macos",
            "architecture": "arm64",
            "assistantVersion": "2.0.0",
        },
    )
    assert response.status_code == 200
    database: Path = app.extensions["support_settings"].database_path
    with sqlite3.connect(database) as connection:
        architecture, consumed_at = connection.execute(
            "SELECT architecture, consumed_at FROM support_sessions"
        ).fetchone()
    assert architecture == "arm64"
    assert consumed_at is not None


def test_macos_manifest_has_only_pinned_identity_fields(client):
    token = token_from(issue(client, "macos", "unknown"))
    response = client.post(
        "/api/v1/support/sessions/consume",
        json={
            "token": token,
            "platform": "macos",
            "architecture": "arm64",
            "assistantVersion": "2.0.0",
        },
    )
    assert response.status_code == 200
    manifest = json.loads(decode64(response.get_json()["payload"]))
    assert set(manifest["artifact"]) == {
        "kind",
        "url",
        "sha256",
        "version",
        "bundleIdentifier",
        "teamIdentifier",
    }
    assert manifest["artifact"]["kind"] == "dmg"
    assert manifest["artifact"]["bundleIdentifier"] == "com.carriez.rustdesk"
    assert manifest["artifact"]["teamIdentifier"] == "ABCDEFGHIJ"


def test_expired_session_is_rejected(app, client):
    token = token_from(issue(client))
    database: Path = app.extensions["support_settings"].database_path
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE support_sessions SET expires_at = 0")
    response = client.post(
        "/api/v1/support/sessions/consume",
        json={
            "token": token,
            "platform": "windows",
            "architecture": "x86_64",
            "assistantVersion": "2.0.0",
        },
    )
    assert response.status_code == 410


def test_persistent_rate_limiter(app):
    store = app.extensions["support_store"]
    assert store.take_rate_limit("test", "actor", 2, 60)[0] is True
    assert store.take_rate_limit("test", "actor", 2, 60)[0] is True
    allowed, retry_after = store.take_rate_limit("test", "actor", 2, 60)
    assert allowed is False
    assert 1 <= retry_after <= 60


def test_cross_origin_and_cross_site_rejected(client):
    response = client.post(
        "/api/v1/support/sessions",
        json={"platform": "windows", "architecture": "x86_64"},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert "Access-Control-Allow-Origin" not in response.headers

    response = client.post(
        "/api/v1/support/sessions",
        json={"platform": "windows", "architecture": "x86_64"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403


def test_invalid_fields_and_targets_rejected(client):
    assert issue(client, "linux", "x86_64").status_code == 400
    response = client.post(
        "/api/v1/support/sessions",
        json={"platform": "windows", "architecture": "x86_64", "command": "calc.exe"},
    )
    assert response.status_code == 400


def test_atomic_consume_allows_only_one_winner(app):
    with app.test_client() as creator:
        token = token_from(issue(creator))
    body = {
        "token": token,
        "platform": "windows",
        "architecture": "x86_64",
        "assistantVersion": "2.0.0",
    }
    barrier = threading.Barrier(2)
    statuses: list[int] = []

    def consume() -> None:
        with app.test_client() as thread_client:
            barrier.wait()
            statuses.append(
                thread_client.post("/api/v1/support/sessions/consume", json=body).status_code
            )

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(statuses) == [200, 410]


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
