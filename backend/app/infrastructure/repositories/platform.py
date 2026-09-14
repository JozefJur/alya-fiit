"""Notification outbox and audit log persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models import AuditLogEntry, Notification


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_recent(self, limit: int = 100) -> list[Notification]:
        stmt = select(Notification).order_by(Notification.id.desc()).limit(limit)
        return list(self.session.scalars(stmt))

    def list_for_user(self, user_id: int, limit: int = 100) -> list[Notification]:
        stmt = (
            select(Notification)
            .where(Notification.recipient_user_id == user_id)
            .order_by(Notification.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))


class AuditLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entry: AuditLogEntry) -> AuditLogEntry:
        self.session.add(entry)
        return entry

    def list_recent(self, limit: int = 200) -> list[AuditLogEntry]:
        stmt = select(AuditLogEntry).order_by(AuditLogEntry.id.desc()).limit(limit)
        return list(self.session.scalars(stmt))

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditLogEntry]:
        stmt = (
            select(AuditLogEntry)
            .where(
                AuditLogEntry.entity_type == entity_type,
                AuditLogEntry.entity_id == entity_id,
            )
            .order_by(AuditLogEntry.id)
        )
        return list(self.session.scalars(stmt))
