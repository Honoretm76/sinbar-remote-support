from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .config import ConfigurationError, SEMVER_PATTERN, Settings


ENV_PATTERN = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SUPPORTED = {
    ("windows", "x86_64"),
    ("windows", "arm64"),
    ("macos", "x86_64"),
    ("macos", "arm64"),
}


@dataclass(frozen=True)
class Artifact:
    platform: str
    architecture: str
    version: str
    url: str
    sha256: str
    kind: str
    publisher_subject_contains: str | None = None
    bundle_identifier: str | None = None
    team_identifier: str | None = None


class ArtifactRegistry:
    def __init__(self, artifacts: dict[tuple[str, str], Artifact]):
        self._artifacts = artifacts

    @classmethod
    def load(cls, settings: Settings) -> "ArtifactRegistry":
        try:
            raw = settings.artifact_manifest_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigurationError("Artifact manifest cannot be read") from exc

        def substitute(match: re.Match[str]) -> str:
            name = match.group(1)
            value = os.environ.get(name, "")
            if not value:
                raise ConfigurationError(f"Artifact manifest variable {name} is not configured")
            return value

        expanded = ENV_PATTERN.sub(substitute, raw)
        if "${" in expanded:
            raise ConfigurationError("Artifact manifest contains an invalid variable expression")
        try:
            document = json.loads(expanded)
        except json.JSONDecodeError as exc:
            raise ConfigurationError("Artifact manifest is invalid JSON") from exc

        if not isinstance(document, dict) or set(document) != {
            "schemaVersion",
            "action",
            "attended",
            "artifacts",
        }:
            raise ConfigurationError("Artifact registry fields do not match the fixed schema")
        if document["schemaVersion"] != 1:
            raise ConfigurationError("Artifact manifest schemaVersion must be 1")
        if document["action"] != "ensure-and-launch-rustdesk":
            raise ConfigurationError("Artifact manifest action is not allowlisted")
        if document["attended"] is not True:
            raise ConfigurationError("Only attended support artifacts are allowed")

        rows = document["artifacts"]
        if not isinstance(rows, list):
            raise ConfigurationError("Artifact manifest artifacts must be a list")
        artifacts: dict[tuple[str, str], Artifact] = {}

        for row in rows:
            if not isinstance(row, dict):
                raise ConfigurationError("Every artifact must be an object")
            common_keys = {"platform", "architecture", "version", "url", "sha256", "kind"}
            if not common_keys.issubset(row):
                raise ConfigurationError("Artifact is missing a required field")

            platform = row["platform"]
            architecture = row["architecture"]
            version = row["version"]
            url = row["url"]
            sha256 = row["sha256"]

            if (platform, architecture) not in SUPPORTED:
                raise ConfigurationError("Artifact platform or architecture is unsupported")
            if not isinstance(version, str) or not SEMVER_PATTERN.fullmatch(version):
                raise ConfigurationError("Artifact version must be a semantic version")
            if not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
                raise ConfigurationError("Artifact sha256 must be a verified lowercase SHA-256")
            if not isinstance(url, str):
                raise ConfigurationError("Artifact URL must be a string")
            cls._validate_url(url, settings.support_hostname)

            if platform == "windows":
                expected = common_keys | {"publisherSubjectContains"}
                if set(row) != expected:
                    raise ConfigurationError("Windows artifact fields do not match the fixed schema")
                if row["kind"] != "msi" or row["publisherSubjectContains"] != "PURSLANE":
                    raise ConfigurationError("Windows artifact identity is not allowlisted")
                artifact = Artifact(
                    platform=platform,
                    architecture=architecture,
                    version=version,
                    url=url,
                    sha256=sha256,
                    kind="msi",
                    publisher_subject_contains="PURSLANE",
                )
            else:
                expected = common_keys | {"bundleIdentifier", "teamIdentifier"}
                if set(row) != expected:
                    raise ConfigurationError("macOS artifact fields do not match the fixed schema")
                team_identifier = row["teamIdentifier"]
                if row["kind"] != "dmg" or row["bundleIdentifier"] != "com.carriez.rustdesk":
                    raise ConfigurationError("macOS artifact identity is not allowlisted")
                if not isinstance(team_identifier, str) or not re.fullmatch(
                    r"[A-Z0-9]{10}", team_identifier
                ):
                    raise ConfigurationError("macOS teamIdentifier must be verified and configured")
                artifact = Artifact(
                    platform=platform,
                    architecture=architecture,
                    version=version,
                    url=url,
                    sha256=sha256,
                    kind="dmg",
                    bundle_identifier="com.carriez.rustdesk",
                    team_identifier=team_identifier,
                )

            key = (platform, architecture)
            if key in artifacts:
                raise ConfigurationError("Duplicate artifact platform and architecture")
            artifacts[key] = artifact

        if set(artifacts) != SUPPORTED:
            missing = sorted(SUPPORTED - set(artifacts))
            raise ConfigurationError(f"Artifact manifest is incomplete: {missing}")
        return cls(artifacts)

    @staticmethod
    def _validate_url(url: str, support_hostname: str) -> None:
        try:
            parsed = urlparse(url)
            port = parsed.port
        except ValueError as exc:
            raise ConfigurationError("Artifact URL is malformed") from exc
        if (
            parsed.scheme != "https"
            or parsed.hostname != support_hostname
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or parsed.query
            or parsed.fragment
        ):
            raise ConfigurationError(
                "Artifact URLs must be HTTPS URLs on the configured support host"
            )

    @staticmethod
    def validate_session_target(platform: str, architecture: str) -> None:
        if platform not in {"windows", "macos"}:
            raise UnsupportedTargetError("Unsupported platform or architecture.")
        if architecture not in {"unknown", "x86_64", "arm64"}:
            raise UnsupportedTargetError("Unsupported platform or architecture.")

    def find(self, platform: str, architecture: str) -> Artifact:
        try:
            return self._artifacts[(platform, architecture)]
        except KeyError as exc:
            raise UnsupportedTargetError("Unsupported platform or architecture.") from exc

    @staticmethod
    def build_job_manifest(
        artifact: Artifact, session_id: str, ttl_seconds: int, now: int | None = None
    ) -> dict[str, Any]:
        issued_at = int(time.time()) if now is None else now
        artifact_payload: dict[str, Any] = {
            "kind": artifact.kind,
            "sha256": artifact.sha256,
            "url": artifact.url,
            "version": artifact.version,
        }
        if artifact.platform == "windows":
            artifact_payload["publisherSubjectContains"] = artifact.publisher_subject_contains
        else:
            artifact_payload["bundleIdentifier"] = artifact.bundle_identifier
            artifact_payload["teamIdentifier"] = artifact.team_identifier

        return {
            "action": "ensure-and-launch-rustdesk",
            "architecture": artifact.architecture,
            "artifact": artifact_payload,
            "attended": True,
            "expiresAt": _utc_text(issued_at + ttl_seconds),
            "issuedAt": _utc_text(issued_at),
            "platform": artifact.platform,
            "schemaVersion": 1,
            "sessionId": session_id,
        }


class UnsupportedTargetError(ValueError):
    pass


def _utc_text(epoch_seconds: int) -> str:
    return (
        datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
