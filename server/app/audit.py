from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


ALLOWED_FIELDS = {
    "architecture",
    "client_key",
    "job_id",
    "outcome",
    "platform",
    "request_id",
    "session_ref",
}


class AuditLogger:
    """Structured security audit records without tokens, IPs, or request bodies."""

    def __init__(self, _audit_key: bytes):
        self._logger = logging.getLogger("sinbar.support.audit")

    def write(self, event: str, **fields: Any) -> None:
        safe = {key: value for key, value in fields.items() if key in ALLOWED_FIELDS}
        safe.update(
            {
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            }
        )
        self._logger.info(json.dumps(safe, separators=(",", ":"), sort_keys=True))

