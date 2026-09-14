"""Append-only audit trail for security- and business-significant events."""

from __future__ import annotations

from typing import Any

from app.infrastructure.persistence.models import AuditLogEntry
from app.infrastructure.repositories.platform import AuditLogRepository


class AuditLogService:
    """Records who did what to which entity.

    Called from use cases inside their transaction, so an audit entry commits
    if and only if the audited change commits.
    """

    def __init__(self, repository: AuditLogRepository) -> None:
        self._repository = repository

    def record(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: int | str,
        details: dict[str, Any] | None = None,
    ) -> AuditLogEntry:
        if not action or "." not in action:
            raise ValueError("action must look like '<area>.<event>', e.g. 'order.created'")
        entry = AuditLogEntry(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            details_json=self._sanitized(details or {}),
        )
        return self._repository.add(entry)

    @staticmethod
    def _sanitized(details: dict[str, Any]) -> dict[str, Any]:
        """Audit entries must never store secrets or raw tokens."""
        redacted = {}
        for key, value in details.items():
            if key in {"password", "password_hash", "token", "jwt"}:
                redacted[key] = "***"
            else:
                redacted[key] = value
        return redacted
