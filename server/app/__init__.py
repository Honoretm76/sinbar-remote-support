from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Flask, Response, g, jsonify, request
from werkzeug.exceptions import BadRequest, HTTPException, RequestEntityTooLarge

from .artifacts import ArtifactRegistry, UnsupportedTargetError
from .audit import AuditLogger
from .config import ConfigurationError, Settings
from .security import ManifestSigner, client_actor_key
from .store import SessionStore


def _utc_text(epoch_seconds: int) -> str:
    return (
        datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _json_error(status: int, code: str, message: str) -> tuple[Response, int]:
    return jsonify({"error": {"code": code, "message": message}}), status


def create_app(settings: Settings | None = None) -> Flask:
    # SQLite journals, audit-adjacent state, and any future temporary files must
    # never be group/world-readable, even if the container runtime has a loose
    # default umask.
    os.umask(0o077)
    settings = settings or Settings.from_environment()
    registry = ArtifactRegistry.load(settings)
    signer = ManifestSigner.load(settings)
    store = SessionStore(settings.database_path)
    audit = AuditLogger(settings.audit_key)

    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=settings.max_body_bytes,
        JSON_SORT_KEYS=True,
        PROPAGATE_EXCEPTIONS=False,
    )
    app.extensions["support_settings"] = settings
    app.extensions["support_registry"] = registry
    app.extensions["support_signer"] = signer
    app.extensions["support_store"] = store
    app.extensions["support_audit"] = audit

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(message)s",
        force=True,
    )

    @app.before_request
    def protect_request() -> tuple[Response, int] | None:
        g.request_id = request.headers.get("X-Request-ID", "")
        try:
            uuid.UUID(g.request_id)
        except (ValueError, TypeError, AttributeError):
            g.request_id = str(uuid.uuid4())

        origin = request.headers.get("Origin")
        if origin is not None and origin != settings.public_origin:
            audit.write(
                "request_rejected",
                request_id=g.request_id,
                outcome="origin_denied",
                client_key=_actor_key(settings),
            )
            return _json_error(403, "origin_denied", "Request origin is not allowed.")

        if request.headers.get("Sec-Fetch-Site", "").lower() in {
            "cross-site",
            "same-site",
        }:
            return _json_error(403, "origin_denied", "Cross-site requests are not allowed.")

        return None

    @app.after_request
    def harden_response(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Request-ID"] = getattr(g, "request_id", str(uuid.uuid4()))

        if request.headers.get("Origin") == settings.public_origin:
            response.headers["Access-Control-Allow-Origin"] = settings.public_origin
            response.headers["Vary"] = "Origin"

        return response

    @app.route("/api/v1/support/sessions", methods=["OPTIONS"])
    @app.route("/api/v1/support/sessions/consume", methods=["OPTIONS"])
    def options() -> Response:
        response = Response(status=204)
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Max-Age"] = "600"
        return response

    @app.get("/api/v1/health")
    def health() -> tuple[Response, int]:
        store.ping()
        return jsonify({"service": "sinbar-support-session-api", "status": "ok"}), 200

    @app.post("/api/v1/support/sessions")
    def create_session() -> tuple[Response, int]:
        actor_key = _actor_key(settings)
        allowed, retry_after = store.take_rate_limit(
            "create", actor_key, settings.create_rate_limit, settings.rate_window_seconds
        )
        if not allowed:
            audit.write(
                "session_create",
                request_id=g.request_id,
                outcome="rate_limited",
                client_key=actor_key,
            )
            response, status = _json_error(429, "rate_limited", "Too many session requests.")
            response.headers["Retry-After"] = str(retry_after)
            return response, status

        body = _strict_json({"platform", "architecture"})
        platform = _bounded_string(body.get("platform"), "platform", 16)
        architecture = _bounded_string(body.get("architecture"), "architecture", 16)
        registry.validate_session_target(platform, architecture)

        token, expires_at, session_ref = store.create_session(
            platform=platform,
            architecture=architecture,
            ttl_seconds=settings.session_ttl_seconds,
            token_hash_key=settings.token_hash_key,
        )
        installer_url = settings.installer_url(platform)
        protocol_url = f"sinbarsupport://start?token={token}"

        audit.write(
            "session_create",
            request_id=g.request_id,
            outcome="issued",
            client_key=actor_key,
            session_ref=session_ref,
            platform=platform,
            architecture=architecture,
        )
        return (
            jsonify(
                {
                    "protocolUrl": protocol_url,
                    "expiresAt": _utc_text(expires_at),
                    "installerUrl": installer_url,
                }
            ),
            201,
        )

    @app.post("/api/v1/support/sessions/consume")
    def consume_session() -> tuple[Response, int]:
        actor_key = _actor_key(settings)
        allowed, retry_after = store.take_rate_limit(
            "consume", actor_key, settings.consume_rate_limit, settings.rate_window_seconds
        )
        if not allowed:
            audit.write(
                "session_consume",
                request_id=g.request_id,
                outcome="rate_limited",
                client_key=actor_key,
            )
            response, status = _json_error(429, "rate_limited", "Too many consume requests.")
            response.headers["Retry-After"] = str(retry_after)
            return response, status

        body = _strict_json({"token", "platform", "architecture", "assistantVersion"})
        token = _bounded_string(body.get("token"), "token", 128)
        platform = _bounded_string(body.get("platform"), "platform", 16)
        architecture = _bounded_string(body.get("architecture"), "architecture", 16)
        assistant_version = _bounded_string(
            body.get("assistantVersion"), "assistantVersion", 32
        )
        if not settings.version_pattern.fullmatch(assistant_version):
            raise ApiInputError("assistantVersion must be a semantic version.")

        # Validate and resolve the exact client-reported architecture before
        # atomically consuming an architecture-unknown portal session.
        artifact = registry.find(platform, architecture)

        result = store.consume_session(
            token=token,
            platform=platform,
            architecture=architecture,
            token_hash_key=settings.token_hash_key,
        )
        if result.outcome == "not_found":
            audit.write(
                "session_consume",
                request_id=g.request_id,
                outcome="rejected",
                client_key=actor_key,
            )
            return _json_error(404, "invalid_session", "Session is invalid or unavailable.")
        if result.outcome in {"expired", "consumed"}:
            audit.write(
                "session_consume",
                request_id=g.request_id,
                outcome=result.outcome,
                client_key=actor_key,
                session_ref=result.session_ref,
            )
            return _json_error(410, "session_unavailable", "Session expired or was already used.")
        if result.outcome == "binding_mismatch":
            audit.write(
                "session_consume",
                request_id=g.request_id,
                outcome="binding_mismatch",
                client_key=actor_key,
                session_ref=result.session_ref,
            )
            return _json_error(409, "session_binding_mismatch", "Session does not match this device.")

        manifest = registry.build_job_manifest(
            artifact=artifact,
            session_id=result.job_id,
            ttl_seconds=settings.manifest_ttl_seconds,
        )
        envelope = signer.sign(manifest)

        audit.write(
            "session_consume",
            request_id=g.request_id,
            outcome="consumed",
            client_key=actor_key,
            session_ref=result.session_ref,
            job_id=result.job_id,
            platform=platform,
            architecture=architecture,
        )
        return jsonify(envelope), 200

    @app.errorhandler(ApiInputError)
    def handle_input_error(error: ApiInputError) -> tuple[Response, int]:
        return _json_error(400, "invalid_request", str(error))

    @app.errorhandler(UnsupportedTargetError)
    def handle_unsupported_target(error: UnsupportedTargetError) -> tuple[Response, int]:
        return _json_error(400, "unsupported_target", str(error))

    @app.errorhandler(ConfigurationError)
    def handle_configuration_error(error: ConfigurationError) -> tuple[Response, int]:
        logging.error(
            json.dumps(
                {
                    "event": "configuration_error",
                    "message": str(error),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return _json_error(503, "service_unavailable", "Service configuration is unavailable.")

    @app.errorhandler(BadRequest)
    def handle_bad_json(_error: BadRequest) -> tuple[Response, int]:
        return _json_error(400, "invalid_json", "Request body must contain valid JSON.")

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_error: RequestEntityTooLarge) -> tuple[Response, int]:
        return _json_error(413, "request_too_large", "Request body is too large.")

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception) -> tuple[Response, int]:
        if isinstance(error, HTTPException):
            return _json_error(error.code or 500, "http_error", error.description)
        audit.write(
            "internal_error",
            request_id=getattr(g, "request_id", "unavailable"),
            outcome="failed",
        )
        app.logger.exception("Unhandled support-session API error")
        return _json_error(500, "internal_error", "An internal error occurred.")

    return app


class ApiInputError(ValueError):
    pass


def _strict_json(allowed_keys: set[str]) -> dict[str, Any]:
    if not request.is_json:
        raise ApiInputError("Content-Type must be application/json.")
    body = request.get_json(silent=False)
    if not isinstance(body, dict):
        raise ApiInputError("JSON body must be an object.")
    unknown = set(body) - allowed_keys
    missing = allowed_keys - set(body)
    if unknown:
        raise ApiInputError(f"Unknown field(s): {', '.join(sorted(unknown))}.")
    if missing:
        raise ApiInputError(f"Missing field(s): {', '.join(sorted(missing))}.")
    return body


def _bounded_string(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ApiInputError(f"{field} must be a non-empty string up to {maximum} characters.")
    return value


def _actor_key(settings: Settings) -> str:
    return client_actor_key(
        remote_address=request.remote_addr or "unknown",
        forwarded_for=request.headers.get("X-Forwarded-For"),
        trusted_proxy_cidrs=settings.trusted_proxy_cidrs,
        audit_key=settings.audit_key,
    )
