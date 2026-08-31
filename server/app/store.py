from __future__ import annotations

import os
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .security import base64url, session_reference, token_digest


@dataclass(frozen=True)
class ConsumeResult:
    outcome: str
    session_ref: str = ""
    job_id: str = ""


class SessionStore:
    def __init__(self, database_path: Path):
        self._path = database_path
        database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            database_path.parent.chmod(0o700)
        except PermissionError:
            pass
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA secure_delete=FAST")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS support_sessions (
                    token_hash BLOB PRIMARY KEY,
                    platform TEXT NOT NULL,
                    architecture TEXT NOT NULL,
                    job_id TEXT NOT NULL UNIQUE,
                    issued_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    consumed_at INTEGER
                ) WITHOUT ROWID;

                CREATE INDEX IF NOT EXISTS support_sessions_expiry
                    ON support_sessions(expires_at);

                CREATE TABLE IF NOT EXISTS rate_limits (
                    scope TEXT NOT NULL,
                    actor_key TEXT NOT NULL,
                    window_start INTEGER NOT NULL,
                    request_count INTEGER NOT NULL,
                    PRIMARY KEY (scope, actor_key, window_start)
                ) WITHOUT ROWID;
                """
            )
        try:
            os.chmod(self._path, 0o600)
        except PermissionError:
            pass

    def ping(self) -> None:
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()

    def create_session(
        self,
        platform: str,
        architecture: str,
        ttl_seconds: int,
        token_hash_key: bytes,
    ) -> tuple[str, int, str]:
        now = int(time.time())
        expires_at = now + ttl_seconds
        token = base64url(secrets.token_bytes(32))
        digest = token_digest(token, token_hash_key)
        job_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM support_sessions WHERE expires_at < ?",
                (now - 3600,),
            )
            connection.execute(
                """
                INSERT INTO support_sessions
                    (token_hash, platform, architecture, job_id, issued_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (digest, platform, architecture, job_id, now, expires_at),
            )
            connection.commit()
        return token, expires_at, session_reference(digest)

    def consume_session(
        self,
        token: str,
        platform: str,
        architecture: str,
        token_hash_key: bytes,
    ) -> ConsumeResult:
        # Canonical tokens are exactly 32 random bytes encoded as unpadded base64url.
        if len(token) != 43 or any(character not in _BASE64URL for character in token):
            return ConsumeResult("not_found")
        digest = token_digest(token, token_hash_key)
        reference = session_reference(digest)
        now = int(time.time())

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT platform, architecture, job_id, expires_at, consumed_at
                FROM support_sessions
                WHERE token_hash = ?
                """,
                (digest,),
            ).fetchone()
            if row is None:
                connection.rollback()
                return ConsumeResult("not_found")
            if row["consumed_at"] is not None:
                connection.rollback()
                return ConsumeResult("consumed", reference, row["job_id"])
            if row["expires_at"] < now:
                connection.rollback()
                return ConsumeResult("expired", reference, row["job_id"])
            if row["platform"] != platform or row["architecture"] not in {
                "unknown",
                architecture,
            }:
                connection.rollback()
                return ConsumeResult("binding_mismatch", reference, row["job_id"])

            cursor = connection.execute(
                """
                UPDATE support_sessions
                SET consumed_at = ?, architecture = ?
                WHERE token_hash = ?
                  AND consumed_at IS NULL
                  AND expires_at >= ?
                  AND platform = ?
                  AND architecture IN ('unknown', ?)
                """,
                (now, architecture, digest, now, platform, architecture),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return ConsumeResult("consumed", reference, row["job_id"])
            connection.commit()
            return ConsumeResult("consumed_ok", reference, row["job_id"])

    def take_rate_limit(
        self, scope: str, actor_key: str, limit: int, window_seconds: int
    ) -> tuple[bool, int]:
        now = int(time.time())
        window_start = now - (now % window_seconds)
        retry_after = max(1, window_start + window_seconds - now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM rate_limits WHERE window_start < ?",
                (window_start - window_seconds,),
            )
            row = connection.execute(
                """
                SELECT request_count FROM rate_limits
                WHERE scope = ? AND actor_key = ? AND window_start = ?
                """,
                (scope, actor_key, window_start),
            ).fetchone()
            count = 0 if row is None else int(row["request_count"])
            if count >= limit:
                connection.rollback()
                return False, retry_after
            connection.execute(
                """
                INSERT INTO rate_limits(scope, actor_key, window_start, request_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(scope, actor_key, window_start)
                DO UPDATE SET request_count = request_count + 1
                """,
                (scope, actor_key, window_start),
            )
            connection.commit()
            return True, retry_after


_BASE64URL = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
