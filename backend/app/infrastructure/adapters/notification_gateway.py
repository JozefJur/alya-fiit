"""Notification port and the outbox implementation (no real e-mail)."""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.domain.entities.enums import NotificationType
from app.infrastructure.persistence.models import Notification


class NotificationGateway(Protocol):
    def send(
        self,
        *,
        recipient_user_id: int,
        notification_type: NotificationType,
        subject: str,
        body: str,
        payload: dict[str, Any],
    ) -> None: ...


class OutboxNotificationGateway:
    """Writes notifications into the database outbox table.

    Nothing leaves the machine; tests and the admin UI read the outbox to
    verify what *would* have been sent.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def send(
        self,
        *,
        recipient_user_id: int,
        notification_type: NotificationType,
        subject: str,
        body: str,
        payload: dict[str, Any],
    ) -> None:
        self._session.add(
            Notification(
                recipient_user_id=recipient_user_id,
                notification_type=notification_type,
                subject=subject,
                body=body,
                payload_json=payload,
            )
        )


class CollectingNotificationGateway:
    """Test double: keeps sent notifications in memory."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(
        self,
        *,
        recipient_user_id: int,
        notification_type: NotificationType,
        subject: str,
        body: str,
        payload: dict[str, Any],
    ) -> None:
        self.sent.append(
            {
                "recipient_user_id": recipient_user_id,
                "notification_type": notification_type,
                "subject": subject,
                "body": body,
                "payload": payload,
            }
        )
